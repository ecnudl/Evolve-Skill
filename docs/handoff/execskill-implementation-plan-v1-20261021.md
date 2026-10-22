# fivebench-execskill-v1 — implementation plan v1 (for implementers)

**Build location: Linux dev machine dl, build tree `/data/execskill-dev` (git clone at `010d453`, branch
`research/exec-skill-coevolution`); unit tests run there with
`/root/continual-alf-prep-20260928/env/bin/python -B -m pytest -p no:cacheprovider`; the Mac holds a pulled mirror for Codex
review and publication only.**

Status: 2026-10-21, v1, written before any code; revised after the final consistency check (check.md: C1–C18, O1–O13; this plan
carries check items C1, C2, C3, C4, C9, C10, C12, C13, O1, O3, O4, O7–O10, O12; "check Cn" below refers to these items, never to the engineer checks C1–C9);
revised again (22:xx) after the ONE Codex review round (findings F1–F24, REG §20; "Codex Fn" below): every interface change of that round is
carried in the module rows (§1), data shapes (§2), hook table (§3), sandbox (§4), wiring (§5), fixtures (§7), tests (§8) and build rows (§9);
a later read-only verifier pass (not a new review round) found propagation gaps, fixed in the same round (smoke receipt classes, frozen
preflight line ranges, `tag_exact` episodes, calc T8 figures, the owner-#9 P_i cap; REG §19). Version strings are unchanged. Companion of `execskill-registration-v1-20261021.md` (same
directory; "REG §n" below). The registration decides WHAT is measured and the thresholds; this plan decides HOW it is built. Where
they disagree, the registration wins and the plan is a bug. Line references to frozen code were taken from the local repo
(`/Users/dulin/Documents/Paper/SkillOpt`), which is byte-identical to the dl snapshot f (`dl:/data/coevo5-20261019-v3-source-f`)
for `skillopt/`, `scripts/` [CI F3]; they are valid for `/data/execskill-dev` at `010d453`.

**Owner rules 2026-10-21 22:3x (binding; REG §0 "负责人 22:3x 的定调", REG §21).** (a) Every REG §14 decision is taken at its default: the
pilot is SB → OQ; leftover D3/D14 workers are left alone (the leftover check records "cannot judge"). (b) The tenet is fixed: co-evolution in
which the examiner evolves through RESEARCH — every generation path has a mandatory research step that reuses v3's frozen research machinery
(new module `research.py`, owned by A11 in B4; tests T-RES-1..3); research supplies material and parameter choices for the registrar-defined
families, truth stays fixed code (Codex F8). (c) The smoke stays elucid-only; formal runs use TWO parallel chains with separate ledger scopes,
caps and consumption namespaces: chain G (solver GLM-5.3 through the frozen BigModel route, `weak_solver_probe.MODELS["glm-5.3"]`, no route)
and chain D (solver deepseek-v4.1-flash-1017 through elucid); method roles are GLM-5.3 in both. Carried in §1 (protocol, client, budgets,
registry, generators, examiner, research rows), §2.7, §5, §7, §8, §9, §10, §11.

Hard rules for every implementer:
- Never edit a frozen file (`skillopt/coevo5/*`, `skillopt/continual_eval/*`, `scripts/run_coevo5.py`, `scripts/weak_solver_probe.py`,
  any scorer, any v3 artifact). Import or copy (REG §1).
- No paid call, no `.env` print, no test-pool path in any test or fixture. All tests run offline with fakes (§7), on dl in
  `/data/execskill-dev`.
- Edit only in `/data/execskill-dev` on dl (over ssh). Never edit in, or rsync from, `/data/skillopt-work` (not a git repo; holds a
  `.env`).
- Every new record carries `version = "fivebench-execskill-v1-<kind>"` and `evidence` (REG §1).
- Write-once artifacts use the frozen `validator_pilot.api.write_json`/`digest` semantics (canonical JSON:
  `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`).
- Model-written code is executed ONLY through `execskill.sandbox.client` (§4). No `exec`/`eval` of model text on the host, ever.

## 1. Package layout `skillopt/execskill/` (one line per module)

Legend: **imp** = imported unchanged; **copy(p)** = copied from the named frozen function with parameter changes p; **new** = new code.

| Module | Purpose | Main API (signatures) | Reuse |
|---|---|---|---|
| `__init__.py` | package marker; `VERSION = "fivebench-execskill-v1"` | — | new |
| `protocol.py` | all registered constants: VERSION, ORDER, seeds/tags (incl. `execskill-v1:yoke:<unit>` donor pairing, `execskill-v1:discourage:<unit>:<cell>`), sizes (REG §3.3; G_acc = one generated item per A\* item: SB ≤ 60, OQ ≤ 50, LM ≤ 100 in the formal chain, ALFWorld and SearchQA 0; G_acc arms S', S, P_y, C (+ S_dup); test read = 1 run per test item), decision minimum `MIN_ASTAR = 30`, `MIN_ASTAR_ROOMS = 20` (Codex F1), maximum schedule (Codex F18: `MAX_CHANGES = 3`, `MAX_TWINS_PER_ITEM = 2` acceptance and test read, `BAND_ROUNDS = 3`, `SELFTEST_PASSES = 2`, `PREFUNDED_REDOS = 1`), thresholds (REG §6.4 incl. J3/J4 formulas, §7 incl. detector Holm family 10% and `MIN_ROOMS_PER_HALF = 8`, validity `MIN_ROUNDS = 8`), caps (REG §9.3; each scope = 1.5 × its maximum-schedule high estimate + one full next reservation, `docs/handoff/execskill-calc-20261021.py` T6/T7: SB run 1.2 / examiner incl. G_acc 3.5 / selftest 2.6 / accept 8.3M; OQ 2.3 / 7.3 / 6.6 / 29.5M; ALF 13.2 / 9.9 / 19.1 / 91.3M; test read 99M default / 126M recommended; redo reserve 14.8 / 22.9M; pilot solver cap 180M default / 300M recommended (if owner #9 adds P_i on ALFWorld: ALF accept 107.5M, recommended pilot 320M, calc T6); smoke solver 14M; S1 probe root 0.5M with B_probe = 32,768), M/B per bench, timeouts, slots, lexicons, templates (COMPUTE_INVITE, COMPUTE_FOLLOWUP, NOTE_HEADERS, NOT_RECOMMENDED_PREFIX, REPAIR_FRAME), placebo corpus pointer, registered test canaries pointer (hash fragments only, Codex F16); owner rules 22:3x (REG §0, §21): `SOLVERS = ("glm-5.3", "deepseek-v4.1-flash-1017")`, `CHAINS = {"G": "glm-5.3", "D": "deepseek-v4.1-flash-1017"}`, `SLOTS = {"glm-5.3": 10 (coevo5 protocol.py:331; shared by chain G's solver cells and BOTH chains' role calls), "deepseek-v4.1-flash-1017": 8, "spreadsheet-native": 3, "alfworld-episode": 6}`, per-solver settings (G: M = B = 65,536 on every bench, read timeout 2,400 s, coevo5 protocol.py:327, :92, thinking per the frozen MODELS entry; D: REG §4.1), per-chain caps = the registered caps for EACH chain (default pilot totals 360M solver / 60M GLM roles, calc T11), research constants (`RESEARCH_*` transcribed by value from coevo5 protocol.py:254-257; `MAX_RESEARCH_REQUESTS = 24` per step and bench, `MAX_ITEMS_PER_FINDING = 10`, research sub-scope cap 4.6M per step and bench, calc T11; seed tag `execskill-v1:research-split:<unit>`), consumption namespaces `G`, `D`, `smoke` | constants only; `kind(name) -> "fivebench-execskill-v1-" + name` | new (values transcribed from REG; PLACEBO texts imported from `coevo5.protocol` by value and re-hashed) |
| `errors.py` | route-B stop classes | `class SandboxUnavailable(RuntimeError)`, `PackageInvalid(ValueError)`, `ConsumptionConflict(RuntimeError)`; `STOP_KINDS` = coevo5 cells.STOP_KINDS ∪ {sandbox, package, consumption} | new; re-exports `BudgetStop, AssumptionBroken, LedgerFailure, ConfigurationError, CleanupUnconfirmed` from **imp** `coevo5.outcomes` (ONE exception set) |
| `client.py` | solver clients: elucid + the solver factory (owner rule 22:3x (c)) | `solver_client(model, *, config) -> client`: `"glm-5.3"` → the frozen `weak_solver_probe.Client(repo, "glm-5.3", proxy=GATEWAY, max_tokens=65536, read_timeout=2400)` with NO `route` (MODELS entry weak_solver_probe.py:76-77: backend bigmodel, thinking enabled, effort low, echo `glm-5.3`; credentials by path, :140-146), built exactly as the v3 factory builds it (coevo5/manifest.py:96-112); `"deepseek-v4.1-flash-1017"` → `ElucidClient`; any other model → `ConfigurationError`; `class ElucidClient(weak_solver_probe.Client)`: `__init__(self, env_path, *, proxy, max_tokens, read_timeout, transport=None)` (does NOT call `super().__init__`, which rejects models outside MODELS, weak_solver_probe.py:228-233); `_receipt(self, status, data, attempts, started) -> dict` (calls super, then reads `usage.completion_tokens_details.reasoning_tokens` and `message.reasoning_content`; reasoning → `ok=False, error_type="thinking_mismatch", subtype="reasoning_mismatch"`; adds `visible_completion_tokens`, `over_nominal`); request body adds `"reasoning_effort": "none"`, no `thinking` field | **imp** `weak_solver_probe._read_env, _validated_url, GATEWAY, Client.call`; **imp** `weak_solver_probe.Client` itself, unchanged, for glm-5.3 |
| `budgets.py` | ledger scope helpers | `solver_scopes(chain, bench, k, kind, attempt=None) -> tuple`, `glm_scopes(chain, role, bench, k) -> tuple` (chain ∈ {G, D}: every scope is prefixed by its chain and each chain has its own caps, owner rule 22:3x; role `examiner_research` = the `…:examiner:research` sub-scope, 4.6M per step and bench, calc T11); kinds ∈ {run, examiner, selftest, accept, test, smoke, probe} (`probe` lives on the S1 probe's own ledger root); `endpoint(setting, scopes, *, client, max_tokens_bound) -> calls.Endpoint` | **imp** `coevo5.budget.Budget, rooted`; **imp** `calls.Endpoint` constructed with `max_tokens = B` (REG §4.1) |
| `slots.py` | route-B slot pools, lock order, wait logging | `class OrderedSlots(calls.Slots)`: `hold(self, *, log_every_s=300) -> ContextManager` = the frozen untimed wait plus a wait-log line every 300 s (pools `alfworld-episode`, `execskill-sandbox-live`, `spreadsheet-native`; a slot wait NEVER maps to P4); `hold_short(self, *, timeout_s=600) -> ContextManager` only for the short-hold per-call `execskill-sandbox` pool (first timeout → logged + one retry; second consecutive timeout → `SandboxUnavailable`, P4, because holds there last seconds); `LOCK_ORDER = ("alfworld-episode", "execskill-sandbox-live", "execskill-sandbox", <model pool>, "spreadsheet-native")`; `assert_order(held, next)`; `LIVE_SANDBOX_CAP = 6` (SpreadsheetBench units ≤ 2) | **copy**(`calls.Slots.hold`: keep the untimed poll, add wait logging, order assertion, the single short-hold timeout); model slots stay in the frozen Endpoint |
| `package.py` | procedure/package objects, canonical JSON, validation, content addressing, edit types | `@dataclass(frozen=True) Procedure`, `Package` (REG §2.1); `load(path) -> Package`; `save(root, package) -> sha`; `validate(package) -> None` (caps, ids, hooks ⊆ HOOKS, module shape, ≤ `MAX_CHANGES` edits per step); `with_(package, add=(), revise=(), remove=(), narrow={}) -> Package`; `edits(parent, candidate) -> [Edit{kind ∈ {new, revision, deletion, narrowing}, old, new}]` (REG §6.1 edit-type table, Codex F6); `withhold(package, ids) -> Package`; `restore(package, parent, ids) -> Package` (restoration twin for deletion/narrowing) | new; **imp** `validator_pilot.api.digest` |
| `policy.py` | static AST/name policy (hygiene + determinism layer, not the boundary) | `check(source, *, bench) -> list[Violation]`; `POLICY` (allowed imports, forbidden names/attributes incl. sympify, parse_expr, pandas eval/query/read_*/to_*, numpy load/save/fromfile/random except default_rng(seed), openpyxl.load_workbook, datetime.now/today, Timestamp.now, print, dunder attributes; module-level: imports, constants ≤ 2,000 chars, defs only); `policy_sha256()`; static bans C4b: LiveMath meta-option fragments, OfficeQA bulletin literals, ALFWorld numbered receptacle literals | new |
| `sandbox/client.py` | host side of the sandbox | `class Worker`: `start(package, *, kind, inputs_dir=None)`, `call(proc_id, fn, args, *, timeout_s) -> Result`, `close()`; `Result = {ok, value, value_sha256, cpu_ms} | {ok: False, fault, exc_type, message, line}`; `docker_command(kind, limits, mounts) -> list[str]`; `cleanup(name) -> None` (forced removal, then verifies that EXACT owned name is absent; raises `CleanupUnconfirmed`; never inspects other workers' containers, Codex F14); `drain_check(prefix="execskill-sbx-") -> None` (prefix-wide absence, called ONCE after the unit's workers have all exited); `with_worker(...)` context manager; lazy start on first call | new; flags **copy**(`backends._native` command list, backends.py:169-178, plus REG §2.6 extras) |
| `sandbox/worker.py` | in-container worker (pinned, mounted read-only at `/runner/worker.py`) | `main()` reads length-prefixed frames on stdin and writes them on a private dup of the original stdout (fd 1 itself is redirected to stderr, see §4); ops `load`, `call`, `ping`; each `call` → `os.fork()`; child: dup2 /dev/null → 0/1/2, `setrlimit(CPU, AS, FSIZE=0, NOFILE)`, `oom_score_adj=1000`, fresh module namespace from the loaded source, run hook, serialize with `json.dumps(sort_keys, allow_nan=False)`, size/nesting caps, write result to its own pipe; parent enforces wall timeout with `SIGKILL`; `ping` returns `{worker_sha256, hashseed, python, libs}`; fixed helpers exposed to procedures: `public_workbook()` (openpyxl on the mounted read-only file, values + formulas), `safe_sympify(text)` (tokenizer whitelist → sympy constructors, no eval) | new; runs inside image `sha256:0a0a5dcb…` |
| `sandbox/policy.json` | serialized POLICY (hashed into the manifest) | — | generated by `policy.py` |
| `compute.py` | fixed exact evaluator for `<calc>` | `parse_tags(reply) -> list[str]` (≤ 8, ≤ 300 chars); `evaluate(expr, bindings) -> {"value": str} | {"value": "not evaluated", "error": cls}`; guards: names ⊆ bindings, |exponent| ≤ 12, depth ≤ 20, bit length ≤ 4,096 (checked BEFORE each op), per-cell watchdog | **copy**(`coevo5.forward._tree/_value/evaluate/literals/rounded`, forward.py:105-221: MAX_EXPONENT 10→12, add names, keep MAX_BITS 4096) |
| `notes.py` | typed note rendering + lexicon screen | `render(fields, *, bench, header) -> str`; `screen(fields, *, bench) -> (kept, dropped)`; FIELD_TYPES = {facts: [str≤200], table: [[str≤40]] ≤ 20×12, candidates: [str≤120], warnings: [str≤200], bindings: [{name, value, quote}]}; `LEXICON[bench]` | new |
| `router.py` | deterministic routing | `route(package, bench, routing_view, worker, *, withhold=frozenset(), restore=frozenset()) -> RouteLog`; `plan(package, parent, bench, views, worker, *, donors) -> FiringPlan` (A\* per edit type and their union: new = new fires, revision = old OR new fires, deletion/narrowing = old fired in S; twin draws with ≤ `MAX_TWINS_PER_ITEM` per item by priority (changed procedures first, then inherited by enable count), withhold vs restoration twins; donor pairs; `MIN_ASTAR`/`MIN_ASTAR_ROOMS` check; zero model calls) | new |
| `solver.py` | the shell: copied QA/Sheet `solve` + ALFWorld loop with hooks | `solve(bench, public, card_text, package, call, *, runtime, worker, withhold=frozenset(), restore=frozenset(), placebo=None, shadow=None, text=None) -> prediction` (prediction = frozen shapes + key `shell`, REG §2.3; `placebo` = sealed donor outputs; `text` = frozen describer texts for the T_F arm, per-hook behaviour of REG §8.1, Codex F20); `_solve_qa`, `_solve_sheet`, `_solve_alfworld` | **copy**(`backends.solve` :364-455, `_solve_alfworld` :715-783: hooks of §3; native slot only around `_native`; ALFWorld catch-all re-raises route-B stops); **imp** helpers `_public_view, _response, _sheet_preview, _xlsx_bytes, _runtime_limits, _new_alfworld, _AlfSession, _alf_post_observation, _completed_without_text, _prediction_unknown, _layout_supported`, contract constants |
| `canonical.py` | level-1 ALFWorld canonicaliser | `canonical(reply, admissible) -> (action, how)` with `how ∈ {tag_exact, tag_level1, whole_exact, whole_level1, unchanged}`; NO earliest-admissible search | new (do NOT port D3 `parse` lines 178-195) |
| `precheck.py` | SpreadsheetBench public-input pre-check | `precheck(program, task, runtime) -> RunReport{status, exc_type, message≤500, answer_cells≤2000}`; uses the frozen `_native` docker argv/env byte-for-byte with a copied worker returning the last traceback line | **copy**(`backends._native` :153-214, `native_worker.py` → `execskill/precheck_worker.py` returning message) |
| `donors.py` | frozen donor corpus for P_y / P_F (Codex F4) | `donor_corpus(edits, run_trajectories, worker, *, bench) -> DonorCorpus` (zero calls: notes/bindings on donor public views, `sheet_feedback` on stored pre-check reports, ALFWorld `alf_before_step`/state hooks replayed step by step along the stored trajectory feeding stored events to `alf_after_step`; outputs per (procedure, donor, step) with content hashes); `pair(items, donors, seed_tag) -> {item: donor}` (seeded, reuse counted); `output(corpus, proc, donor, step) -> fields` (step beyond the donor's last → last step); `seal(corpus) -> sha` | new; worker = `sandbox.client.Worker` |
| `placebo.py` | placebo twins P_y, P_i | `sham_fields(proc, item, donor_output, *, kind) -> fields` (keeps constant header; length band ±20%); `sham_compute()` → "not evaluated" + echo; `sham_repair(previous_program, execution_error, donor_advice)`; `sham_discourage(admissible, n, seed)` (drawn at dispatch, no donor); `shadow(package_new, trajectory) -> triggers` (same trigger RULE; call counts are not matched, rates reported) | new; corpus = **imp** values of `coevo5.protocol.PLACEBOS_SCREEN/CONFIRM`; donor outputs from `donors.py` |
| `judge.py` | scorer v2 + format flags | `judge(bench, public, private, prediction, receipts, *, runtime) -> {"official", "final", "v2", "lenient", "format", "flags", "carrier"}`; `select_answer(bench, reply) -> (answer, carrier ∈ {official, json, none})` = reference-independent precedence: a usable official carrier (last non-empty `<answer>`; LiveMath single letter; extracted program; action) is used EXCLUSIVELY, JSON only when it is unusable (Codex F7); `json_answer(reply) -> str|None`; invariant `v2.pass >= final.pass` asserted | **imp** `backends.score, _score_answer_tag`, `outcomes.classify/finalize`, `scoring.lenient`; v2 is new |
| `outcomes_ext.py` | rows P1–P7 in front of frozen `outcomes.classify`; copied preflight | `preflight(bench, prediction, receipts, *, deciding, refused, spent) -> Verdict|None` (copy of `outcomes.preflight` :207-228: mandatory stops — budget, ledger, assumption, cleanup — scanned over ALL receipts; delivery rows 4-5 applied to the DECIDING receipt only, Codex F12); `classify(bench, prediction, score, receipts, *, deciding, refused, spent) -> Verdict` (P-rows first, then frozen on `[receipts[deciding]]`); tokens `unknown_fault`; `worst_delivery(receipts) -> str` (recorded, never decides) | **imp** `outcomes.classify, finalize, Verdict, UNDELIVERED_ERRORS, undelivered`; **copy**(`outcomes.preflight` :207-228, `_delivery` :256-263 with `_last_error` :251-253, parameterised by the deciding receipt instead of `receipts[-1]`, :252, :258) |
| `stats_ext.py` | statistics | `item_scores(cells, arm, items, *, side) -> dict` (per-item mean over runs; L/H with `unknown_fault`); **primary** `paired_t(d, *, strata=None, clusters=None, weights=None) -> {mean, se, df, p}` (one-sided; block-stratified; ALFWorld: games-weighted t on room means, df = rooms − blocks; Codex F1); sensitivity only: `signflip(d, *, strata=None, clusters=None, n=100_000, seed) -> p`, `wilcoxon(d) -> p` (zeros dropped, tie-corrected normal); `bootstrap_ci(...)`; `iut(d1, d2, ...) -> Decision`; `holm(pvals) -> adjusted`; `spearman_perm(xs, ys, *, n=10_000, seed) -> (rho, p)` (validity rounds) | **imp** `stats.bounds, total, sign_test, bootstrap` |
| `cells.py` | one cell | `run_cell(context, cell, task, package, arm, *, store) -> record` (`store` = `TrainingStore` (full trajectories) or the evaluation adapter, Codex F16); `_solve(...)`; `_replay(context, cell, task, package, logical_log)` replays LOGICAL calls: each logical call's returned receipt and reply are served once, transport sends (frozen resends, calls.py:268-279, each recorded at :214) are kept for ledger accounting only and never served as replies (Codex F13); reads stored pre-check reports; `run_cells(context, jobs, *, workers)`; `run_parallel` | **copy**(`coevo5.cells` :1-263: VERSION, injectable solver, record keys + `package_sha256, arm_kind, enabled, withheld, restored, faults, deciding_receipt, worst_delivery, logical_calls, judge, evidence`; drop `on_reply` native grab; the preflight call at :196 replaced by `outcomes_ext.preflight(…, deciding=…)`) |
| `units.py` | unit runner | `run_unit(unit_root, *, run, identity, work)`, `complete`, `unit_path`, `cell_context`, `Setting` | **copy**(`coevo5.units` :50-160: VERSION; route-B chains) |
| `rounds.py` | interleaved rounds | `run_round(setting, attempt, endpoint, unit, arms, schedule, tasks, *, tag, blocks=None)`; `_order(values, tag)`; `table_of`; `shared_unanswered`; `guard(cells, arms, unit)` (infrastructure only; `unknown_fault` excluded); `balance(cells) -> ok` (start-time guard) | **copy**(`step.run_round, _order, table_of, shared_unanswered, guard, key, bench_of, pool_tasks`, step.py:71-157) |
| `registry.py` | root-independent consumption registry | `register(chain, bench, items, *, unit, purpose, run_root)`; `dispatch(chain, bench, items, *, unit)`; `decide(chain, bench, items, *, unit)`; `release(chain, bench, items, *, unit)` (routed_not_dispatched); `consumed(chain, bench) -> set`; one namespace per chain (`G`, `D`, `smoke`; owner rule 22:3x, REG §3.4): the same item may be consumed once in EACH chain (replication, disclosed); fcntl lock; raises `ConsumptionConflict` | new |
| `supply.py` | supplies and slices | `searchqa_tail(manifest_path, hf_cache, *, start=4001, exclude) -> list` (tail-only, hash-checks blocks A-D, never writes C/D); `alfworld_items(data_root, pool_ids) -> list` (ids in the new namespace `alfworld-xs:<sha256(gamefile relative path)[:16]>`, never equal to a 57-game pool id; the id → game-file mapping lives only in the registrar's supply file; rooms, task types from path prefix); `prereset(items, cut) -> views` (zero-call reset that writes the routing view ONLY for the cut slices: smoke 12, run 60, accept 150, examiner select candidates ≤ 200 = 422 games, estimate 7–21 min at 1–3 s per reset vs 1–2.9 h for all 3,514 [calc T8]); `order(bench, supply) -> list` (`data.ranked`, room grouping for ALFWorld); `slices(bench, order, sizes, consumed) -> dict` (ALFWorld: room groups, 40 acceptance rooms, ≤ 5 games per room per slice [calc T1]; LiveMath formal chain: run = 54 meta-absent + the first 65 of the 129 meta-present items in the fixed order, J7 options-only probe = the remaining 64 meta-present items (purpose `accept_probe`, registered and consumed by the acceptance unit), acceptance = 100 meta-absent) | **imp** `data.ranked, pool, item_hash`; **copy**(`scripts/make_searchqa_fresh_sample.build` order logic: tail-only) |
| `exclusion.py` | test exclusion under TestAccess, behind its own owner consent (O4) | `exclusion_consent(path) -> record` (exact key set `{exclusion_runs: ["alfworld_test_identity_check", "searchqa_test_exclusion"], by: "owner", date, note}` in `<root>/shared/exclusion-consent.json`; distinct from the test-read consent, because the frozen `consent()` requires `test_evaluation = true`, evaluation.py:152-159, and is not reused); `exclude_tests(pinned, supply, *, access, consent) -> {"counts", "exclusion_sha256"}`; `alfworld_test_identity(access, *, consent) -> {"split": "valid_unseen", "disjoint": bool, "counts"}`; both refuse without the consent file and print counts and hashes only, never item text | **imp** `data.TestAccess, test_ids` |
| `trajectories.py` | trajectory and enable-log records | `write(attempt, cell_id, record)`; `load_run(unit)`; `masked_view(traj, *, bench, purpose)` (detector view: answer content, run status hidden); `landmark_view(traj) -> view|Excluded(reason)` (ALFWorld, Codex F10: only episodes still active before step 10; fixed-length 10 (observation, action) pairs; terminal observations, `won`/`done` removed; early terminations → `Excluded("ended_by_step_10:<won|done|infrastructure>")`); `whitelisted(traj)` | new |
| `replay.py` | zero-call replay and engineer checks C5–C9 | `zero_crash(package, change, trajectories, worker_pair) -> report` (two workers, PYTHONHASHSEED 0 and 1, two item orders); `run_tests(change, trajectories, worker) -> report` with fixed property kinds (`applies_true/false, note_contains, note_matches, discourage_contains/excludes, binding_equals, repair_requested, state_equals`), non-vacuity, differential and negative tests; `reference_tracker_agreement(proc, alf_trajectories) -> float` | new; reference tracker = fixed port of D3 hand tracker (registrar code) |
| `detectors.py` | mechanical categories + model detectors | `MECHANICAL[bench]: dict[name, fn]` (full-trajectory categories; descriptive only); `MECHANICAL_MASKED[bench]` = the same categories evaluated on the SAME masked view the detector sees (ALFWorld: the landmark view, so `step_budget_exhausted` and full-episode loop counts are NOT part of the residual definition and are reported only descriptively; check C2); `split(run_cells, *, bench, seed_tag) -> (write, hold)` (ALFWorld by ROOM, ≥ `MIN_ROOMS_PER_HALF` = 8 rooms per half else `cannot_decide`; others by item; Codex F11); `seal_candidates(detectors) -> sha` (before any hold-half evaluation); `evaluate(detector, views, worker) -> fired`; `accept(candidates, hold, masked_mech_and_library) -> [{accepted, precision, base, p_boot, p_holm, recall, jaccard, n_fired, n_items, n_rooms}]` (residual cells = no `MECHANICAL_MASKED` category and no accepted detector fires on the masked view; item- / ROOM-cluster bootstrap; Holm over the ≤ 3 candidates at family 10%; Jaccard on the FULL masked hold half before residualization) | new |
| `generators/` (`families.py`, `officeqa.py`, `livemath.py`, `sheet.py`, `alfworld_select.py`) | registrar-defined transformation FAMILIES with fixed reference functions (Codex F8); owner rule 22:3x (b): every family consumes ONLY qualified findings of `research.py` (material or parameter choices; none → `no_material`, no items; OQ tables, LM definitions/theorems, SB LibreOffice Calc function quotes, ALFWorld selection hints only), truth still by the fixed reference function; the examiner only picks cells/parameters | `FAMILIES[bench]: {name: Family{params_schema, reference_fn}}` (OfficeQA: difference, ratio, percent change, sum over named cells — answer computed from the PERTURBED cells by the exact evaluator; LiveMath: parameterised templates solved independently by the fixed checker (sympy on the problem structure, 50 digits) in the sandbox; Sheet: formula-defined cell edits whose expected cells are recomputed by the recalc engine (semantic truth), then a SEPARATE engine qualification; benches without a family → `selection_only`); `apply(family, params, item, *, private) -> item | Drop(reason)` with `truth` and `engine_qualification` recorded separately; ALFWorld `select(filter_spec, pool_views) -> games` + `null_select(n, seed)` | **imp** `forward.evaluate` kernel (via `compute.py`), `sheet_recalc`; engine qualification via `execskill.qualify`; D6 drop reasons as template |
| `examiner.py` | examiner role prompts + parsing | `detector_write(roles, payload) -> [detector]`; `generator_write(roles, payload) -> [generator]` (a generator = family + parameter ranges + research requests, owner rule 22:3x (b)); `research_requests(generator) -> [request]` (checked mechanically by `leakage.findings/mechanical` before dispatch; no item text); `policy_revise(...)`; `gates(generator, ...) -> GateRecord` (T, D band, S shortcut, L labels) | **imp** `roles.Roles.plain/fit`; new parsers |
| `research.py` | examiner research, the mandatory step of every generation path (owner rule 22:3x (b); REG §7.2) | copy of `skillopt/coevo5/research.py` with VERSION `fivebench-execskill-v1` (USER_AGENT carries the new version; API parameters byte-identical): `Wikipedia` (frozen parameters :49, :135-143; disambiguation and "Jeopardy" titles dropped :53, :190-192; explicit credential-free proxy :145-154), `Archive(root)` (pinned SHA-256 index verified on open, :353-393; Python 3.11 / openpyxl / LibreOffice Calc help pages and the public task cards), `Sources` (every result list and page archived write-once by hash before use, :395-407 → `write_immutable_json`, continual_eval/core.py:60-61), `verbatim` (:342-346) and `_qualify` (:510-531), `request` (≤ 3 rounds × ≤ 3 queries, ≤ 3 pages, ≤ 8 calls, coevo5 protocol.py:254-257, :63); NEW request kinds `family_material(roles, sources, *, bench, family, label)` (OQ: an eligible Wikipedia numeric table, :59, :328-334; LM: a verbatim Wikipedia definition/theorem ≤ 1,500 chars, :58; SB: an archive quote of each LibreOffice Calc function used) and `parameter_choice(roles, sources, *, bench, family, request, label)` (each value backed by a verbatim quote; values outside the family's registered ranges dropped), `selection_hint` (ALFWorld selection filter only); `split(findings, unit) -> (g_self, g_acc)` by seed `execskill-v1:research-split:<unit>`; researcher = GLM-5.3 role charged to `…:examiner:research` | **copy**(`coevo5.research`: whole module minus `rewrite` and the `skill.Rule` import, which route B has no use for; roles **imp**) |
| `engineer.py` | engineer role + fixed checks C1–C9 | `propose(roles, payload) -> Manifest + sources`; `check(change, ctx) -> CheckReport`; `fix(roles, change, report) -> change`; `candidate(parent, changes) -> Package` | **imp** `roles`, `leakage.normalize, Corpus, findings, mechanical, adjudicate` |
| `describer.py` | text twin at freeze | `describe(roles, procedure) -> text` (pinned prompt, one call, frozen sha) | new |
| `acceptance.py` | one acceptance round + decision | `prepare(step) -> Sealed{candidate_sha, edits, donor_corpus_sha, placebo_y, placebo_i, plan(A*), twins, G_acc, dup_arm}` (G_acc = one generated item per A\* item; arms S', S, P_y, C (+ S_dup on benches with a generator after step 1)); `dispatch(sealed, blocks)`; `decide(cells, sealed) -> decision.json` (J1–J7, REG §6.4: J1/J2 by `stats_ext.paired_t`, sign-flip and Wilcoxon recorded as sensitivity; J3 = fault items of A (S' and P_y, any run, routing or execution) / \|A\|; J4 = item counts with margin max(2, ⌈0.02\|A\*\|⌉); J6 on every registered duplicate pair; harmful-sham rule → S'−S only at 2.5%, wording "content/effort explanation not excluded"; second-call and repair-call rates per arm, > 10-pt flag); \|A\*\| < 30 or ALFWorld < 20 rooms → `decision.json` with `decision: "not_run_small_astar"`, S' archived, S passes on unchanged, every slice item released as `routed_not_dispatched` (nothing consumed; O9, Codex F1) | new; uses `stats_ext`, `rounds`, `donors` |
| `validity.py` | predictive validity metric (Codex F9) | `round_pair(decision, g_acc_cells) -> {d_gen, d_real, se_gen, se_real, cov}` (ONE S'−S pair per acceptance round); `dup_control(cells) -> {gen_ci95, real_ci95}` (registered duplicate arm pair); `status(rounds) -> "refuted"|"validated"|"not_evaluable"` with precedence refuted > validated > not_evaluable: refuted = ≥ 8 rounds and (≥ 2 rounds with \|d_gen − d_real\| > 2·√(se_gen² + se_real² − 2cov) or the duplicate's generated-set CI excludes 0); validated = ≥ 8 rounds, not refuted, Spearman > 0 with permutation-over-rounds p < 0.05 (10,000, seed 20261021), duplicate CIs cover 0 on both sets; else not_evaluable | new; uses `stats_ext.spearman_perm` |
| `step.py` | eight sub-steps of one step | `run_step(setting, chain, bench, k, parent) -> StepRecord` (units run, diagnose, generate (≤ `BAND_ROUNDS` = 3 band probes), engineer, selftest (≤ `SELFTEST_PASSES` = 2), donors, accept-b<m>, decision, freeze) | new orchestration over copied units |
| `evaluation.py` | multi-arm test read | `evaluate(unit_root, *, run, shared, pinned, chain, bench, arms, plan, context, workers)` (1 run per test item, REG §8.1; arms F, C, P_F, T_F, twins ≤ 2 per item); consent check with the new test-read key set (§2.10); structural-zero sharing; `EvaluationStore` persistence adapter (Codex F16: sealed cell records hold `request_sha256`, `reply_sha256`, judge tokens and flags only; raw predictions/receipts live in `<attempt>/transient/` and are deleted after scoring incl. re-execution, with a deletion-manifest hash; the copied evaluation no longer calls the ordinary cell persistence, evaluation.py:379 → cells.py:97/:187/:224); `canary_scan(attempt_dir, canaries) -> hits` over EVERY artifact before sealing (hit → pause); `unseal(chain_root, ..., keyed by (arm, task_id, run))` refusing until the owner's continuation file exists and, when it says `continue`, the hashed formal-chain addendum also exists and predates the unseal; otherwise later reads are labelled `repeated_test_development` (Codex F17) | **copy**(`coevo5.evaluation` :43-450: CONSENT_FIELDS new set, multi-arm, re-keyed unseal) |
| `qualify.py` | SB qualification with importable versions | `qualify(...)` = copy of the record-producing closure of `coevo5.qualify.qualify` stamping `fivebench-execskill-v1-sheet-qualification` (the frozen one imports v3 `VERSION`, qualify.py:24, and stamps it at :124; Codex F15); `load(path, *, importable=IMPORTABLE) -> record` (own version, or a v3 record only via `IMPORTABLE`); `reverify(record) -> None` (zero calls, pinned hashes) | **copy**(`coevo5.qualify.qualify` :93-131 record part, `load` :134-140); **imp** frozen scoring helpers (`reference_prediction`, `_check`, `_passed`, `category`, `backends.score`) |
| `manifest.py` | manifest build/verify | `make(out, **pins) -> path`; `load(path, *, verify=True)`; `verify_code(manifest)`; `environment()` (python, docker version, image digests via `docker image inspect`, in-image `pip freeze` via one sandbox ping); FIELDS (§2.9) | **copy**(`coevo5.manifest` :33-151) |
| `readout.py` | registered readouts | `q1_home` (paired t, Holm over \|L\|), `q2_similar`, `q3_noninferiority`, `code_vs_text` (interval readings: superiority if the 95% bound excludes 0, non-inferiority at ±5 points off-home, else `inconclusive`; Codex F20), `labels(holm=True)` (priority table: harmful elsewhere > general > benefit established only at home > cannot act elsewhere > no measurable effect, other descriptors listed; Codex F21), `format_withholding`; tables with M/E labels and selection vs generalization evidence labels | new |
| `chain.py` | chain runner | `run(setting, chain)`, `terminate`, child launch per bench evaluation; `.runner.lock`; `chain-complete.json` | **copy**(`coevo5.chain` :57-310) |
| `smoke.py` | smoke stages S0–S4 | `s0()`, `s1_probe()`, `s2_solver()`, `sn1_noise()`, `s3_roles()`, `s4_ministep()`, `summary()`; format floor 0.9 and margin 1/20; receipt classes (Codex F19): `CONTROL` = S1-e probe and registered fault-drill receipts (enumerated, excluded; S1-e must classify as `reasoning_mismatch`), `PRODUCTION` = every receipt sent with the registered body AND the registered M and B (the S2, S-N1 and S4 cells other than the enumerated fault-drill cells); `PROBE` = S1-a…d and S1-f (registered body but probe-only M/B: B_probe = 32,768 sequential, M = B = 64 for S1-d; B is undecided until S1-b), listed separately, not counted, also leak-free; pass needs ≥ 300 production-configuration receipts with zero reasoning leaks; resend receipts counted separately and also leak-free | **copy**(`coevo5.smoke.format_check` pattern :69-77, :275-310) |
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
 "replies":["<first reply>","<second reply>"],"deciding_receipt":1,"worst_delivery":"delivered|undelivered:<error>|truncated",
 "logical_calls":[{"purpose":"first","receipt_index":0,"send_indices":[0]},{"purpose":"second","receipt_index":1,"send_indices":[1,2]}],
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
 "description":"...","view":"alf_landmark10|qa_masked|sheet_masked","written_from":"<unit>/write-half","candidates_sha256":"<sealed before hold>",
 "split":{"unit":"room|item","write_rooms":8,"hold_rooms":8},
 "validation":{"hold_unit":"...","residual_rule":"mechanical_on_masked_view","excluded_early_end":{"won":5,"done":0,"infrastructure":1},
   "residual_cells":118,"n_fired":14,"n_items":9,"n_rooms":5,"precision":0.86,"base":0.55,
   "p_boot_lift_le_0.10":0.02,"p_holm":0.06,"recall_residual":0.21,"jaccard_max_full_hold":0.31,"faults":0,"deterministic":true,
   "accepted":true},"retired_at":null}
```

### 2.5 Generator and generated-item set
```json
{"version":"fivebench-execskill-v1-generator","id":"g-officeqa-2-1","bench":"officeqa","source":"<python emitting family parameters>",
 "family":"officeqa.percent_change","params":{"...":"..."},"source_sha256":"...",
 "gates":{"truth":{"made":80,"dropped":{"format":3,"reference_fn_failed":11,"literal_not_in_context":2,"answer_in_context":1},
          "engine_qualification":{"checked":66,"failed":0}},
          "band":{"probe_items":30,"pass_rate":0.47,"adjustments":1,"in_band":true},
          "shortcut":{"probe":"question_only","flagged_share":0.07,"used":true},"labels":{"key_balance":{"A":0.2}}},
 "status":"admitted|validated|refuted|not_evaluable","rounds":[{"step":"...","contrast":"S'-S","d_gen":0.03,"d_real":0.05,
   "se_gen":0.04,"se_real":0.06,"cov":0.001}],"dup_control":{"gen_ci95":[-0.04,0.05],"real_ci95":[-0.06,0.04]}}
```
Generated item (one line of `items.jsonl`): `{"id":"gen:<gen>:<n>","source_item":"<id>","public":{...frozen bench schema},
"private":{"answer": "...","truth":{"kind":"family_reference|sympy_solve|recalc_formula|simulator","family":"...","checked_by":"execskill.generators.officeqa"},
"engine_qualification":{"passes":2,"ok":true}},
"set":"G_self|G_acc","seed":123}`.

### 2.6 Acceptance record (`decision/decision.json`)
```json
{"version":"fivebench-execskill-v1-decision","step":"pilot/s1-spreadsheetbench/t1","bench":"spreadsheetbench",
 "freshness":"route_b_fresh_method_side_reused","sealed":{"candidate":"<sha>","parent":"<sha>","placebo_y":"<sha>",
 "placebo_i":"<sha>|null","plan_sha256":"...","twins_sha256":"...","g_acc_sha256":"...|null"},
 "A":60,"A_star":41,"A_star_rooms":null,"runs":2,"blocks":["b1"],"mde_registered":0.12,"evidence_kind":"selection",
 "edits":[{"kind":"new|revision|deletion|narrowing","id":"p-...","astar_items":30}],"donors":{"corpus_sha256":"...","reuse_max":1},
 "contrasts":{"S'-S":{"mean":0.06,"whole_batch":0.041,"p_t":0.03,"df":40,"sensitivity":{"p_signflip":0.03,"p_wilcoxon":0.02},
              "ci95":[-0.01,0.13],"up":9,"down":3,"tie":29},
              "S'-P_y":{"...":"..."},"P_y-S":{"...":"...","by_donor":"..."},"P_i-S":{"...":"..."},"S'-C":{},"S-C":{}},
 "guards":{"J3":{"fault_items":1,"A":60,"share":0.0167,"ok":true},"J4_items":{"S'":2,"S":1,"margin":2,"ok":true},
   "J5":{"infra":{"S'":0.0},"reasoning":0,"unanswered":0,"balance":true},"J6_dup":{"pair":"S-C|S-S_dup","p_two_sided":0.61},"J7_meta":null},
 "placebo_rule":"informative|harmful_sham_parent_only_2.5pct|helpful_sham_reported","second_call_rates":{"S'":0.31,"P_y":0.29,"flag_gt_10pt":false},
 "worst_delivery_rates":{"S'":0.0},"twins_cap":{"max_per_item":2,"not_withheld_items":0},
 "twins":{"p-...":{"n":20,"tau":0.05,"ci95":[-0.1,0.2]}},"decision":"accept|reject|undetermined|not_run_small_astar","reason":"..."}
```

### 2.7 Consumption record (`/data/execskill-history/consumption/<chain>/<bench>.jsonl`; chain ∈ {G, D, smoke}, owner rule 22:3x)
`{"version":"fivebench-execskill-v1-consumption","chain","bench","item_id","item_hash","state":"registered|dispatched|decided|routed_not_dispatched",
"purpose":"smoke|run|accept|accept_probe|examiner|detector_holdout","unit","run_root","attempt","ts","record_sha256"}` (one line per state change; the
reader folds lines; states only move forward; another unit OF THE SAME CHAIN touching a non-released item → `ConsumptionConflict`; chains G and D have separate namespaces and see the same items, REG §3.4).

### 2.8 Cell record (copied cells + new keys)
v3 keys (cells.py:221-230) + `package_sha256, arm_kind ∈ {candidate, parent, card, placebo_y, placebo_i, dup, text, withhold:<id>, restore:<id>,
gen:<set>}, enabled, withheld, restored, faults{kind: n}, deciding_receipt, worst_delivery (recorded, never decides), logical_calls
[{purpose, receipt_index, send_indices}] (replay unit; `sends` stay for accounting), judge (incl. v2 carrier), evidence, shared_with (cell id when
structural-zero shared)`. Evaluation cells use the `EvaluationStore` shape of §2.10 instead.

### 2.9 Manifest (`fivebench-execskill-v1-manifest`)
`{version, root, history_root, slot_root, data{supply files + sha, items files + sha, split pins}, sheet_qualification{imported record sha,
engine sha, reverified_at}, cards{bench: sha}, contracts{bench: {text, sha}}, templates{name: sha}, lexicon_sha, placebo_corpus_sha,
runtime{bench: {...}}, sandbox{image_id, worker_sha256, policy_sha256, docker_argv_template_sha, limits, measured{vsz, rss, view_bytes_p99}},
clients{solver{backend: "elucid", model, url_host, env_path, proxy, reasoning_effort: "none", M, B, branch: "E|N", read_timeout, slots,
response_model_ids, client_source_sha}, roles{model: "glm-5.3", max_tokens: 16384, read_timeout: 900, reasoning: "low"}}, seeds, sizes,
thresholds, caps, importable_versions, fixtures{sha}, code(pin_code over skillopt/ and scripts/), loaded_code, environment{python,
openpyxl, docker, image digests, in_image_pip_freeze_sha}, provenance{build_tree: "/data/execskill-dev", git_head, snapshot_root: "/data/execskill-20261021-source", sha256_list_sha256, env_files_absent: true}, record_hash}`. `verify_code` + zero-call `docker image inspect`
before EVERY unit; mismatch → `chain-terminated.json`.

### 2.10 Test-read record and consent
Test-read consent: `{test_evaluation, sheet_test_qualification, multi_arm_arms, by: "owner", date, note}` (exact set). Exclusion consent
(separate owner file, O4): `<root>/shared/exclusion-consent.json` = `{exclusion_runs: ["alfworld_test_identity_check",
"searchqa_test_exclusion"], by: "owner", date, note}` (exact set); required by `exclude-tests` before the S0 test-exclusion runs (ALFWorld
`valid_unseen` identity check, SearchQA exclusion), which hold TestAccess before any test-read consent exists.
Evaluation cell (sealed record, Codex F16): hashes only (`request_sha256`, `reply_sha256`, token, judge tokens, flags, `transient_deleted_sha256`);
raw predictions/receipts only under `<attempt>/transient/` until scoring (incl. re-execution) finishes, then deleted; `canary_scan.json`
`{artifacts_scanned, hits: 0}` written before sealing. Owner continuation file `<root>/shared/owner-continuation.json` `{by: "owner", date,
decision: "continue|stop", note}` must exist before `unseal`; with `continue`, the formal-chain addendum `<root>/shared/formal-addendum.json`
`{sha256 of the addendum document, written_at}` must also exist and predate the unseal, else every later test read is labelled
`repeated_test_development` (Codex F17).

## 3. Hook points in the copied backend paths (`execskill/solver.py`)

Frozen references are to `skillopt/continual_eval/backends.py`. The copy must reproduce frozen requests byte for byte when the
package is empty (equivalence test T-SOLVER-1; on ALFWorld only on episodes in which every reply is an exact admissible command,
`how == tag_exact`, because the always-on level-1 canonicaliser executes the canonical command where the frozen loop executes the raw
text, backends.py:752-762, and one such step changes every later transition and request of the episode; T-CANON-4 isolates that difference, and route-B ALFWorld numbers are therefore not comparable with v3's).

| Path | Frozen location | Route-B hook | Rule |
|---|---|---|---|
| QA system prompt | :379-394 (base + contract + "Frozen skill guidance (use only where applicable):" + skill_text) | none | skill_text = active bench card only (REG §2.2); identical bytes in S', S, C, P |
| QA user | :417 `json.dumps(view)` | `before_call`, `bindings` → `view["procedure_notes"]` as LAST key | rendered by `notes.render` with fixed headers; absent when empty (keeps equivalence) |
| QA first call | `_response(call, system, user)` :90-113 | — | Recorder per call; truncated → no second call |
| QA post-call | after :417-424, before extraction :425-436 | `<calc>` round trip (REG §2.4) | at most one second call; user = first user + `first_reply`, `computed`, `instruction`; final = second if delivered and not truncated, else first; the cell is decided on that deciding receipt (`outcomes_ext.preflight/classify`), `worst_delivery` recorded |
| Sheet view | :397-409 | `before_call`; workbook passed to the sandbox as a read-only mounted file `/input/input.xlsx` (never inlined) | — |
| Sheet after extraction | around per-case `_native` loop :433-452 | `precheck` once on the public input → `sheet_feedback` → optional ONE repair call | precheck in a one-shot container with frozen argv/env; native slot only around each container run; final program = repair program if delivered |
| ALFWorld routing | before the loop | `applies` on `{initial_observation, admissible_commands_at_reset, task_text}` from the items file; sha256 asserted against the live reset view | — |
| ALFWorld pre-call | view construction :744-746 | `alf_before_step` → notes (≤ 1,500 chars/step) + discouraged list rendered as `NOT_RECOMMENDED_PREFIX + ", ".join(cmds)`; shown admissible list UNCHANGED | — |
| ALFWorld action | parse :752-756 | `canonical.canonical` (level 1) | `how` logged; empty or > 1000 chars → `invalid_action_format` (frozen rule) |
| ALFWorld post-step | after `env.step` :762-764 | `alf_after_step(event, state)` | state ≤ declared bytes; host keeps state |
| ALFWorld catch-all | `except Exception` :774-776 | re-raise `SandboxUnavailable, CleanupUnconfirmed, BudgetStop, AssumptionBroken, LedgerFailure, ConfigurationError, ConsumptionConflict` BEFORE the catch-all | unit test T-SOLVER-6 |

Prediction shape = frozen shape + `shell` key: `{route, calls[{purpose, request_sha256, receipt_index}], procedure_events, faults,
notes_chars, deciding_receipt, worst_delivery, fallback, precheck, compute}`. The shell has NO function that writes or edits the delivered reply.
Empty-package equivalence compares two projections (REG §2.3, Codex F23): request hashes, and the prediction minus `shell`; ALFWorld only on
episodes whose every reply is `tag_exact`.

Text arm (`text=`, T_F, REG §8.1, Codex F20): `before_call` → the frozen description in the same slot (±20% of the procedure's median note
length on the run slice); `bindings` → description + the registered `<calc>` invitation, no values (the fixed evaluator still serves plain-number
expressions under the same trigger rule); `sheet_feedback` → description + the shell's own error message, one repair call under the same
trigger rule; `alf_before_step`/state → description each step, no discouraged list, no state; a procedure with no output on an item shows
nothing there.

Placebo arms (`placebo=`): same predicates and hooks; content from the SEALED donor corpus (`donors.output`, computed zero-call before
dispatch, REG §6.1, Codex F4) via `placebo.sham_*`; the ALFWorld discourage sham is drawn at dispatch; second calls by the same trigger RULE
(compute: the solver's own `<calc>` tag; repair: `placebo.shadow` runs S' procedures on the placebo's own trajectory to decide `request_repair`,
the shadow result is never shown); call counts are NOT matched, per-arm rates are reported (Codex F5). Twin arms (`withhold=`): the withheld
procedure's predicate still runs and is logged `shadow_fired`; restoration twins (`restore=`) re-insert a deleted/narrowed procedure (REG §6.1
edit-type table).

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
  `docker rm --force <name>` bounded 10 s, then `docker ps -a --filter name=^/<exact name>$` must list nothing (the frozen `_native` likewise
  verifies only its own uuid name, backends.py:158, :190), else `CleanupUnconfirmed`; the prefix-wide `docker ps -a --filter name=execskill-sbx-`
  check runs ONCE in `drain_check` after every worker of the unit has exited, because up to six workers legitimately coexist (Codex F14).
- **Lifetime**: lazily started on the first call of a cell (QA/Sheet) or an episode (ALFWorld); ALFWorld card-arm episodes start an
  empty-package worker so every arm takes the same slot path (REG §6.2). A container start acquires an `execskill-sandbox-live` slot
  (cap 6; SpreadsheetBench units ≤ 2), released only after the forced removal is confirmed. Workers for engineer checks: two containers with
  PYTHONHASHSEED 0 and 1.
- **Slots and lock order**: `alfworld-episode` (6) → `execskill-sandbox-live` (6 live containers, held for a container's lifetime;
  SpreadsheetBench units ≤ 2) → `execskill-sandbox` (per call; 4 on 7 CPUs, registered after S0) → model pool (frozen Endpoint; elucid 8,
  glm-5.3 10) → `spreadsheet-native` (3). Waits for `alfworld-episode`, `execskill-sandbox-live` and `spreadsheet-native` use the frozen
  untimed wait with a wait-log line every 300 s; a slot wait NEVER maps to P4 (the registered lock order already prevents deadlock).
  Only the short-hold per-call `execskill-sandbox` pool keeps a timeout: 600 s → logged, one retry; a second consecutive timeout →
  `SandboxUnavailable` (P4), because holds there last seconds. ALFWorld units run with workers = 6 = episode slots (check C3; calc T8: the
  maximum-schedule ALFWorld acceptance round has ≈ 900 episodes (S', S, P_y, C + 2 twins per game); 16 workers on 6 slots with a 3,600 s
  timeout would give ≈ 20 spurious P4s; with 6 workers, none).
- **Escape probe** (S0, fixed registrar code in the same container argv): no network (`socket.connect(("1.1.1.1", 53))` fails), `/` and
  `/runner` read-only, uid 65534, env keys == registered list, no `*.env`, `*key*`, `consent*`, `ledger*` under `/`, pids/memory limits
  bite, child cannot write files (FSIZE).

## 5. Concurrency, ledger and recovery wiring

- One `budget.Budget` at `<root>/shared/ledger` (imported unchanged). One Endpoint per unit attempt per role (halt generation,
  calls.py:145). Solver Endpoint constructed with `max_tokens = B`; `ElucidClient` sends nominal `M`. Scopes via `budgets.py`;
  examiner-triggered solver cells (band, shortcut, G_acc) are charged to `…:examiner`, self-test to `…:selftest`, acceptance to
  `…:accept:attempt-N`, test reads to `<chain>:xs:test`; every scope is prefixed by its chain (`G:` / `D:`, owner rule 22:3x) and each chain has its own caps (REG §9.3); research calls go to `<chain>:…:examiner:research` (4.6M per step and bench, calc T11).
- Threads: 16 per QA/Sheet unit; ALFWorld units run with workers = 6 = `alfworld-episode` slots (check C3). Acceptance in blocks (SearchQA 4,
  OfficeQA 2 time-separated ≥ 2 h, ALFWorld 4); SpreadsheetBench and ALFWorld never run concurrently (memory on 15 GiB).
- **Two chains (owner rule 22:3x (c); REG §4.1, §11).** Chain G (solver `solver_client("glm-5.3")`, M = B = 65,536, read timeout 2,400 s,
  `glm-5.3` slots = 10 shared with BOTH chains' role calls) and chain D (elucid, 8 slots) run from one manifest listing `CHAINS`. They run
  concurrently only if memory and slots allow: machine-wide at most ONE SpreadsheetBench unit at a time (one SB unit's worst case is 13.5 GiB),
  SpreadsheetBench and ALFWorld never concurrent across chains, QA units may overlap; the sandbox-live (6), native (3) and episode (6) pools are
  machine-wide. Chain G gets a zero-call cap check after its first run unit (its per-cell cost is not measured in the elucid-only smoke); a
  breach pauses chain G only (REG §9.3).
- **Memory** (O12): host 15 GiB, 7 CPUs. Worst-case sum of container memory limits [calc T8]: ALFWorld unit 6 × 768 MiB + 6 env workers
  (≤ 1 GiB each, assumed) = 10.5 GiB; QA unit 6 × 768 MiB = 4.5 GiB; SpreadsheetBench unit 2 live sandboxes × 768 MiB + 3 native × 4 GiB =
  13.5 GiB, admissible only if the S0-measured native peak RSS ≤ 2 GiB (expected sum ≤ 7.5 GiB), otherwise native slots 3 → 2 (written
  into the manifest before S1). SpreadsheetBench and ALFWorld never concurrent.
- Recovery: copied `units.run_unit` attempt-N; owner `recovery.json`; a redo re-dispatches the whole block with the SAME sealed inputs
  (incl. the donor corpus) and the same registry entries; ≤ 2 redos, the first paid from the redo reserve, a second only with an owner cap
  decision written in `recovery.json`; no splicing across attempts (owner decision #15 may change this).
- Maximum schedule (REG §9.2, Codex F18) is enforced in code, not only budgeted: `router.plan` caps twins at 2 per item, `package.validate`
  caps 3 edits per step, `step.py` caps band probes at 3 and self-test passes at 2; caps in `protocol.py` derive from it (calc T6).

## 6. CLI `scripts/run_execskill.py` (subcommands)

`probe` (S1) · `sandbox-selftest` (S0 sandbox suite + escape probe + measurements) · `import-texts` (accepts exactly
`fivebench-coevolution-v3-texts-import`) · `import-sheet-qualification` (+ zero-call reverify) · `make-items --bench alfworld|searchqa`
· `exclude-tests` (TestAccess under the owner's `exclusion-consent.json`; counts + exclusion hash only) · `make-fixtures` · `smoke-make` / `smoke --stage S0|S1|S2|SN1|S3|S4` /
`smoke-summary` · `make-manifest` · `consent` (writes nothing itself; validates the owner's file) · `run --manifest M --chain C`
· `step-unit` / `evaluate-unit` (children) · `replay --package P --trajectories DIR` (zero tokens) · `show-package` · `monitor`
(counts, never scores) · `recover` · `terminate` · `resume-ledger` · `continuation-check` · `report`. Every launch script: `unset
OPENAI_API_KEY OPENAI_BASE_URL`, `export PYTHONDONTWRITEBYTECODE=1`, runs `python -B` from the verified snapshot.

## 7. Fixtures and fake backends (zero-API tests): `tests/execskill_fakes.py`

- `FakeSolver(script)`: deterministic replies keyed by `(bench, request_sha256)` or by regex on the user JSON; can emit: tagged answer,
  JSON answer, `<calc>` tags, truncated reply (`finish_reason="length"`), over-nominal usage, reasoning tokens > 0, reasoning_content,
  undelivered errors; produces receipts in the frozen Client shape (port of `tests/coevo5_fakes.py`).
- `FakeGLM(script)`: engineer/examiner/describer/leakage replies (valid, invalid JSON, fenced code, policy-violating code).
- FakeSolver per model (owner rule 22:3x (c)): `glm-5.3` receipts in the frozen Client shape with thinking enabled (reasoning text allowed,
  never a mismatch), `deepseek-v4.1-flash-1017` receipts reasoning-off; keyed additionally by model so one e2e run drives chains G and D.
- `FakeResearch` in `tests/execskill_fakes_research.py` — a SEPARATE file owned by A11 (like `execskill_fakes_docker.py` of A5 and
  `execskill_fakes_env.py` of A6), so file ownership stays disjoint and A2's `execskill_fakes.py` is untouched: an `httpx.MockTransport`
  Wikipedia API at the frozen parameters (search and parse replies incl. a redirect, a disambiguation page, a "Jeopardy" title, an eligible
  numeric table, a definition paragraph), a fixture archive directory with `index.json` and pinned sha256 (Python / openpyxl / LibreOffice Calc
  help pages, task cards), scripted researcher replies (valid, invalid JSON, a non-verbatim quote, a request that exhausts its calls).
- `FakeDocker`: implements the sandbox argv contract by running `worker.py` in a local subprocess with the same framing (for CI on a
  machine without docker; the REAL container is exercised in S0 on dl). Can inject: container start failure, cleanup failure, worker
  SIGKILL, frame corruption.
- `FakeAlfEnv(games)`: scripted text environment with admissible commands, `won` signal, `infos.extra.expert_plan/gamefile` present (to
  test stripping); rooms and task types.
- `FakeNative`: SpreadsheetBench program execution returning scripted run reports.
- Fixture items: 20 per bench shaped like real public views (OfficeQA table-text pages with arithmetic answers; LiveMath five-option items
  with symbolic truth; SpreadsheetBench workbooks incl. one at the measured p99 size; SearchQA short QA; ALFWorld 12 fake games incl. short
  successful episodes (T ≤ 10) and episodes whose terminal observation contains "You won"); Codex-round fixtures: tag/JSON conflict replies
  (both orders, tag right/JSON wrong and the reverse, empty tag + JSON, JSON only); valid-first/undelivered-second and valid-first/truncated-second
  cells; a resend + two-call repair + re-execution cell; two live sandbox workers; test-content canary strings; fixture
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
| T-CLIENT-6 | client | (owner rule 22:3x) `solver_client("glm-5.3")` returns the frozen `weak_solver_probe.Client` with backend bigmodel, NO route, thinking enabled / effort low, max_tokens 65,536, read timeout 2,400 s, proxy GATEWAY (fake credentials file, nothing printed); `solver_client("deepseek-v4.1-flash-1017")` returns `ElucidClient`; any other model → `ConfigurationError`; a glm-5.3 receipt carrying reasoning is NOT a mismatch |
| T-LEDGER-1..3 | budgets | Endpoint reserves with B; completion in (M, B] → no halt; completion > B → `AssumptionBroken`; scopes rooted |
| T-SLOT-1..2 | slots | (1) 16 workers, 6 `alfworld-episode` slots, heavy-tailed fake durations (lognormal, median 300 s, p90 1,900 s, simulated clock) → all episodes finish, zero P4, zero deadlock; (2) lock-order assertion fires on an out-of-order acquire; the live-container cap (6; SpreadsheetBench ≤ 2) is never exceeded; short-hold pool: one timeout → logged retry, two consecutive → `SandboxUnavailable` |
| T-PKG-1..5 | package | canonical sha stable; caps (incl. ≤ 3 edits per step, Codex F18); withhold/with_ produce new shas; narrowed benches respected by router; (5) `edits(parent, candidate)` classifies new / revision / deletion / narrowing and `restore()` yields the restoration-twin sha (REG §6.1 edit-type table, Codex F6) |
| T-POLICY-1..6 | policy | each forbidden name/attribute rejected; module-level statements rejected; meta-option/bulletin/receptacle literals rejected; allowed imports pass |
| T-SBX-1..12 | sandbox | load/call/ping; timeout, memory, NaN, over-cap, nesting, print, module loop, SIGKILL of child and of worker → P1 not P4; restart without faulting proc; image missing → `SandboxUnavailable`; exact-name cleanup failure → `CleanupUnconfirmed`; fresh namespace per call (state cannot leak); two hash seeds give equal hashes for deterministic code and differ for `fx-nondeterministic` |
| T-SBX-13 | sandbox | (Codex F14) two live workers in one unit: closing worker 1 verifies only its own exact container name and succeeds while worker 2 is alive; `drain_check` after both have exited fails if any `execskill-sbx-` container remains and passes otherwise |
| T-COMP-1..5 | compute | grammar, names, magnitude guard on `(((9**99)**99)**99)` style input, depth, "not evaluated" on failure |
| T-NOTES-1..3 | notes | rendering fixed headers; lexicon drops count as faults; SB exempts "format" |
| T-ROUTE-1..5 | router | deterministic; predicate fault → not enabled; A\* computed from public views only; ALFWorld routing view sha asserted; (5) edit-type A\* (new: fires; revision: old OR new fires; deletion: the deleted procedure fired in S; narrowing: the narrowed-out set), twins capped at 2 per item with priority changed-first then inherited by enable count, restoration twins on a seeded half of the deletion items (Codex F6, F18) |
| T-SOLVER-1 | solver | **empty package ≡ frozen `backends.solve`** on the two registered projections (request hashes; prediction minus the `shell` key; REG §2.3, Codex F23) on fixtures of all five benches; ALFWorld only on episodes whose EVERY reply is an exact admissible command (`how == tag_exact`); an episode with one non-exact step is excluded whole, never compared step by step |
| T-SOLVER-2..8 | solver | notes last key; compute round trip ≤ 1 extra call; truncated first reply → no second call; second-call fallback; Sheet precheck uses frozen argv/env; native slot never held during a model call (3 slots / 12 workers, no deadlock); ALFWorld catch-all re-raises route-B stops; `delivered_reply == model_reply` for QA; discouraged commands never removed from the shown list; expert_plan/gamefile never in any view, note, trace |
| T-SOLVER-9 | solver | text arm T_F per hook (REG §8.1 table, Codex F20): `before_call` shows the frozen description in the same slot within ±20% of the procedure's median note length; `bindings` shows the description and the `<calc>` invitation without computed values; `sheet_feedback` shows description + the shell's error message and allows one repair call under the same trigger rule; `alf_before_step`/state shows the description each step, no discouraged list; no output on an item → nothing shown |
| T-CANON-1..3 | canonical | level-1 rules; NO earliest-admissible search (a reply rejecting "go to drawer 1" then mentioning it is NOT mapped) |
| T-CANON-4 | canonical | isolates the level-1 canonicaliser: a reply "Action: go to X" is executed by route B as the canonical "go to X" while the frozen v3 loop executes the raw text (backends.py:752-762); `how` logged; the divergence starts at the first non-`tag_exact` step and carries into every later transition and request of that episode (asserted on a fixture whose later requests differ), which is why T-SOLVER-1 compares only episodes whose every reply is `tag_exact` and why route-B ALFWorld numbers are not comparable with v3's (REG §2.2, §2.3) |
| T-PLACEBO-1..5 | placebo | donor pairing by seed deterministic (one donor per acceptance item; unavailable step → last available donor step); length band; header kept; compute sham echoes + "not evaluated"; repair sham keeps program + error; shadow triggers equal S' triggers on the same trajectory |
| T-PLACEBO-6 | placebo/donors | (Codex F4) donor outputs computed with ZERO model calls (FakeSolver/FakeGLM call counters stay 0) from the parent's sealed run-slice trajectories; content hashes sealed with the candidate, a donor trajectory changed after sealing → refusal; no acceptance-item text in any donor output; ALFWorld discourage sham drawn at dispatch from the admissible commands with the registered seed; `P_y−S` reported by donor cluster |
| T-JUDGE-1..4 | judge | v2 ≥ official on all fixtures and on archived v3/cal-1 TRAINING cells (S0); JSON extraction cases; completion-aware failures |
| T-JUDGE-5 | judge | precedence (REG §4.4, Codex F7): a usable official carrier (non-empty last `<answer>` tag / single letter / extracted program / action) is used EXCLUSIVELY even when the JSON disagrees — tag right + JSON wrong → pass, tag wrong + JSON right → fail; JSON consulted only with no tag, an empty tag or no program; v2 ≥ official on every conflict fixture |
| T-OUT-1..3 | outcomes_ext | rows P1–P7; `unknown_fault` excluded from infrastructure share; delivery decided on the deciding receipt, `worst_delivery` recorded and never decisive |
| T-OUT-4 | outcomes_ext | copied preflight (Codex F12): a mandatory stop in ANY receipt (incl. a non-deciding first receipt) halts; delivery checks read the DECIDING receipt, never `receipts[-1]` (the frozen behaviour: `_delivery`, outcomes.py:256-263, reads `receipts[-1]` at :258) |
| T-OUT-5 | outcomes_ext + judge | through actual scoring: valid first + undelivered second → the first reply is scored, not an infrastructure fault; valid first + delivered-but-truncated second → the first reply is scored, `worst_delivery = truncated` recorded; P5 consistent with REG §2.4 |
| T-STATS-1..7 | stats_ext | (1) `paired_t` one-sided p equals a hand computation; (2) block-stratified t; ALFWorld games-weighted t on room means, df = rooms − blocks; (3) size check (Codex F1): the exact enumeration reproduces calc T9 for the null N1 at n = 30 and 41 (t-test size 0.123 / 0.066); (4) sign-flip and Wilcoxon are recorded as sensitivity and never change a decision; (5) IUT and Holm; (6) `spearman_perm` permutes over rounds; (7) L/H with `unknown_fault` |
| T-CELLS-1..3 | cells | `_replay` serves logical calls in order (two-call cell under REEXECUTE does not pause); stored precheck read back; structural-zero sharing links `shared_with` |
| T-CELLS-4 | cells | (Codex F13) a cell with a frozen transport resend (calls.py:268-279) + a two-call repair, replayed under REEXECUTE: exactly 2 logical replies served in order, never a resent transport reply; `logical_calls` persisted; ledger accounting still counts every send |
| T-TRAJ-1 | trajectories | `landmark_view(trajectory)` returns nothing for episodes that end before step 10 or are infrastructure-censored, else exactly 10 nonterminal steps with terminal observations and won/done flags removed (Codex F10) |
| T-REG-1..5 | registry | states forward only; conflict across units; redo reuses own registration; release returns items; root-independence |
| T-REG-6 | registry | (owner rule 22:3x) per-chain namespaces: an item consumed in chain D is dispatchable once in chain G; a second unit of the SAME chain → `ConsumptionConflict`; `smoke` items absent from both chains' supplies |
| T-SUPPLY-1..6 | supply | SearchQA tail builder never emits positions < 4,001 and checks A–D hashes; ALFWorld room grouping disjoint across run/accept/select; slices consecutive; smoke items removed first; ALFWorld ids in the `alfworld-xs:` namespace never equal a pool id and the pre-reset touches only the cut slices; ≤ 5 games per room per slice; LiveMath formal slices = run 54 meta-absent + 65 meta-present, J7 probe 64 meta-present (`accept_probe`), acceptance 100 meta-absent |
| T-REPLAY-1..4 | replay | fixed property kinds only; non-vacuity (property false when withheld); negative tests; reference-tracker agreement computed |
| T-DET-1..3 | detectors | masked views hide answer content/run status/step count; residual metrics; Jaccard dedup; a `len(steps)==50` detector is not accepted |
| T-DET-4 | detectors | synthetic ALFWorld set where every failure runs 50 steps: residual cells defined by `MECHANICAL_MASKED` on the 10-step landmark view still contain failures; a view-only detector with real lift on residual cells CAN be accepted; a `len(steps)==50` detector still cannot (check C2) |
| T-DET-5 | detectors | landmark task (Codex F10): short successful episodes (won before step 10) and early `done` episodes are excluded from validation and counted by outcome; infrastructure-censored episodes excluded; a detector keyed on terminal text ("You won") cannot fire on any included view |
| T-DET-6 | detectors | (Codex F11) ALFWorld halves split by room, < 8 rooms per half → `undecidable`; candidates hashed before the hold half is read (a changed candidate → refusal); Holm over ≤ 3 candidates at family level 10%; Jaccard computed on the full masked hold half before residualisation |
| T-GEN-1..5 | generators | (Codex F8) (1) OfficeQA family reference functions (difference, ratio, percent change, named-cell sum) recompute the answer from the perturbed cells; an examiner output carrying an answer field is rejected; (2) LiveMath: the fixed checker solves each instance independently (sympy on the problem structure), single matching option, no meta option, key balance; (3) Sheet: semantic truth recomputed by the recalc engine from formula-defined edits, THEN engine qualification as a separate check (with FakeNative); (4) ALFWorld null selector; (5) a bench without a registered family → `selection_only`, no generated truth |
| T-RES-1 | research | (owner rule 22:3x) frozen sources only: Wikipedia requests carry exactly the frozen parameters (research.py:135-143) through the explicit proxy, any other host refused; an archive file whose sha256 differs from `index.json` → refusal on open; disambiguation and "Jeopardy" pages dropped (also after a redirect) |
| T-RES-2 | research | every result list and page archived write-once by hash BEFORE use (a second write with other content fails); a quote that is not verbatim (whitespace-normalised) in its archived page voids the finding (`quote_not_verbatim`) and the request goes on |
| T-RES-3 | research | call ceilings: ≤ 3 rounds × ≤ 3 queries, ≤ 3 pages, ≤ 8 calls (an invalid reply consumes its call, never retried; a round starts only while 3 calls and a page fit); ≤ 24 requests per step and bench; requests carrying benchmark item text are refused before dispatch; findings split G_self / G_acc by seed, disjoint, hashed before the engineer step |
| T-GEN-6 | generators | (owner rule 22:3x) a family builds items ONLY from qualified findings (none → `no_material`, zero items, recorded); truth recomputed by the fixed reference function even when a finding states a number; ≤ 10 items per finding |
| T-VAL-1..4 | validity | (Codex F9) one evidence unit per acceptance round (one `d_gen`/`d_real` pair for S'−S; within-round covariance reported); < 8 rounds → `not_evaluable` whatever the disagreement; refuted = ≥ 8 rounds and [≥ 2 rounds with \|d_gen − d_real\| > 2 pooled SE incl. covariance, or the duplicate pair's 95% CI on generated items excludes 0]; validated = ≥ 8 rounds, not refuted, Spearman > 0 with permutation p < 0.05 over rounds (10,000, seed 20261021), duplicate CIs contain 0 on both sets; all else `not_evaluable`; precedence refuted > validated > not_evaluable |
| T-ACC-1..8 | acceptance | (1) sealed inputs immutable (incl. the donor-corpus sha); (2) J1/J2 by `paired_t` on synthetic cell tables, J5–J7 as before; (3) J3 = fault items of A (S' and P_y, any run, routing or execution, planning faults included) / \|A\| at the calc T10 boundaries (Codex F22); (4) J4 compares item counts with margin max(2, ⌈0.02\|A\*\|⌉) (2 up to \|A\*\| = 100, 3 at 150); (5) harmful-sham rule → S'−S only at 2.5%, report wording "content/effort explanation not excluded"; second-call rate difference > 10 points flagged (Codex F5); (6) revision/deletion/narrowing estimands and restoration twins (Codex F6); (7) \|A\*\| < 30 or ALFWorld < 20 rooms → `decision: "not_run_small_astar"`, S' archived, S passes on, items released `routed_not_dispatched`, nothing consumed (Codex F1); (8) every decision carries `evidence_kind: "selection"` (Codex F2) |
| T-EVAL-1..3 | evaluation | consent key set exact; multi-arm unit; `unseal` refuses without `owner-continuation.json`; with `continue` and no formal-chain addendum hashed before the unseal, every later read is labelled `repeated_test_development` (Codex F17) |
| T-EVAL-4 | evaluation | (Codex F16) sealed evaluation records hold hashes, judge tokens and flags only — a raw prediction or receipt anywhere outside `<attempt>/transient/` fails; the transient store is deleted after scoring (incl. re-execution) and its deletion-manifest hash recorded |
| T-EVAL-5 | evaluation | canary scan over every artifact before sealing: a planted test-content canary string in any file → sealing refused; a clean tree → `canary_scan.json` with `hits: 0` |
| T-QUAL-1..2 | qualify | (Codex F15) the copied record closure stamps `fivebench-execskill-v1` (never `fivebench-coevolution-v3`) while scoring through the frozen helpers; v3 qualification records enter only through `IMPORTABLE` with their original hashes |
| T-STEP-1 | step/protocol | maximum schedule enforced (Codex F18): a 4th edit rejected, a 3rd twin per item never planned, a 4th band probe or a 3rd self-test pass refused; the caps in `protocol.py` equal calc T6 |
| T-CHAINS-1 | step/chain | (owner rule 22:3x) one manifest, chains G and D: separate ledger scopes (`G:` / `D:`), separate caps, separate consumption namespaces, the SAME slice items; never two SpreadsheetBench units at once and never SB with ALFWorld across chains; chain G's post-first-run-unit cap check pauses chain G only |
| T-READ-1 | readout | label priority table (harmful elsewhere > general > home-only benefit established > cannot act elsewhere > no measurable effect) applied as descriptors, not exclusive (Codex F21); selection vs independent generalization evidence wording (Codex F2); code-vs-text readings only with the registered bounds, else `inconclusive` (Codex F20) |
| T-SMOKE-1 | smoke | (Codex F19) `smoke-summary` enumerates control receipts (S1-e, fault drills) and excludes them; S1 probe receipts (probe-only M/B) form their own listed class, are never counted as production and must be leak-free; the production criterion needs ≥ 300 production-configuration receipts (registered body, M and B) with zero reasoning leaks; frozen-path resend receipts counted separately, also zero leaks; S1-e not judged `reasoning_mismatch` → fail |
| T-EXCL-1 | exclusion | exclusion-consent key set exact; `exclude_tests` and `alfworld_test_identity` refuse without the file (and refuse the test-read consent in its place); output holds counts and hashes only, never item text |
| T-MAN-1..2 | manifest | verify_code refuses a changed file; environment fields present |

### 8.2 End-to-end zero-API chain test (`tests/test_execskill_e2e.py`)

A two-bench pilot (SpreadsheetBench fixtures → ALFWorld fake games, and SB → OQ fixtures) on a temporary root with FakeSolver (per model), FakeGLM, FakeResearch,
FakeDocker, FakeAlfEnv, FakeNative, run as the TWO chains G and D (owner rule 22:3x; SB → OQ is the binding pilot): run → diagnose → research (archive write-once, verbatim quotes, call ceilings) → generate (families consume only qualified findings) → engineer (one valid change, one leaking change dropped, one crashing change
dropped) → selftest → accept (A\*, donor corpus, P_y, P_i, twins incl. a restoration twin, G_acc, S_dup) → decision → freeze (describer) → multi-arm test read
with structural-zero sharing (evaluation store: hashes only, transient store deleted, canary scan) → sealed → owner continuation file +
formal-chain addendum → unseal → readout tables. Assertions: every record versioned; chain G and chain D records carry their chain, scopes and consumption namespace, and both chains dispatch the same slice items without `ConsumptionConflict`; registry states; ledger
reservations == settlements; no test text in any training-side artifact; the decision is reproducible from cell records alone (re-run
`decide` → identical JSON).

### 8.3 Break-the-code checks (must FAIL loudly when the code is sabotaged)

Run as a separate job (`tests/test_execskill_mutations.py`): each mutation is applied to a temp copy and the named test must fail —
(1) shell appends text to the delivered reply → T-SOLVER-2; (2) router reads `private` → T-ROUTE-3; (3) placebo forgets the header → T-PLACEBO-3;
(4) registry allows re-dispatch → T-REG-2; (5) `_replay` replays only the last logical call → T-CELLS-1; (6) Endpoint built with M instead of B → T-LEDGER-2;
(7) canonicaliser searches the whole reply → T-CANON-2; (8) detector view includes step count → T-DET-1; (9) v2 can turn a pass into a fail → T-JUDGE-1;
(10) consent accepts extra keys → T-EVAL-1; (11) worker child keeps stdout → T-SBX (print); (12) ALFWorld view keeps `infos.extra` → T-SOLVER-8;
(13) residual cells use full-episode mechanical categories → T-DET-4; (14) an episode-slot wait maps to P4 → T-SLOT-1; (15) exclusion runs accept the
test-read consent → T-EXCL-1. Codex-round mutations: (16) v2 reads the JSON when a usable tag exists → T-JUDGE-5; (17) preflight reads
the last receipt → T-OUT-4; (18) every close checks the whole `execskill-sbx-` prefix → T-SBX-13; (19) the evaluation store keeps raw replies →
T-EVAL-4; (20) qualify stamps v3 → T-QUAL-1; (21) placebo content computed from acceptance items or after dispatch → T-PLACEBO-6; (22) the
landmark view keeps the terminal observation → T-TRAJ-1/T-DET-5; (23) `_replay` serves a resent transport reply → T-CELLS-4; (24) J1 decided by
the sign-flip p → T-STATS-4; (25) S1-e counted as a production receipt → T-SMOKE-1; (26) the router plans a third twin per item → T-ROUTE-5. Owner-rule mutations (22:3x): (27) the research sources accept a non-frozen host or a changed archive file → T-RES-1; (28) a family builds items without a qualified finding → T-GEN-6; (29) chains share one consumption namespace or unprefixed scopes → T-REG-6 / T-CHAINS-1; (30) `solver_client("glm-5.3")` adds a route or `thinking: disabled` → T-CLIENT-6.

## 9. Build order: 5 batches, parallel agents own DISJOINT files

Each batch ends with its unit tests green on dl in `/data/execskill-dev`
(`/root/continual-alf-prep-20260928/env/bin/python -B -m pytest -p no:cacheprovider`; offline, fakes only) and ONE Codex review round per
batch on the pulled Mac mirror (memory: stepwise Codex review, one round per item). Agents edit files only in `/data/execskill-dev` (over
ssh), never in `/data/skillopt-work` (not a git repo; holds a `.env`; never an rsync source). File ownership is exclusive inside a batch; later batches may import earlier modules but never edit them (a needed
change goes back to the owner of that file as a fix ticket).

| Batch | Agent | Owns (files) | Depends on | Done when |
|---|---|---|---|---|
| B1 foundations | A1 | `protocol.py`, `errors.py`, `budgets.py`, `slots.py`, `__init__.py`, `tests/test_execskill_protocol.py`, `tests/test_execskill_budgets.py` | frozen coevo5 | T-ID-1, T-LEDGER-*, T-SLOT-1..2 |
| | A2 | `client.py` (incl. `solver_client(model)`, owner rule 22:3x), `tests/test_execskill_client.py`, `tests/execskill_fakes.py` (FakeSolver per model, FakeGLM parts) | — | T-CLIENT-1..6 |
| | A3 | `package.py`, `policy.py` (also generates `sandbox/policy.json`), `notes.py`, `compute.py`, `canonical.py`, their tests | — | T-PKG-1..5 (incl. `edits`/`restore`), T-POLICY, T-NOTES, T-COMP, T-CANON |
| | A4 | `registry.py`, `supply.py`, `exclusion.py`, their tests, fixture item builders `tests/fixtures/execskill/*` | — | T-REG (incl. T-REG-6 per-chain namespaces), T-SUPPLY, T-EXCL-1 (exclusion tested with a fake TestAccess) |
| B2 sandbox + shell | A5 | `sandbox/worker.py`, `sandbox/client.py`, `sandbox/__init__.py`, FakeDocker in `tests/execskill_fakes_docker.py`, `tests/test_execskill_sandbox.py` | B1 (policy, slots, errors) | T-SBX-1..13 with FakeDocker (incl. two live workers) |
| | A6 | `solver.py`, `router.py`, `precheck.py`, `precheck_worker.py`, `tests/test_execskill_solver.py`, `tests/test_execskill_router.py`, FakeAlfEnv/FakeNative in `tests/execskill_fakes_env.py` | B1; sandbox client interface (stub until A5 lands) | T-SOLVER-1 (two-projection equivalence) first, then T-SOLVER-2..9 (incl. the text arm), T-ROUTE-1..5 |
| | A7 | `judge.py` (v2 precedence), `outcomes_ext.py` (incl. the copied preflight), `stats_ext.py`, their tests | B1 | T-JUDGE-1..5, T-OUT-1..5, T-STATS-1..7 |
| B3 cells, units, rounds | A8 | `cells.py` (logical-call replay, `store=`), `units.py`, `rounds.py`, `trajectories.py` (incl. `landmark_view`), their tests | B1, B2 | T-CELLS-1..4, T-TRAJ-1, guard/balance tests |
| | A9 | `placebo.py`, `donors.py` (new, Codex F4), `acceptance.py`, `validity.py`, their tests | B1, B2 (router, sandbox client), A7, A8 (trajectories) | T-PLACEBO-1..6, T-ACC-1..8, T-VAL-1..4 |
| B4 method roles + examiner | A10 | `engineer.py`, `replay.py`, `describer.py`, their tests | B2, B3 | C1–C9 pipeline on fixtures; T-REPLAY |
| | A11 | `detectors.py`, `examiner.py`, `generators/*` (incl. `generators/families.py`, Codex F8), `research.py` (owner rule 22:3x: copy of `coevo5.research`), `tests/execskill_fakes_research.py` (FakeResearch), their tests incl. `tests/test_execskill_research.py` | B2, B3 | T-DET-1..6, T-GEN-1..6, T-RES-1..3 |
| B5 orchestration + ops | A12 | `step.py`, `chain.py`, `evaluation.py` (persistence adapter, canary scan, addendum check), `qualify.py` (copied record closure), `readout.py`, their tests, `tests/test_execskill_e2e.py` | B1–B4 | T-STEP-1, T-CHAINS-1, T-EVAL-1..5, T-QUAL-1..2, T-READ-1, e2e chain test green (chains G and D) |
| | A13 | `manifest.py`, `prelaunch.py`, `smoke.py`, `scripts/run_execskill.py`, `tests/test_execskill_manifest.py`, `tests/test_execskill_mutations.py`, ops scripts under `/data/execskill-20261021-ops` (written on dl only at launch time) | B1–B4 | T-MAN, T-SMOKE-1, mutation suite (1)–(30), `smoke-make` dry run with fakes |

Integration gates between batches: (i) after B2, T-SOLVER-1 equivalence (two registered projections) must pass against the frozen `backends.solve` on all five benches
(ALFWorld: on episodes whose every reply is `how == tag_exact`; T-CANON-4 covers the canonicaliser); (ii) after B3, a fake acceptance round
reproduces its decision from cell records; (iii) after B5, the e2e test and the mutation suite pass in a fresh `git clone` of
`/data/execskill-dev` on dl (memory: GitHub publish convention — clean-clone tests first). Docs: update `docs/current-workflow.md`,
`docs/results-and-lessons.md` (pending results only, no claims), and `docs/project-status.md` per AGENTS.md when the code lands.

## 10. Smoke specification for dl (operational)

Pre-conditions: owner decisions #1–#10, the design-v0 deviation items #23–#30 and the Codex-round items #31–#32 of REG §14 taken at their defaults by the owner (2026-10-21 22:3x): pilot SB → OQ as two chains G and D; leftover D3/D14
workers left alone, the leftover check excludes them by command line and records "cannot judge" (#3); branch `research/exec-skill-coevolution` committed in `/data/execskill-dev` on dl (owner approval for any push); the
owner's exclusion consent (`exclusion-consent.json`, §2.10) written before the S0 test-exclusion runs.

1. **Snapshot (dl-local).** From the build tree on dl: `rsync -a --exclude='.env*' --exclude='.git' --exclude='__pycache__'` of
   `skillopt/ scripts/ tests/` from `/data/execskill-dev` to `/data/execskill-20261021-source`; write the sha256 list of the source tree,
   recompute it on the copy and compare the two lists with `cmp`; `find /data/execskill-20261021-source -name '.env*'` must print nothing.
   Never edit the snapshot afterwards. The manifest `provenance` records the build-tree path, its git HEAD sha and the sha of the sha256
   list (§2.9). `/data/skillopt-work` is never an rsync source. The Mac mirror is pulled FROM dl (`git pull` or rsync) for Codex review and
   GitHub publication only.
2. **Connectivity** (AGENTS.md; docs/project-status.md §6.2; Codex F24): the exact alias `ssh PJ-CL4MIND-DULIN` first; only if it fails,
   `ssh -O check PJ-CL4MIND-DULIN` to tell a working ControlMaster from a failed fresh handshake (a diagnostic with `ControlMaster=no`
   proves nothing); never terminate the user's master connection; then non-interactive `bash -ic 'proxy_on && …'` only where external
   access is needed; the solver client uses the explicit PJLAB gateway with `trust_env=False`; never print `.env`; `unset OPENAI_API_KEY
   OPENAI_BASE_URL` in every run script.
3. **S0 (zero calls)** in tmux `execskill-prep`: `python -B scripts/run_execskill.py sandbox-selftest`, pytest on the snapshot
   (`-p no:cacheprovider`), `import-texts`, `import-sheet-qualification`, `make-items --bench alfworld` (zero-call pre-reset only for the cut slices, ≈ 422
   games, 7–21 min estimated), `make-items --bench searchqa --dry-run` (counts only), `exclude-tests` (TestAccess under the owner's
   exclusion consent; counts + exclusion hash), `make-fixtures`, `smoke-make --root /data/execskill-20261021-pre`.
   Record measured view sizes, VSZ/RSS, native peak RSS (memory rule, §5), container start latency; write the registered limits into the smoke manifest BEFORE S1.
4. **S1 probe** (≤ 60 calls) on its OWN ledger root `/data/execskill-20261021-pre/probe/ledger` (cap 0.5M), separate from the smoke
   ledger used by S2–S4: S1-b/c/e use the registered B_probe = 32,768 (sequential; one reservation ≈ 141k tokens), the 8 concurrent S1-d
   calls use M = B = 64 (≈ 50k reserved in total) [calc T8]; a completion > B_probe halts only the probe ledger. First single call confirmed
   before any concurrency; then S1-a…f (REG §10). Branch E/N for B is decided here and written into the manifest; no later change.
5. **S2 solver smoke** (elucid only, owner rule 22:3x (c); tmux `execskill-smoke`, background on dl; sparse event-driven monitoring): arms C, X, P, twins × 2 runs on
   SearchQA 20 and fixtures OQ/LM/SB 20 each; ALFWorld trimmed to 6 games × 1 run × arms C, X, P (withholding twins on ALFWorld are
   exercised by the offline tests with FakeAlfEnv; the real twin drill runs in S4 on SearchQA); the pass criteria of REG §10 are computed
   by `smoke-summary` (counts, never scores of real items beyond the format share). Receipts are classed at dispatch (Codex F19):
   production-configuration receipts (registered body, M and B: the S2, S-N1 and S4 cells) vs probe receipts (S1-a…d, f: registered body
   with probe-only M/B, i.e. B_probe = 32,768 or M = B = 64 for S1-d, because B is set only by S1-b; listed, not counted, also leak-free) vs
   control receipts (S1-e and the fault drills, enumerated by cell id and excluded); the criterion needs ≥ 300 production-configuration
   receipts with zero reasoning leaks (≈ 1,290 planned production cells, 578 of them in procedure-free cells: S2's card arm and S-N1; calc T7); frozen-path resend receipts are counted separately and must also show zero leaks (T-SMOKE-1).
6. **S-N1 noise** (SearchQA 200 × two identical C arms × 1; ALFWorld 6 × 2), **S-E6 cost** — results replace REG §3.3/§9.1 assumptions
   via a written pre-pilot amendment if they move by > 25%. Before the pilot, S-E6 compares, for EVERY scope cap (REG §9.3, incl. the
   test-read cap), measured per-cell tokens × measured ledger/actual ratio × the MAXIMUM-schedule cell count of REG §9.2 (calc T4–T6, not
   the estimate) + one full next reservation R = 4 × (request bytes + 512 + B) (budget.py:283-314) against that cap (zero calls); any
   excess → v1.1 re-registration before the pilot. S-E6 checks per-cell cost only; cell counts come from the maximum schedule (Codex F18).
7. **S3 roles** (GLM ≤ 0.5M; the generation call first runs one research request on the frozen sources through the explicit PJLAB gateway —
   archive write-once, verbatim quotes, ≤ 8 calls; owner rule 22:3x (b)) and **S4 mini-step + resume drill** (inject `SandboxUnavailable` via a registered fault switch available only in
   the smoke root; owner-format `recovery.json` written by the operator as a drill, labelled `smoke`).
8. **Exit**: `smoke-summary` writes `smoke-result.json` (pass/fail per row); any fail → no pilot; amend to `fivebench-execskill-v1.1` with new
   directories and re-run the failed rows. On pass: `make-manifest` for `/data/execskill-20261021-pilot`, owner consent file, owner go.

Estimated smoke cost (estimates, `docs/handoff/execskill-calc-20261021.py` T7): S1 0.05–0.3M (own probe root, cap 0.5M); S2 1.9–5.7M
(of which ALFWorld 6 × 1 run × C, X, P ≈ 0.76–1.13M); S-N1 1.05–1.9M; S4 0.46–1.22M; smoke solver (S2 + S-N1 + S4) 3.4–8.8M under a
smoke solver cap of 14M (= 1.5 × high + one reservation, rounded up); GLM ≤ 0.5M of the 2M cap.

## 11. Open items the implementers must not decide alone

- Final sandbox limits (P, M, C, RLIMIT_AS, frame cap) come from S0 measurement and are written into the manifest before S1 (REG §2.6),
  together with the native-slot count (3, or 2 if the S0 native peak RSS > 2 GiB; §5 memory rule).
- Branch E/N for B (REG §4.1) is an S1 output; if N and any completion > B was seen in S1/S2, stop and ask the owner.
- The fixed reference tracker for ALFWorld (port of D3's hand tracker) is registrar code: its agreement threshold (≥ 97%) is registered, but
  its own correctness vs simulator facts was measured only on D3's traces (7,350/7,524 agreement for the learned tracker [FP F1, F6-F9]);
  any disagreement pattern found in S0 goes to the owner before the pilot.
- Lexicon contents per bench (REG §2.2) are registered at implementation time and frozen by sha before S2; changes after S2 need v1.1.
- Pilot order (owner #1) changes only which benches' slices are cut first; code must support both default and recommended pilots without edits.
- Owner 22:3x: the default pilot SB → OQ is taken and runs as two chains G and D. Chain G's per-cell cost is not measured before its first run
  unit (placeholder deepseek anchors, calc T11) and is checked zero-call after it (REG §9.3): a breach pauses chain G for the owner; implementers
  never raise a cap.
- Research budgets (≤ 24 requests per step and bench, ≤ 10 items per finding, sub-scope 4.6M) are registered (REG §7.2, calc T11); the archive
  contents (pages and sha256) are frozen before S0 and bound in the manifest (`Archive.index_sha256`, research.py:358-361).
