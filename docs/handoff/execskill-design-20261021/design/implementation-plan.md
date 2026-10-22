# fivebench-execskill-v1 — implementation plan (for implementers)

Status: 2026-10-21, written before any code. Companion of `registration-draft.md` (same directory; "REG §n" below). The
registration decides WHAT is measured and the thresholds; this plan decides HOW it is built. Where they disagree, the
registration wins and the plan is a bug. Line references to frozen code were taken from the local repo
(`/Users/dulin/Documents/Paper/SkillOpt`), which is byte-identical to `dl:/data/coevo5-20261019-v3-source-f` for `skillopt/`,
`scripts/`, `tests/` [CI F3].

Hard rules for every implementer:
- Never edit a frozen file (`skillopt/coevo5/*`, `skillopt/continual_eval/*`, `scripts/run_coevo5.py`, `scripts/weak_solver_probe.py`,
  any scorer, any v3 artifact). Import or copy (REG §1).
- No paid call, no `.env` print, no test-pool path in any test or fixture. All tests run offline with fakes (§7).
- Every new record carries `version = "fivebench-execskill-v1-<kind>"` and `evidence` (REG §1).
- Write-once artifacts use the frozen `validator_pilot.api.write_json`/`digest` semantics (canonical JSON:
  `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`).
- Model-written code is executed ONLY through `execskill.sandbox.client` (§4). No `exec`/`eval` of model text on the host, ever.

## 1. Package layout `skillopt/execskill/` (one line per module)

Legend: **imp** = imported unchanged; **copy(p)** = copied from the named frozen function with parameter changes p; **new** = new code.

| Module | Purpose | Main API (signatures) | Reuse |
|---|---|---|---|
| `__init__.py` | package marker; `VERSION = "fivebench-execskill-v1"` | — | new |
| `protocol.py` | all registered constants: VERSION, ORDER, seeds/tags, sizes (REG §3.3), thresholds (REG §6.4, §7), caps (REG §9.3), M/B per bench, timeouts, slots, lexicons, templates (COMPUTE_INVITE, COMPUTE_FOLLOWUP, NOTE_HEADERS, NOT_RECOMMENDED_PREFIX, REPAIR_FRAME), placebo corpus pointer | constants only; `kind(name) -> "fivebench-execskill-v1-" + name` | new (values transcribed from REG; PLACEBO texts imported from `coevo5.protocol` by value and re-hashed) |
| `errors.py` | route-B stop classes | `class SandboxUnavailable(RuntimeError)`, `PackageInvalid(ValueError)`, `ConsumptionConflict(RuntimeError)`; `STOP_KINDS` = coevo5 cells.STOP_KINDS ∪ {sandbox, package, consumption} | new; re-exports `BudgetStop, AssumptionBroken, LedgerFailure, ConfigurationError, CleanupUnconfirmed` from **imp** `coevo5.outcomes` (ONE exception set) |
| `client.py` | elucid solver client | `class ElucidClient(weak_solver_probe.Client)`: `__init__(self, env_path, *, proxy, max_tokens, read_timeout, transport=None)` (does NOT call `super().__init__`, which rejects models outside MODELS, weak_solver_probe.py:228-233); `_receipt(self, status, data, attempts, started) -> dict` (calls super, then reads `usage.completion_tokens_details.reasoning_tokens` and `message.reasoning_content`; reasoning → `ok=False, error_type="thinking_mismatch", subtype="reasoning_mismatch"`; adds `visible_completion_tokens`, `over_nominal`); request body adds `"reasoning_effort": "none"`, no `thinking` field | **imp** `weak_solver_probe._read_env, _validated_url, GATEWAY, Client.call` |
| `budgets.py` | ledger scope helpers | `solver_scopes(bench, k, kind, attempt=None) -> tuple`, `glm_scopes(role, bench, k) -> tuple`; kinds ∈ {run, examiner, selftest, accept, test, smoke}; `endpoint(setting, scopes, *, client, max_tokens_bound) -> calls.Endpoint` | **imp** `coevo5.budget.Budget, rooted`; **imp** `calls.Endpoint` constructed with `max_tokens = B` (REG §4.1) |
| `slots.py` | route-B slot pools with timeouts and lock order | `class TimedSlots(calls.Slots)`: `hold(self, *, timeout_s) -> ContextManager` raising `SandboxUnavailable` on timeout; `LOCK_ORDER = ("alfworld-episode", "execskill-sandbox", <model pool>, "spreadsheet-native")`; `assert_order(held, next)` | **copy**(`calls.Slots.hold`: add timeout, order assertion); model slots stay in the frozen Endpoint |
| `package.py` | procedure/package objects, canonical JSON, validation, content addressing | `@dataclass(frozen=True) Procedure`, `Package` (REG §2.1); `load(path) -> Package`; `save(root, package) -> sha`; `validate(package) -> None` (caps, ids, hooks ⊆ HOOKS, module shape); `with_(package, add=(), revise=(), remove=(), narrow={}) -> Package`; `withhold(package, ids) -> Package` | new; **imp** `validator_pilot.api.digest` |
| `policy.py` | static AST/name policy (hygiene + determinism layer, not the boundary) | `check(source, *, bench) -> list[Violation]`; `POLICY` (allowed imports, forbidden names/attributes incl. sympify, parse_expr, pandas eval/query/read_*/to_*, numpy load/save/fromfile/random except default_rng(seed), openpyxl.load_workbook, datetime.now/today, Timestamp.now, print, dunder attributes; module-level: imports, constants ≤ 2,000 chars, defs only); `policy_sha256()`; static bans C4b: LiveMath meta-option fragments, OfficeQA bulletin literals, ALFWorld numbered receptacle literals | new |
| `sandbox/client.py` | host side of the sandbox | `class Worker`: `start(package, *, kind, inputs_dir=None)`, `call(proc_id, fn, args, *, timeout_s) -> Result`, `close()`; `Result = {ok, value, value_sha256, cpu_ms} | {ok: False, fault, exc_type, message, line}`; `docker_command(kind, limits, mounts) -> list[str]`; `cleanup(name) -> None` (raises `CleanupUnconfirmed`); `with_worker(...)` context manager; lazy start on first call | new; flags **copy**(`backends._native` command list, backends.py:169-178, plus REG §2.6 extras) |
| `sandbox/worker.py` | in-container worker (pinned, mounted read-only at `/runner/worker.py`) | `main()` reads length-prefixed frames on stdin and writes them on a private dup of the original stdout (fd 1 itself is redirected to stderr, see §4); ops `load`, `call`, `ping`; each `call` → `os.fork()`; child: dup2 /dev/null → 0/1/2, `setrlimit(CPU, AS, FSIZE=0, NOFILE)`, `oom_score_adj=1000`, fresh module namespace from the loaded source, run hook, serialize with `json.dumps(sort_keys, allow_nan=False)`, size/nesting caps, write result to its own pipe; parent enforces wall timeout with `SIGKILL`; `ping` returns `{worker_sha256, hashseed, python, libs}`; fixed helpers exposed to procedures: `public_workbook()` (openpyxl on the mounted read-only file, values + formulas), `safe_sympify(text)` (tokenizer whitelist → sympy constructors, no eval) | new; runs inside image `sha256:0a0a5dcb…` |
| `sandbox/policy.json` | serialized POLICY (hashed into the manifest) | — | generated by `policy.py` |
| `compute.py` | fixed exact evaluator for `<calc>` | `parse_tags(reply) -> list[str]` (≤ 8, ≤ 300 chars); `evaluate(expr, bindings) -> {"value": str} | {"value": "not evaluated", "error": cls}`; guards: names ⊆ bindings, |exponent| ≤ 12, depth ≤ 20, bit length ≤ 4,096 (checked BEFORE each op), per-cell watchdog | **copy**(`coevo5.forward._tree/_value/evaluate/literals/rounded`, forward.py:105-221: MAX_EXPONENT 10→12, add names, keep MAX_BITS 4096) |
| `notes.py` | typed note rendering + lexicon screen | `render(fields, *, bench, header) -> str`; `screen(fields, *, bench) -> (kept, dropped)`; FIELD_TYPES = {facts: [str≤200], table: [[str≤40]] ≤ 20×12, candidates: [str≤120], warnings: [str≤200], bindings: [{name, value, quote}]}; `LEXICON[bench]` | new |
| `router.py` | deterministic routing | `route(package, bench, routing_view, worker, *, withhold=frozenset()) -> RouteLog`; `plan(package, parent, bench, views, worker) -> FiringPlan` (A\* computation, twin draws, yoke pairs; zero model calls) | new |
| `solver.py` | the shell: copied QA/Sheet `solve` + ALFWorld loop with hooks | `solve(bench, public, card_text, package, call, *, runtime, worker, withhold=frozenset(), placebo=None, shadow=None) -> prediction` (prediction = frozen shapes + key `shell`, REG §2.3); `_solve_qa`, `_solve_sheet`, `_solve_alfworld` | **copy**(`backends.solve` :364-455, `_solve_alfworld` :715-783: hooks of §3; native slot only around `_native`; ALFWorld catch-all re-raises route-B stops); **imp** helpers `_public_view, _response, _sheet_preview, _xlsx_bytes, _runtime_limits, _new_alfworld, _AlfSession, _alf_post_observation, _completed_without_text, _prediction_unknown, _layout_supported`, contract constants |
| `canonical.py` | level-1 ALFWorld canonicaliser | `canonical(reply, admissible) -> (action, how)` with `how ∈ {tag_exact, tag_level1, whole_exact, whole_level1, unchanged}`; NO earliest-admissible search | new (do NOT port D3 `parse` lines 178-195) |
| `precheck.py` | SpreadsheetBench public-input pre-check | `precheck(program, task, runtime) -> RunReport{status, exc_type, message≤500, answer_cells≤2000}`; uses the frozen `_native` docker argv/env byte-for-byte with a copied worker returning the last traceback line | **copy**(`backends._native` :153-214, `native_worker.py` → `execskill/precheck_worker.py` returning message) |
| `placebo.py` | placebo twins P_y, P_i | `yoke_pairs(items, seed_tag) -> dict`; `sham_fields(proc, item, pair_output, *, kind) -> fields` (keeps constant header; length band ±20%); `sham_compute()` → "not evaluated" + echo; `sham_repair(previous_program, execution_error, advice_len)`; `sham_discourage(admissible, n, seed)`; `shadow(package_new, trajectory) -> triggers` | new; corpus = **imp** values of `coevo5.protocol.PLACEBOS_SCREEN/CONFIRM` |
| `judge.py` | scorer v2 + format flags | `judge(bench, public, private, prediction, receipts, *, runtime) -> {"official", "final", "v2", "lenient", "format", "flags"}`; `json_answer(reply) -> str|None`; invariant `v2.pass >= final.pass` asserted | **imp** `backends.score, _score_answer_tag`, `outcomes.classify/finalize`, `scoring.lenient`; v2 is new |
| `outcomes_ext.py` | rows P1–P7 in front of frozen `outcomes.classify` | `classify(bench, prediction, score, receipts, *, refused, spent) -> Verdict` (P-rows first, then frozen); tokens `unknown_fault`; `delivery(receipts) -> worst` | **imp** `outcomes.classify, Verdict, UNDELIVERED_ERRORS` |
| `stats_ext.py` | statistics | `item_scores(cells, arm, items, *, side) -> dict` (L/H with `unknown_fault`); `signflip(d, *, strata=None, clusters=None, n=100_000, seed) -> p`; `bootstrap_ci(...)`; `iut(d1, d2, ...) -> Decision`; `holm(pvals) -> adjusted`; `power_table(...)` | **imp** `stats.bounds, total, sign_test, bootstrap` |
| `cells.py` | one cell | `run_cell(context, cell, task, package, arm) -> record`; `_solve(...)`; `_replay(context, cell, task, package, recorders)` replays the ORDERED list of sends and reads stored pre-check reports; `run_cells(context, jobs, *, workers)`; `run_parallel` | **copy**(`coevo5.cells` :1-263: VERSION, injectable solver, record keys + `package_sha256, arm_kind, enabled, withheld, faults, deciding_receipt, judge, evidence`; drop `on_reply` native grab; delivery = worst receipt) |
| `units.py` | unit runner | `run_unit(unit_root, *, run, identity, work)`, `complete`, `unit_path`, `cell_context`, `Setting` | **copy**(`coevo5.units` :50-160: VERSION; route-B chains) |
| `rounds.py` | interleaved rounds | `run_round(setting, attempt, endpoint, unit, arms, schedule, tasks, *, tag, blocks=None)`; `_order(values, tag)`; `table_of`; `shared_unanswered`; `guard(cells, arms, unit)` (infrastructure only; `unknown_fault` excluded); `balance(cells) -> ok` (start-time guard) | **copy**(`step.run_round, _order, table_of, shared_unanswered, guard, key, bench_of, pool_tasks`, step.py:71-157) |
| `registry.py` | root-independent consumption registry | `register(bench, items, *, unit, purpose, run_root)`; `dispatch(bench, items, *, unit)`; `decide(bench, items, *, unit)`; `release(bench, items, *, unit)` (routed_not_dispatched); `consumed(bench) -> set`; fcntl lock; raises `ConsumptionConflict` | new |
| `supply.py` | supplies and slices | `searchqa_tail(manifest_path, hf_cache, *, start=4001, exclude) -> list` (tail-only, hash-checks blocks A-D, never writes C/D); `alfworld_items(data_root, pool_ids) -> list` (rooms, task types from path prefix, initial routing view by zero-call reset); `order(bench, supply) -> list` (`data.ranked`, room grouping for ALFWorld); `slices(bench, order, sizes, consumed) -> dict` | **imp** `data.ranked, pool, item_hash`; **copy**(`scripts/make_searchqa_fresh_sample.build` order logic: tail-only) |
| `exclusion.py` | test exclusion under TestAccess | `exclude_tests(pinned, supply, *, access) -> {"counts", "exclusion_sha256"}`; `alfworld_test_identity(access) -> {"split": "valid_unseen", "disjoint": bool, "counts"}` | **imp** `data.TestAccess, test_ids` |
| `trajectories.py` | trajectory and enable-log records | `write(attempt, cell_id, record)`; `load_run(unit)`; `masked_view(traj, *, bench, purpose)` (detector view: answer content, run status hidden; ALFWorld prefix 10 steps); `whitelisted(traj)` | new |
| `replay.py` | zero-call replay and engineer checks C5–C9 | `zero_crash(package, change, trajectories, worker_pair) -> report` (two workers, PYTHONHASHSEED 0 and 1, two item orders); `run_tests(change, trajectories, worker) -> report` with fixed property kinds (`applies_true/false, note_contains, note_matches, discourage_contains/excludes, binding_equals, repair_requested, state_equals`), non-vacuity, differential and negative tests; `reference_tracker_agreement(proc, alf_trajectories) -> float` | new; reference tracker = fixed port of D3 hand tracker (registrar code) |
| `detectors.py` | mechanical categories + model detectors | `MECHANICAL[bench]: dict[name, fn]`; `evaluate(detector, views, worker) -> fired`; `accept(detector, hold, mech_and_library) -> {accepted, precision, base, lb90, recall, jaccard, n_fired, n_items}` (residual cells, item-cluster bootstrap) | new |
| `generators/` (`officeqa.py`, `livemath.py`, `sheet.py`, `alfworld_select.py`) | apply examiner perturbation specs with fixed truth | `apply(spec, item, *, private) -> item | Drop(reason)`; LiveMath truth in sandbox via `safe_sympify` at 50 digits; Sheet via recalc image + `qualify.qualify`; ALFWorld `select(filter_spec, pool_views) -> games` + `null_select(n, seed)` | **imp** `forward.evaluate` kernel (via `compute.py`), `qualify.qualify`, `sheet_recalc`; D6 drop reasons as template |
| `examiner.py` | examiner role prompts + parsing | `detector_write(roles, payload) -> [detector]`; `generator_write(roles, payload) -> [generator]`; `policy_revise(...)`; `gates(generator, ...) -> GateRecord` (T, D band, S shortcut, L labels) | **imp** `roles.Roles.plain/fit`; new parsers |
| `engineer.py` | engineer role + fixed checks C1–C10 | `propose(roles, payload) -> Manifest + sources`; `check(change, ctx) -> CheckReport`; `fix(roles, change, report) -> change`; `candidate(parent, changes) -> Package` | **imp** `roles`, `leakage.normalize, Corpus, findings, mechanical, adjudicate` |
| `describer.py` | text twin at freeze | `describe(roles, procedure) -> text` (pinned prompt, one call, frozen sha) | new |
| `acceptance.py` | one acceptance round + decision | `prepare(step) -> Sealed{candidate_sha, placebo_y, placebo_i, plan(A*), twins, G_acc}`; `dispatch(sealed, blocks)`; `decide(cells, sealed) -> decision.json` (D1–D7, REG §6.4) | new; uses `stats_ext`, `rounds` |
| `validity.py` | predictive validity metric | `pairs(decision, g_acc_cells) -> [pair]`; `status(generator_history) -> "validated"|"refuted"|"not_evaluable"` (≥ 8 informative pairs, slope permutation test, negative controls) | new |
| `step.py` | eight sub-steps of one step | `run_step(setting, chain, bench, k, parent) -> StepRecord` (units run, diagnose, generate, engineer, selftest, accept-b<m>, decision, freeze) | new orchestration over copied units |
| `evaluation.py` | multi-arm test read | `evaluate(unit_root, *, run, shared, pinned, chain, bench, arms, plan, context, workers)`; consent check with new key set; structural-zero sharing; `unseal(chain_root, ..., keyed by (arm, task_id, run))` refusing until the owner's continuation file exists | **copy**(`coevo5.evaluation` :43-450: CONSENT_FIELDS new set, multi-arm, re-keyed unseal) |
| `qualify.py` | SB qualification with importable versions | `load(path, *, importable=IMPORTABLE) -> record`; `reverify(record) -> None` (zero calls, pinned hashes) | **copy**(`coevo5.qualify.load` :134-140) + **imp** `qualify.qualify` |
| `manifest.py` | manifest build/verify | `make(out, **pins) -> path`; `load(path, *, verify=True)`; `verify_code(manifest)`; `environment()` (python, docker version, image digests via `docker image inspect`, in-image `pip freeze` via one sandbox ping); FIELDS (§2.9) | **copy**(`coevo5.manifest` :33-151) |
| `readout.py` | registered readouts | `q1_home`, `q2_similar`, `q3_noninferiority`, `code_vs_text`, `labels(holm=True)`, `format_withholding`; tables with M/E labels | new |
| `chain.py` | chain runner | `run(setting, chain)`, `terminate`, child launch per bench evaluation; `.runner.lock`; `chain-complete.json` | **copy**(`coevo5.chain` :57-310) |
| `smoke.py` | smoke stages S0–S4 | `s0()`, `s1_probe()`, `s2_solver()`, `sn1_noise()`, `s3_roles()`, `s4_ministep()`, `summary()`; format floor 0.9 and margin 1/20 | **copy**(`coevo5.smoke.format_check` pattern :69-77, :275-310) |
| `prelaunch.py` | snapshot verify, pytest, zero-call checks | `verify_snapshot(list_path)`, `zero_call_checks()`, `leftovers()` (excludes D3/D14 workers by command-line match, lists them) | **copy**(`coevo5.prelaunch` helpers) |
| `scripts/run_execskill.py` | CLI (§6) | argparse subcommands | **copy**(`scripts/run_coevo5.py` :238-311 pattern) |

## 2. Data shapes (JSON)

All records: canonical JSON, write-once, with `version`, `evidence`, `record_sha256` (digest of the record minus that field).

### 2.1 Procedure and package
```json
{"version":"fivebench-execskill-v1-procedure","id":"p-spreadsheetbench-1-2","origin":"spreadsheetbench",
 "accepted_at":null,"description":"<=600 chars","hooks":["applies","before_call","sheet_feedback"],
 "source":"<python module, <=6000 B>","header":"<constant instruction header, <=200 chars, rendered by the shell>",
 "max_note_chars":1500,"requests_second_call":false,"state_bytes":0,"excluded_benches":[],
 "replay_tests":[{"id":"rt-1","trajectory":"spreadsheetbench/<item>/S/1/<unit16>","hook":"sheet_feedback",
   "property":{"kind":"repair_requested","value":true},"claims_fix":true,
   "nonvacuity":{"withheld_expect":false,"mutation":"drop_exception_message"}}],
 "lineage":{"parent":null,"revises":null,"engineer_call":"<request sha256>"},"sha256":"..."}
```
```json
{"version":"fivebench-execskill-v1-package","parent_sha256":"...|null","procedures":["<proc sha256>", "..."],
 "order":["p-...","p-..."],"retired":["<sha>"],"narrowed":{"<id>":["officeqa"]},"step":"pilot/s1-spreadsheetbench/t1",
 "describer":{"<id>":{"text_sha256":"...","prompt_sha256":"..."}},"sha256":"..."}
```

### 2.2 Route log / enable log
```json
{"version":"fivebench-execskill-v1-route","package_sha256":"...","bench":"officeqa","routing_view_sha256":"...",
 "per_procedure":{"p-officeqa-2-1":{"applies":true,"enabled":true,"withheld":false,"fault":null}},
 "enabled":["p-officeqa-2-1"],"route_sha256":"..."}
```
Enable log line (`<unit>/attempt-N/enable_log.jsonl`, append-only, after the cell record): `{unit, arm, bench, item, run,
enabled, withheld, applies, faults, route_sha256}`.

### 2.3 Trajectory (training-side units only; test units store hashes only)
```json
{"version":"fivebench-execskill-v1-trajectory","cell":"<cell id>","bench":"officeqa","arm":"S'","package_sha256":"...",
 "route":{"...":"RouteLog"},
 "calls":[{"purpose":"first","system":"<text>","user":"<text>","request_sha256":"...","receipt":{"...":"summary"}},
          {"purpose":"second","system":"...","user":"...","request_sha256":"...","receipt":{}}],
 "replies":["<first reply>","<second reply>"],"deciding_receipt":1,
 "shell":{"notes":[{"id":"...","fields":{},"rendered_chars":812,"dropped":[]}],
          "compute":{"tags":["..."],"results":[{"expr":"...","value":"..."}]},
          "precheck":{"status":"exception","exc_type":"KeyError","message":"..."},
          "procedure_calls":[{"id":"...","fn":"before_call","args_sha256":"...","value_sha256":"...","fault":null,"cpu_ms":12}],
          "faults":[{"procedure":"...","hook":"...","kind":"timeout","exc_type":"...","message":"<=500"}],
          "fallback":null},
 "alfworld_steps":[{"i":0,"view_sha256":"...","notes":"...","discouraged":["..."],"reply":"...","action":"...","how":"tag_exact",
          "post_observation":"<=12000 chars","state_sha256":{"<id>":"..."}}],
 "judge":{"official":{},"final":{},"v2":{"token":"pass"},"lenient":{},"format":{},"flags":[]},
 "token":"pass|fail|unknown|unknown_fault|unknown_artifact","dispatch_ts":"...","finish_ts":"..."}
```

### 2.4 Detector record
```json
{"version":"fivebench-execskill-v1-detector","id":"d-alfworld-1-1","bench":"alfworld","source":"<python>",
 "description":"...","view":"alf_prefix10|qa_masked|sheet_masked","written_from":"<unit>/write-half",
 "validation":{"hold_unit":"...","residual_cells":118,"n_fired":14,"n_items":9,"precision":0.86,"base":0.55,
   "lb90_precision_minus_base":0.12,"recall_residual":0.21,"jaccard_max":0.31,"faults":0,"deterministic":true,
   "accepted":true},"retired_at":null}
```

### 2.5 Generator and generated-item set
```json
{"version":"fivebench-execskill-v1-generator","id":"g-officeqa-2-1","bench":"officeqa","source":"<python emitting specs>",
 "params":{"...":"..."},"source_sha256":"...",
 "gates":{"truth":{"made":80,"dropped":{"format":3,"reproduction_failed":11,"literal_not_in_context":2,"answer_in_context":1}},
          "band":{"probe_items":30,"pass_rate":0.47,"adjustments":1,"in_band":true},
          "shortcut":{"probe":"question_only","flagged_share":0.07,"used":true},"labels":{"key_balance":{"A":0.2}}},
 "status":"admitted|validated|refuted|not_evaluable","pairs":[{"step":"...","contrast":"S'-S","d_gen":0.03,"d_real":0.05,
   "se_gen":0.04,"se_real":0.06,"informative":false,"negative_control":false}]}
```
Generated item (one line of `items.jsonl`): `{"id":"gen:<gen>:<n>","source_item":"<id>","public":{...frozen bench schema},
"private":{"answer": "...","truth":{"kind":"formula|sympy|recalc|simulator","expr":"...","checked_by":"execskill.generators.officeqa"}},
"set":"G_self|G_acc","seed":123}`.

### 2.6 Acceptance record (`decision/decision.json`)
```json
{"version":"fivebench-execskill-v1-decision","step":"pilot/s1-spreadsheetbench/t1","bench":"spreadsheetbench",
 "freshness":"route_b_fresh_method_side_reused","sealed":{"candidate":"<sha>","parent":"<sha>","placebo_y":"<sha>",
 "placebo_i":"<sha>|null","plan_sha256":"...","twins_sha256":"...","g_acc_sha256":"...|null"},
 "A":60,"A_star":41,"runs":2,"blocks":["b1"],"mde_registered":0.12,
 "contrasts":{"S'-S":{"mean":0.06,"whole_batch":0.041,"p_signflip":0.03,"ci95":[-0.01,0.13],"up":9,"down":3,"tie":29},
              "S'-P_y":{"...":"..."},"P_y-S":{"...":"..."},"P_i-S":{"...":"..."},"S'-C":{},"S-C":{}},
 "guards":{"D3_fault_share":0.004,"D4_format":{"S'":2,"S":1,"ok":true},"D5":{"infra":{"S'":0.0},"reasoning":0,"unanswered":0,
   "balance":true},"D6_dup":{"p_two_sided":0.61},"D7_meta":null},
 "placebo_rule":"informative|harmful_sham_stricter_D1|helpful_sham_reported","second_call_rates":{"S'":0.31,"P_y":0.29},
 "twins":{"p-...":{"n":20,"tau":0.05,"ci95":[-0.1,0.2]}},"decision":"accept|reject|undetermined","reason":"..."}
```

### 2.7 Consumption record (`/data/execskill-history/consumption/<bench>.jsonl`)
`{"version":"fivebench-execskill-v1-consumption","bench","item_id","item_hash","state":"registered|dispatched|decided|routed_not_dispatched",
"purpose":"smoke|run|accept|examiner|detector_holdout","unit","run_root","attempt","ts","record_sha256"}` (one line per state change; the
reader folds lines; states only move forward; another unit touching a non-released item → `ConsumptionConflict`).

### 2.8 Cell record (copied cells + new keys)
v3 keys (cells.py:221-230) + `package_sha256, arm_kind ∈ {candidate, parent, card, placebo_y, placebo_i, withhold:<id>, gen:<set>}, enabled,
withheld, faults{kind: n}, deciding_receipt, delivery (worst receipt), judge, evidence, shared_with (cell id when structural-zero shared)`.

### 2.9 Manifest (`fivebench-execskill-v1-manifest`)
`{version, root, history_root, slot_root, data{supply files + sha, items files + sha, split pins}, sheet_qualification{imported record sha,
engine sha, reverified_at}, cards{bench: sha}, contracts{bench: {text, sha}}, templates{name: sha}, lexicon_sha, placebo_corpus_sha,
runtime{bench: {...}}, sandbox{image_id, worker_sha256, policy_sha256, docker_argv_template_sha, limits, measured{vsz, rss, view_bytes_p99}},
clients{solver{backend: "elucid", model, url_host, env_path, proxy, reasoning_effort: "none", M, B, branch: "E|N", read_timeout, slots,
response_model_ids, client_source_sha}, roles{model: "glm-5.3", max_tokens: 16384, read_timeout: 900, reasoning: "low"}}, seeds, sizes,
thresholds, caps, importable_versions, fixtures{sha}, code(pin_code over skillopt/ and scripts/), loaded_code, environment{python,
openpyxl, docker, image digests, in_image_pip_freeze_sha}, provenance, record_hash}`. `verify_code` + zero-call `docker image inspect`
before EVERY unit; mismatch → `chain-terminated.json`.

### 2.10 Test-read record and consent
Consent: `{test_evaluation, sheet_test_qualification, alfworld_test_identity_check, multi_arm_arms, by: "owner", date, note}` (exact set).
Evaluation cell: hashes only (`request_sha256`, `reply_sha256`, token, judge tokens, flags). Owner continuation file
`<root>/shared/owner-continuation.json` `{by: "owner", date, decision: "continue|stop", note}` must exist before `unseal`.

## 3. Hook points in the copied backend paths (`execskill/solver.py`)

Frozen references are to `skillopt/continual_eval/backends.py`. The copy must reproduce frozen requests byte for byte when the
package is empty (equivalence test T-SOLVER-1).

| Path | Frozen location | Route-B hook | Rule |
|---|---|---|---|
| QA system prompt | :379-394 (base + contract + "Frozen skill guidance (use only where applicable):" + skill_text) | none | skill_text = active bench card only (REG §2.2); identical bytes in S', S, C, P |
| QA user | :417 `json.dumps(view)` | `before_call`, `bindings` → `view["procedure_notes"]` as LAST key | rendered by `notes.render` with fixed headers; absent when empty (keeps equivalence) |
| QA first call | `_response(call, system, user)` :90-113 | — | Recorder per call; truncated → no second call |
| QA post-call | after :417-424, before extraction :425-436 | `<calc>` round trip (REG §2.4) | at most one second call; user = first user + `first_reply`, `computed`, `instruction`; final = second if delivered and not truncated, else first |
| Sheet view | :397-409 | `before_call`; workbook passed to the sandbox as a read-only mounted file `/input/input.xlsx` (never inlined) | — |
| Sheet after extraction | around per-case `_native` loop :433-452 | `precheck` once on the public input → `sheet_feedback` → optional ONE repair call | precheck in a one-shot container with frozen argv/env; native slot only around each container run; final program = repair program if delivered |
| ALFWorld routing | before the loop | `applies` on `{initial_observation, admissible_commands_at_reset, task_text}` from the items file; sha256 asserted against the live reset view | — |
| ALFWorld pre-call | view construction :744-746 | `alf_before_step` → notes (≤ 1,500 chars/step) + discouraged list rendered as `NOT_RECOMMENDED_PREFIX + ", ".join(cmds)`; shown admissible list UNCHANGED | — |
| ALFWorld action | parse :752-756 | `canonical.canonical` (level 1) | `how` logged; empty or > 1000 chars → `invalid_action_format` (frozen rule) |
| ALFWorld post-step | after `env.step` :762-764 | `alf_after_step(event, state)` | state ≤ declared bytes; host keeps state |
| ALFWorld catch-all | `except Exception` :774-776 | re-raise `SandboxUnavailable, CleanupUnconfirmed, BudgetStop, AssumptionBroken, LedgerFailure, ConfigurationError, ConsumptionConflict` BEFORE the catch-all | unit test T-SOLVER-6 |

Prediction shape = frozen shape + `shell` key: `{route, calls[{purpose, request_sha256, receipt_index}], procedure_events, faults,
notes_chars, deciding_receipt, fallback, precheck, compute}`. The shell has NO function that writes or edits the delivered reply.

Placebo arms (`placebo=`): same predicates and hooks; content from `placebo.sham_*`; second calls by the same trigger rule (compute:
the solver's own `<calc>` tag; repair: `placebo.shadow` runs S' procedures on the placebo's own trajectory to decide `request_repair`,
the shadow result is never shown). Twin arms (`withhold=`): the withheld procedure's predicate still runs and is logged
`shadow_fired`.

## 4. Sandbox design (`execskill/sandbox/`)

- **Boundary**: the container. Image `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd` only, `--pull=never`.
- **argv template** (copied from `backends._native` :169-178 and extended): `docker run -i --pull=never --name
  execskill-sbx-<uuid4> --network=none --read-only --user=65534:65534 --cap-drop=ALL --security-opt=no-new-privileges=true
  --pids-limit=<P> --memory=<M>m --memory-swap=<M>m --cpus=<C> --ipc=private --shm-size=16m --no-healthcheck --log-driver=none
  --ulimit=nofile=64:64 --ulimit=core=0:0 --env PYTHONHASHSEED=<0|1> --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1
  --env MKL_NUM_THREADS=1 --env EXECSKILL_SANDBOX=execskill-worker-v1 --mount type=bind,source=<runner dir>,target=/runner,readonly
  [--mount type=bind,source=<cell input dir>,target=/input,readonly] --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m
  --workdir=/tmp --entrypoint=python <image> -s -B -P /runner/worker.py`. The docker CLI subprocess gets `env={"PATH": "/usr/bin:/bin"}`.
  Limits P/M/C registered after S0 measurement (start values P=64, M=768, C=0.5 for cell/episode workers; generator worker M=1024, C=1).
- **Framing**: `docker run -i` gives the worker only stdin/stdout, so the frame channel is the container's stdin (requests) and stdout
  (responses), length-prefixed `<8-byte big-endian length><canonical JSON>`. At start the worker `os.dup`s fd 1 into a private
  binary channel and points `sys.stdout`/fd 1 at fd 2 (stderr, which the host discards with `stderr=DEVNULL`); every CHILD then
  dup2s /dev/null onto 0/1/2, so nothing a procedure prints, and no library that writes to /dev/stdout, can reach the frame stream. Frame cap: registered from S0 (`max(1 MiB, 4 × p100 view bytes)`), never
  carries workbook bytes. Each response echoes `seq`, `proc`, `fn`, `args_sha256`.
- **Ops**: `load {package_sha256, procedures[{id, source, hooks}], policy_sha256}` → `{loaded, rejected[{id, reason}]}` (policy and
  syntax checked again inside); `call {seq, proc, fn, args}` → `{seq, ok, value, value_sha256, cpu_ms}` or `{seq, ok: false, fault,
  exc_type, message≤500, line}`; `ping` → `{worker_sha256, hashseed, python, sympy, pandas, numpy, openpyxl}`; ready handshake =
  first `ping` after start, within 20 s.
- **Per call**: parent `os.fork()`; child: dup2(/dev/null → 0,1,2), `setrlimit(RLIMIT_CPU, cpu_s)`, `RLIMIT_AS` (from S0), `RLIMIT_FSIZE 0`,
  `RLIMIT_NOFILE 32`, write `1000` to `/proc/self/oom_score_adj`, exec the procedure function from a fresh namespace built from the
  loaded source text (no module state survives), serialize (`allow_nan=False`, depth ≤ 32, size caps), write to a child-private pipe,
  `os._exit(0)`. Parent: wall timeout (predicate 2 s, hooks 5 s, detectors 5 s, generators 60 s) → `SIGKILL` → fault `timeout`;
  any non-zero exit, signal, missing/invalid frame → fault of that call.
- **Host client error mapping**: worker death, EOF, frame corruption, seq mismatch → restart the container once WITHOUT the faulting
  procedure, record P1 for the in-flight call, continue; restart failure, image missing, docker error → `SandboxUnavailable` (P4);
  `docker rm --force` bounded 10 s + `docker ps -a --filter name=execskill-sbx-` empty, else `CleanupUnconfirmed`.
- **Lifetime**: lazily started on the first call of a cell (QA/Sheet) or an episode (ALFWorld); ALFWorld card-arm episodes start an
  empty-package worker so every arm takes the same slot path (REG §6.2). Workers for engineer checks: two containers with
  PYTHONHASHSEED 0 and 1.
- **Slots and lock order**: `alfworld-episode` (6) → `execskill-sandbox` (per call; 4 on 7 CPUs, registered after S0) → model pool
  (frozen Endpoint; elucid 8, glm-5.3 10) → `spreadsheet-native` (3). Every route-B wait has a timeout (sandbox 600 s, native 1,800 s,
  episode 3,600 s) → P4.
- **Escape probe** (S0, fixed registrar code in the same container argv): no network (`socket.connect(("1.1.1.1", 53))` fails), `/` and
  `/runner` read-only, uid 65534, env keys == registered list, no `*.env`, `*key*`, `consent*`, `ledger*` under `/`, pids/memory limits
  bite, child cannot write files (FSIZE).

## 5. Concurrency, ledger and recovery wiring

- One `budget.Budget` at `<root>/shared/ledger` (imported unchanged). One Endpoint per unit attempt per role (halt generation,
  calls.py:145). Solver Endpoint constructed with `max_tokens = B`; `ElucidClient` sends nominal `M`. Scopes via `budgets.py`;
  examiner-triggered solver cells (band, shortcut, G_acc) are charged to `…:examiner`, self-test to `…:selftest`, acceptance to
  `…:accept:attempt-N`, test reads to `deepseek:xs:test`.
- Threads: 16 per unit. QA/Sheet acceptance in blocks (SearchQA 4, OfficeQA 2 time-separated ≥ 2 h, ALFWorld 4); SpreadsheetBench and
  ALFWorld never run concurrently (memory on 15 GiB).
- Recovery: copied `units.run_unit` attempt-N; owner `recovery.json`; a redo re-dispatches the whole block with the SAME sealed inputs
  and the same registry entries; ≤ 2 redos; no splicing across attempts (owner decision #15 may change this).

## 6. CLI `scripts/run_execskill.py` (subcommands)

`probe` (S1) · `sandbox-selftest` (S0 sandbox suite + escape probe + measurements) · `import-texts` (accepts exactly
`fivebench-coevolution-v3-texts-import`) · `import-sheet-qualification` (+ zero-call reverify) · `make-items --bench alfworld|searchqa`
· `exclude-tests` (TestAccess; counts + exclusion hash only) · `make-fixtures` · `smoke-make` / `smoke --stage S0|S1|S2|SN1|S3|S4` /
`smoke-summary` · `make-manifest` · `consent` (writes nothing itself; validates the owner's file) · `run --manifest M --chain C`
· `step-unit` / `evaluate-unit` (children) · `replay --package P --trajectories DIR` (zero tokens) · `show-package` · `monitor`
(counts, never scores) · `recover` · `terminate` · `resume-ledger` · `continuation-check` · `report`. Every launch script: `unset
OPENAI_API_KEY OPENAI_BASE_URL`, `export PYTHONDONTWRITEBYTECODE=1`, runs `python -B` from the verified snapshot.

## 7. Fixtures and fake backends (zero-API tests): `tests/execskill_fakes.py`

- `FakeSolver(script)`: deterministic replies keyed by `(bench, request_sha256)` or by regex on the user JSON; can emit: tagged answer,
  JSON answer, `<calc>` tags, truncated reply (`finish_reason="length"`), over-nominal usage, reasoning tokens > 0, reasoning_content,
  undelivered errors; produces receipts in the frozen Client shape (port of `tests/coevo5_fakes.py`).
- `FakeGLM(script)`: engineer/examiner/describer/leakage replies (valid, invalid JSON, fenced code, policy-violating code).
- `FakeDocker`: implements the sandbox argv contract by running `worker.py` in a local subprocess with the same framing (for CI on a
  machine without docker; the REAL container is exercised in S0 on dl). Can inject: container start failure, cleanup failure, worker
  SIGKILL, frame corruption.
- `FakeAlfEnv(games)`: scripted text environment with admissible commands, `won` signal, `infos.extra.expert_plan/gamefile` present (to
  test stripping); rooms and task types.
- `FakeNative`: SpreadsheetBench program execution returning scripted run reports.
- Fixture items: 20 per bench shaped like real public views (OfficeQA table-text pages with arithmetic answers; LiveMath five-option items
  with symbolic truth; SpreadsheetBench workbooks incl. one at the measured p99 size; SearchQA short QA; ALFWorld 12 fake games); fixture
  procedures `fx-note`, `fx-bindings`, `fx-sheet-repair`, `fx-alf-tracker` (D3 hand-tracker port + revisit discouragement), `fx-crash`,
  `fx-print`, `fx-oom`, `fx-loop`, `fx-module-loop`, `fx-nested-state`, `fx-nondeterministic` (set order), `fx-lexicon` (emits "answer only
  with the number"), `fx-meta` (references the LiveMath meta option), `fx-literal` ("drawer 3").

## 8. Test plan

### 8.1 Unit tests (one file per module, `tests/test_execskill_<module>.py`)

| Test id | Module | Asserts |
|---|---|---|
| T-ID-1 | errors/cells | `BudgetStop` in a copied cell → stop kind `budget`; route-B stops map to `sandbox/package/consumption` |
| T-ID-2 | all | every record version starts with `fivebench-execskill-v1`; no record stamped `fivebench-coevolution-v3` |
| T-CLIENT-1..5 | client | reasoning_tokens>0 or reasoning_content → `thinking_mismatch` + subtype; resend path taken by the frozen Recorder; `over_nominal` flag; echoed model mismatch refused; body has `reasoning_effort:"none"`, no `thinking`; proxy must equal GATEWAY |
| T-LEDGER-1..3 | budgets | Endpoint reserves with B; completion in (M, B] → no halt; completion > B → `AssumptionBroken`; scopes rooted |
| T-PKG-1..4 | package | canonical sha stable; caps; withhold/with_ produce new shas; narrowed benches respected by router |
| T-POLICY-1..6 | policy | each forbidden name/attribute rejected; module-level statements rejected; meta-option/bulletin/receptacle literals rejected; allowed imports pass |
| T-SBX-1..12 | sandbox | load/call/ping; timeout, memory, NaN, over-cap, nesting, print, module loop, SIGKILL of child and of worker → P1 not P4; restart without faulting proc; image missing → `SandboxUnavailable`; cleanup failure → `CleanupUnconfirmed`; fresh namespace per call (state cannot leak); two hash seeds give equal hashes for deterministic code and differ for `fx-nondeterministic` |
| T-COMP-1..5 | compute | grammar, names, magnitude guard on `(((9**99)**99)**99)` style input, depth, "not evaluated" on failure |
| T-NOTES-1..3 | notes | rendering fixed headers; lexicon drops count as faults; SB exempts "format" |
| T-ROUTE-1..4 | router | deterministic; predicate fault → not enabled; A\* computed from public views only; ALFWorld routing view sha asserted |
| T-SOLVER-1 | solver | **empty package ≡ frozen `backends.solve`** request hashes and predictions on fixtures of all five benches |
| T-SOLVER-2..8 | solver | notes last key; compute round trip ≤ 1 extra call; truncated first reply → no second call; second-call fallback; Sheet precheck uses frozen argv/env; native slot never held during a model call (3 slots / 12 workers, no deadlock); ALFWorld catch-all re-raises route-B stops; `delivered_reply == model_reply` for QA; discouraged commands never removed from the shown list; expert_plan/gamefile never in any view, note, trace |
| T-CANON-1..3 | canonical | level-1 rules; NO earliest-admissible search (a reply rejecting "go to drawer 1" then mentioning it is NOT mapped) |
| T-PLACEBO-1..5 | placebo | yoke pairing deterministic; length band; header kept; compute sham echoes + "not evaluated"; repair sham keeps program + error; shadow triggers equal S' triggers on the same trajectory |
| T-JUDGE-1..4 | judge | v2 ≥ official on all fixtures and on archived v3/cal-1 TRAINING cells (S0); JSON extraction cases; completion-aware failures |
| T-OUT-1..3 | outcomes_ext | rows P1–P7; `unknown_fault` excluded from infrastructure share; delivery = worst receipt |
| T-STATS-1..5 | stats_ext | sign-flip p on a null permutation is uniform (simulation); stratified/clustered flips; IUT; Holm; L/H with `unknown_fault` |
| T-CELLS-1..3 | cells | `_replay` replays ordered sends (two-call cell under REEXECUTE does not pause); stored precheck read back; structural-zero sharing links `shared_with` |
| T-REG-1..5 | registry | states forward only; conflict across units; redo reuses own registration; release returns items; root-independence |
| T-SUPPLY-1..4 | supply | SearchQA tail builder never emits positions < 4,001 and checks A–D hashes; ALFWorld room grouping disjoint across run/accept/select; slices consecutive; smoke items removed first |
| T-REPLAY-1..4 | replay | fixed property kinds only; non-vacuity (property false when withheld); negative tests; reference-tracker agreement computed |
| T-DET-1..3 | detectors | masked views hide answer content/run status/step count; residual metrics; Jaccard dedup; a `len(steps)==50` detector is not accepted |
| T-GEN-1..4 | generators | OfficeQA reproduction-of-original gate; LiveMath single matching option, no meta option, key balance; Sheet recalc + qualify (with FakeNative); ALFWorld null selector |
| T-VAL-1..2 | validity | < 8 informative pairs → `not_evaluable`; slope test with negative controls |
| T-ACC-1..4 | acceptance | sealed inputs immutable; D1–D7 on synthetic cell tables; harmful-sham rule; |A\*| < 15 → not run and nothing consumed |
| T-EVAL-1..3 | evaluation | consent key set exact; multi-arm unit; `unseal` refuses without `owner-continuation.json` |
| T-MAN-1..2 | manifest | verify_code refuses a changed file; environment fields present |

### 8.2 End-to-end zero-API chain test (`tests/test_execskill_e2e.py`)

A two-bench pilot (SpreadsheetBench fixtures → ALFWorld fake games, and SB → OQ fixtures) on a temporary root with FakeSolver, FakeGLM,
FakeDocker, FakeAlfEnv, FakeNative: run → diagnose → generate → engineer (one valid change, one leaking change dropped, one crashing change
dropped) → selftest → accept (A\*, P_y, P_i, twins, G_acc) → decision → freeze (describer) → multi-arm test read with structural-zero
sharing → sealed → owner continuation file → unseal → readout tables. Assertions: every record versioned; registry states; ledger
reservations == settlements; no test text in any training-side artifact; the decision is reproducible from cell records alone (re-run
`decide` → identical JSON).

### 8.3 Break-the-code checks (must FAIL loudly when the code is sabotaged)

Run as a separate job (`tests/test_execskill_mutations.py`): each mutation is applied to a temp copy and the named test must fail —
(1) shell appends text to the delivered reply → T-SOLVER-2; (2) router reads `private` → T-ROUTE-3; (3) placebo forgets the header → T-PLACEBO-3;
(4) registry allows re-dispatch → T-REG-2; (5) `_replay` replays only the last send → T-CELLS-1; (6) Endpoint built with M instead of B → T-LEDGER-2;
(7) canonicaliser searches the whole reply → T-CANON-2; (8) detector view includes step count → T-DET-1; (9) v2 can turn a pass into a fail → T-JUDGE-1;
(10) consent accepts extra keys → T-EVAL-1; (11) worker child keeps stdout → T-SBX (print); (12) ALFWorld view keeps `infos.extra` → T-SOLVER-8.

## 9. Build order: 5 batches, parallel agents own DISJOINT files

Each batch ends with its unit tests green on the Mac (offline) and ONE Codex review round per batch (memory: stepwise Codex review,
one round per item). File ownership is exclusive inside a batch; later batches may import earlier modules but never edit them (a needed
change goes back to the owner of that file as a fix ticket).

| Batch | Agent | Owns (files) | Depends on | Done when |
|---|---|---|---|---|
| B1 foundations | A1 | `protocol.py`, `errors.py`, `budgets.py`, `slots.py`, `__init__.py`, `tests/test_execskill_protocol.py`, `tests/test_execskill_budgets.py` | frozen coevo5 | T-ID-1, T-LEDGER-*, slot timeout/order tests |
| | A2 | `client.py`, `tests/test_execskill_client.py`, `tests/execskill_fakes.py` (FakeSolver, FakeGLM parts) | — | T-CLIENT-* |
| | A3 | `package.py`, `policy.py` (also generates `sandbox/policy.json`), `notes.py`, `compute.py`, `canonical.py`, their tests | — | T-PKG, T-POLICY, T-NOTES, T-COMP, T-CANON |
| | A4 | `registry.py`, `supply.py`, `exclusion.py`, their tests, fixture item builders `tests/fixtures/execskill/*` | — | T-REG, T-SUPPLY (exclusion tested with a fake TestAccess) |
| B2 sandbox + shell | A5 | `sandbox/worker.py`, `sandbox/client.py`, `sandbox/__init__.py`, FakeDocker in `tests/execskill_fakes_docker.py`, `tests/test_execskill_sandbox.py` | B1 (policy, slots, errors) | T-SBX-* with FakeDocker |
| | A6 | `solver.py`, `router.py`, `precheck.py`, `precheck_worker.py`, `tests/test_execskill_solver.py`, `tests/test_execskill_router.py`, FakeAlfEnv/FakeNative in `tests/execskill_fakes_env.py` | B1; sandbox client interface (stub until A5 lands) | T-SOLVER-1 (equivalence) first, then T-SOLVER-2..8, T-ROUTE |
| | A7 | `judge.py`, `outcomes_ext.py`, `stats_ext.py`, their tests | B1 | T-JUDGE, T-OUT, T-STATS |
| B3 cells, units, rounds | A8 | `cells.py`, `units.py`, `rounds.py`, `trajectories.py`, their tests | B1, B2 | T-CELLS, guard/balance tests |
| | A9 | `placebo.py`, `acceptance.py`, `validity.py`, their tests | B1, B2 (router), A7 | T-PLACEBO, T-ACC, T-VAL |
| B4 method roles + examiner | A10 | `engineer.py`, `replay.py`, `describer.py`, their tests | B2, B3 | C1–C10 pipeline on fixtures; T-REPLAY |
| | A11 | `detectors.py`, `examiner.py`, `generators/*`, their tests | B2, B3 | T-DET, T-GEN |
| B5 orchestration + ops | A12 | `step.py`, `chain.py`, `evaluation.py`, `qualify.py`, `readout.py`, their tests, `tests/test_execskill_e2e.py` | B1–B4 | e2e chain test green |
| | A13 | `manifest.py`, `prelaunch.py`, `smoke.py`, `scripts/run_execskill.py`, `tests/test_execskill_manifest.py`, `tests/test_execskill_mutations.py`, ops scripts under `/data/execskill-20261021-ops` (written on dl only at launch time) | B1–B4 | T-MAN, mutation suite, `smoke-make` dry run with fakes |

Integration gates between batches: (i) after B2, T-SOLVER-1 equivalence must pass against the frozen `backends.solve` on all five benches;
(ii) after B3, a fake acceptance round reproduces its decision from cell records; (iii) after B5, the e2e test and the mutation suite pass
on a clean clone (memory: GitHub publish convention — clean-clone tests first). Docs: update `docs/current-workflow.md`,
`docs/results-and-lessons.md` (pending results only, no claims), and `docs/project-status.md` per AGENTS.md when the code lands.

## 10. Smoke specification for dl (operational)

Pre-conditions: owner decisions #1–#10 of REG §14 answered (defaults otherwise); leftover D3/D14 workers handled (#3); branch
`research/exec-skill-coevolution` committed locally (owner approval for any push).

1. **Snapshot.** On the Mac: sha256 list of `skillopt/ scripts/ tests/` → rsync to `dl:/data/execskill-20261021-source` → recompute on dl and
   `cmp` (map §1 ops pattern). Never edit the snapshot afterwards.
2. **Connectivity** (AGENTS.md): `ssh -O check` on the configured alias, then non-interactive `bash -ic 'proxy_on && …'` only where external
   access is needed; the solver client uses the explicit PJLAB gateway with `trust_env=False`; never print `.env`; `unset OPENAI_API_KEY
   OPENAI_BASE_URL` in every run script.
3. **S0 (zero calls)** in tmux `execskill-prep`: `python -B scripts/run_execskill.py sandbox-selftest`, pytest on the snapshot
   (`-p no:cacheprovider`), `import-texts`, `import-sheet-qualification`, `make-items --bench alfworld`, `make-items --bench searchqa --dry-run`
   (counts only), `exclude-tests` (TestAccess, counts + exclusion hash), `make-fixtures`, `smoke-make --root /data/execskill-20261021-pre`.
   Record measured view sizes, VSZ/RSS, container start latency; write the registered limits into the smoke manifest BEFORE S1.
4. **S1 probe** (≤ 60 calls, `/data/execskill-20261021-pre/ledger`, cap 0.5M): first single call confirmed before any concurrency; then
   S1-a…f (REG §10). Branch E/N for B is decided here and written into the manifest; no later change.
5. **S2 solver smoke** (tmux `execskill-smoke`, background on dl; sparse event-driven monitoring): arms C, X, P, twins on SearchQA 20,
   ALFWorld 6, fixtures OQ/LM/SB 20 each, 2 runs; the pass criteria of REG §10 are computed by `smoke-summary` (counts, never scores of
   real items beyond the format share).
6. **S-N1 noise** (SearchQA 200 × two identical C arms × 1; ALFWorld 6 × 2), **S-E6 cost** — results replace REG §3.3/§9.1 assumptions
   via a written pre-pilot amendment if they move by > 25%.
7. **S3 roles** (GLM ≤ 0.5M) and **S4 mini-step + resume drill** (inject `SandboxUnavailable` via a registered fault switch available only in
   the smoke root; owner-format `recovery.json` written by the operator as a drill, labelled `smoke`).
8. **Exit**: `smoke-summary` writes `smoke-result.json` (pass/fail per row); any fail → no pilot; amend to `fivebench-execskill-v1.1` with new
   directories and re-run the failed rows. On pass: `make-manifest` for `/data/execskill-20261021-pilot`, owner consent file, owner go.

Estimated smoke cost (estimates): S1 ≤ 0.2M; S2 ≈ 1.0–2.5M (C/X/P × 2 runs, ALFWorld 6 × 3 arms × 2 × 36–45k ≈ 1.3–1.6M of it); S-N1 ≈
1.0–2.0M; S4 ≈ 0.5M; total within the 5M smoke cap; GLM ≤ 0.5M of the 2M cap.

## 11. Open items the implementers must not decide alone

- Final sandbox limits (P, M, C, RLIMIT_AS, frame cap) come from S0 measurement and are written into the manifest before S1 (REG §2.6).
- Branch E/N for B (REG §4.1) is an S1 output; if N and any completion > B was seen in S1/S2, stop and ask the owner.
- The fixed reference tracker for ALFWorld (port of D3's hand tracker) is registrar code: its agreement threshold (≥ 97%) is registered, but
  its own correctness vs simulator facts was measured only on D3's traces (7,350/7,524 agreement for the learned tracker [FP F1, F6-F9]);
  any disagreement pattern found in S0 goes to the owner before the pilot.
- Lexicon contents per bench (REG §2.2) are registered at implementation time and frozen by sha before S2; changes after S2 need v1.1.
- Pilot order (owner #1) changes only which benches' slices are cut first; code must support both default and recommended pilots without edits.
