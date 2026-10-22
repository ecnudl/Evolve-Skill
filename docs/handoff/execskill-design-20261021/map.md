# Route B (executable-skill co-evolution): consolidated design-constraints map

Status: consolidation of the seven read-only maps, written 2026-10-21 ~17:40 HKT. I wrote only this file. I made no
model/API call, opened no test pool, and touched nothing on dl.

**Inputs.**
- The design: `scratchpad/execskill/design-v0.md`, the shape the owner approved on 10/21 at 16:4x.
- The seven maps in `scratchpad/execskill/understand/`, cited by tag:
  - [SB] solver-backends.md
  - [CI] coevo5-infra.md
  - [CM] coevo5-method.md
  - [FP] feasibility-prototypes.md
  - [DP] data-and-pools.md
  - [LO] linux-ops.md
  - [SF] scorers-and-formats.md

  All scratchpad paths are under
  `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/`.

**Conventions.**
- Paths are repo-relative unless absolute. `dl:` means the Linux development machine.
- A tag such as [SB F12] names the map and fact that verified a claim.
- Status labels:
  - "verified": a reader read it.
  - "inferred": a reader's reading, or mine.
  - "unverified": no reader checked it.
- "(re-checked)": I grepped the local repo at ~17:30 and the line or value matched.

**Process note.** The relayed user request asked for a summary of the best-looking past results. That is a different
task, and this map does not address it. docs/project-status.md:14 records that the summary was made separately as
`docs/handoff/best-case-summary-20261021.md`. The file exists (17:21, 25,521 B); I did not read it.

## 0. Summary for the implementer (read first)

1. **What already exists.** Route B can reuse `skillopt/coevo5/` + `skillopt/continual_eval/` for running, scoring,
   interleaving and token accounting. Both trees are byte-identical to the frozen v3 snapshot
   `dl:/data/coevo5-20261019-v3-source-f` [CI F3, LO F21].

   **What does not exist:**
   - execution of model-written code: coevo5 has none (checks.py:3) and no sandbox;
   - a solver loop with hooks;
   - multi-arm test reading;
   - a fresh-batch reader with a consumption ledger;
   - scorer v2;
   - generated-item gates beyond "the truth is computed by a program";
   - a client route for `deepseek-v4.1-flash-1017`.
2. **New package and identity.** Route B must be a new package outside `skillopt/continual_eval/`, with a new protocol
   VERSION and new output directories. Importing a coevo5 module stamps records `fivebench-coevolution-v3-*` [CI F2].
   §2.0 gives the import-versus-copy rule.
3. **Blockers before registration:**
   - (a) There are 0 fresh real items for SpreadsheetBench and OfficeQA, the first two benches in design-v0's order
     [DP §5].
   - (b) Scorer v2 does not exist [SF F31].
   - (c) The new gateway did not enforce `max_tokens`: it returned 21 tokens at max_tokens 2 (docs/project-status.md:14).
     The ledger halts globally when `completion_tokens > max_tokens` (skillopt/coevo5/ledger.py:67, re-checked).
   - (d) There is no sandbox for procedures, predicates, detectors or generators [CI G1].
   - (e) Failure categories have no anchored label. Only pass/fail is anchored; categories come from a GLM diagnosis that
     sees the reference [CM §5.5].

## 1. What exists (one page)

Data flow of one v3 cell (verified by [SB], [CI], [CM]):
```
manifest.load (manifest.py:116-151) -> units.Setting (units.py:50) -> units.run_unit (units.py:126; lock, attempt-N, Pause)
 -> step.run_round (step.py:105-121; every arm x item x run job in ONE seeded shuffle, one thread pool)
  -> cells.run_cells / run_parallel (cells.py:237-263; workers 16)
   -> cells.run_cell (cells.py:166; O_EXCL claim, write-once record)
    -> cells._solve (cells.py:122-136) -> backends.solve(bench, public, skill_TEXT, call=Recorder) (backends.py:364)
         system = base + contract + "Frozen skill guidance (use only where applicable):" + Skill  (backends.py:379-394)
         user   = json.dumps(public view) (backends.py:417); ONE call for QA/Sheet; ALFWorld one call per step (:715-783)
         Sheet: program extracted (code_delivery.py:21), run in docker once per input case INSIDE solve (:437-452)
      -> Recorder (calls.py:261-279; <=2 resends, 300 s apart) -> Endpoint.send (calls.py:150-221; slot, reservation,
         request sha256 only) -> weak_solver_probe.Client.call (scripts/weak_solver_probe.py:227-345; httpx,
         trust_env=False, <=4 attempts) -> ledger.settle (ledger.py:51-72) -> budget.Budget (events.jsonl, scopes, halt)
    -> backends.score (backends.py:517) -> outcomes.classify (outcomes.py:185) -> record {final (token), official}
 -> stats.bounds / total (stats.py:19-37; L/H) -> gate.verdict (gate.py:100-128)   |   readout.Readings (test sets)
Test reading: chain.py starts one child process per bench (chain.py:153-224) -> evaluation.evaluate (evaluation.py:321;
 ONE arm per unit) -> test_tasks (evaluation.py:227; consent.json, TestAccess, write-once registry, Sheet test qualification)
```

**Method layer (v3, text rules).**
- Every role is GLM-5.3 through `roles.Roles.ask`, which accepts only a reply that is one JSON object (roles.py:92-117).
- `step.learn` (step.py:830-861) runs these units in order:
  - train;
  - prepare: halves, `examiner.revise`, `examiner.diagnose`, analyst, research, leakage, trigger sets;
  - selftest;
  - screen;
  - confirm;
  - composite;
  - merge.

  Sources: [CM F7-F13].
- Generated items exist only through `forward.build_panel` (forward.py:384-443), only for similar-placement rules, and only
  in OfficeQA or LiveMath style [CM F32-F37].

**Run layout** (v3, verified on dl [CI 3.10, LO F44]):
```
<root>/shared/{consent.json, baselines-checked.json, ledger/{.lock,events.jsonl,state.json}, slots/<pool>.<i>.lock,
               test/<bench>.json (write-once registry), host_only/diagnostics/*.log, host_only/specs/}
<root>/<chain>/{chain.json, .runner.lock, chain-complete.json | chain-terminated.json, s0/evaluation/<bench>/, s<k>/<unit>/}
<unit>/{unit.json (sealed once), .lock, attempt-<n>/{started.json, cells/<id>.{claim,json}, artifacts/<sha>.json,
        host_only/scorer_artifacts/<pos>/, status.json (paused), recovery.json (owner), roles.json, ...}}
```

**Ops** [CI 3.11, LO F23-F27]:
- Python is `/root/continual-alf-prep-20260928/env/bin/python` (3.11.16) [LO F3].
- Snapshot S = an rsync copy; integrity = a sha256 list made on the Mac compared with `cmp` against a list recomputed on
  dl.
- Prep runs pytest on S and the zero-call SpreadsheetBench engine qualification.
- Then: smoke, make-manifest, check-baselines, consent.
- Finally one tmux session per chain, `bash -i run-chain.sh`, which calls `proxy_on` and writes `EXIT` markers.

**Where route B plugs in.** Today the learnable object enters only as `skill_text` (backends.py:380, :732). Hook points
for a copied solver [SB §4 "Hook points"]:

| Hook | Location in the frozen code |
|---|---|
| QA pre-call | after backends.py:391-394 (Sheet view :406-409), before `_response` (:417) |
| QA post-call | after :417-424, before extraction (:425-436) |
| Sheet after extraction | around the per-case `_native` loop (:433-450) |
| ALFWorld pre-call | view construction (:744-746) |
| ALFWorld veto | between action parse (:752-756) and `env.step` (:762) |
| ALFWorld post-step | after :762-764 |

## 2. Reuse plan per new module

### 2.0 The identity rule that decides import versus copy

**Importing stamps v3.** Every coevo5 module does `from .protocol import ...`, so an importing package gets v3's
constants. Its records are stamped `fivebench-coevolution-v3-*` at:
- cell (cells.py:222);
- unit (units.py:154);
- test-panel and evaluation (evaluation.py:199, :367, :396);
- sheet-qualification (qualify.py:124, :136);
- manifest (prelaunch.py:508, manifest.py:119);
- smoke (smoke.py:112, :129);
- chain (chain.py:275);
- report (report.py:413).

Source: [CI F2]. The cal-1 precedent imported the unchanged package and applied `dataclasses.replace` to the Setting,
so its records still say v3 (dl:/data/coevo5-20261020-cal1-ops/cal1.py:127-131) [CI F43]. AGENTS.md requires a new
version for new behaviour, so that pattern alone is not enough.

**Exception classes must form one set.**
- `cells.STOP_KINDS` (cells.py:45-46) and `units.run_unit` (units.py:149) map exception CLASSES.
- budget.py raises `skillopt.coevo5.outcomes.BudgetStop`, `AssumptionBroken` and `LedgerFailure` (budget.py:36).
- A copied cells/units must therefore import these classes from `skillopt.coevo5.outcomes`. The alternative is to copy
  calls+ledger+budget+outcomes+cells+units+evaluation+qualify together. Otherwise a budget stop is classified as a
  generic "exception" [CI §4 pitfall].

**Placement and pinned files.**
- Keep new code out of `skillopt/continual_eval/`. `core.source_identity` hashes every `skillopt/continual_eval/*.py`
  (core.py:89-102, re-checked), and `load_plan` refuses a changed identity (core.py:294-297) [SB F42].
- Do not edit pinned files. The v3 manifest pins every file under skillopt/ and scripts/, and `verify_code` refuses a
  changed pinned file (manifest.py:44-48, 71-81) [SB F42].

**Recommendation** (mine, derived from the facts above):

| Treatment | Modules |
|---|---|
| Import unchanged | budget, ledger, calls, outcomes, stats, checks, roles; `skillopt/continual_eval/{backends, code_delivery, sheet_*}`. These are protocol-free or use only universal constants: ledger uses CLIENT_ATTEMPTS 4 and RESERVATION_OVERHEAD 512; calls uses MAX_RESENDS 2 and a 300 s cooldown that the Endpoint constructor can override. |
| Copy with a new VERSION | cells, units, evaluation, qualify, manifest, the prelaunch helpers, smoke, chain, CLI |
| Copy without importing | the step.py primitives. Importing step pulls in analyst, examiner, forward, gate, research, roles and skill [CI 3.9]. |

### 2.1 Shell, router, procedures, format guard (solver side)

**Import unchanged** [SB 3.1]:
- From `skillopt/continual_eval/backends.py`:
  - functions: `score` (:517), `readiness` (:230), `_public_view` (:73), `_response` (:90), `_sheet_preview` (:342),
    `_xlsx_bytes` (:285), `_native` (:153), `_runtime_limits` (:119), `_image_ready` (:132), `_new_alfworld` (:666),
    `_AlfSession` (:605), `_alf_post_observation` (:701), `_completed_without_text` (:475), `_prediction_unknown`
    (:69), `_layout_supported` (:359);
  - constants: `LIVEMATH_CONTRACT` (:35), `SHEET_CONTRACT_V2` (:53-56), `CONTRACT_FIRST_LAYOUT_V2`,
    `CODE_EXTRACTION_VERSION`, `SHEET_PREVIEW_VERSION`, `ALFWORLD_TRACE_VERSION`, `MAX_RESPONSE` (:30-56).
- `code_delivery.extract_python` (code_delivery.py:21).
- The task-card-only arm can call frozen `backends.solve` with the v3 RUNTIME and a task-card Skill text: that
  reproduces v3's prompts byte for byte [SB U2].

**Copy and parameterize:**
- Copy `backends.solve` (:364-455) and `_solve_alfworld` (:715-783) into a new module, e.g.
  `skillopt/execskill/solver.py`, with explicit hooks at the §1 points. Add an equivalence test: with no procedure
  enabled, every `(system, user)` pair (`calls._request_hash`, calls.py:125) and the prediction must equal frozen
  `backends.solve` [SB §4].
- D3's `tracker_episode` (dl:/data/feasibility/D3/r3/pilot_alf_glm.py:205-255) is the only working shell template. It
  carries four pilot-specific assumptions, so do not adopt it verbatim [FP G2]:
  - it is pinned to the v3 snapshot path;
  - it uses max_tokens 512;
  - it asserts a scaffold digest;
  - it imports model code in-process with `importlib`.
- D3's `parse`/`canonical` (pilot_alf_glm.py:165-195, about 30 lines) can serve as the ALFWorld action guard, but only if
  it is registered for EVERY arm [FP R4, F22]. Whether to use it changes the sign of the tracker effect [FP Q2].

**Write new:**
- The package format: procedure code, applicability predicate (code), description, replay tests.
- A router that runs every predicate per item and per step and logs fired / not fired. Store the activation log inside
  the prediction dict: cells.py:187 stores the whole prediction by hash, but `_prediction_summary` keeps only
  status/reason/cases (cells.py:108-112) [CI G3].
- Three hook kinds: context rewrite, deterministic compute, veto. Veto and compute were never prototyped [FP G1].
- Multi-call QA with usage summed per call. Today costs are `{"calls": 1}` (backends.py:417) [SB G1].
- A second call needs either a re-packed user string or a new multi-message client identity: the client is single-turn,
  `[system, user]` (weak_solver_probe.py:259-266) [SB G2].
- SpreadsheetBench execution feedback needs its own `_native` call and its own slot policy. `on_reply` takes a native
  slot after EVERY reply, which risks deadlock on the 3-slot pool (cells.py:127-129; calls.py:77-90) [SB G3].
- A new trace format holding per-step view, raw reply, admissible commands and shell decisions. Today's trace has none
  of these (backends.py:757-764) [SB F24, G8].
- A size and cost bound for injected context. `MAX_SKILL_BYTES = 20000` (protocol.py:48, re-checked) bounds only text,
  and ALFWorld resends the prompt every step [SB G9].
- A placebo procedure that takes the same slot and makes the same number of calls [CM 4.2 #6].
- An input whitelist: procedures see only `public` plus the frozen view keys. Never `private`, never
  `infos.extra.expert_plan` or `infos.extra.gamefile` [SB F22, K5].

### 2.2 Sandbox for model-written code (procedures, predicates, detectors, generators)

**Import unchanged:**
- The pinned native image `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd` (tag
  `evolve-skill-native:smoke-20260928`). Its build import-checks openpyxl, pandas, numpy and sympy. Repo pins: sympy
  1.13.3, pandas 2.2.3, numpy 1.26.4, openpyxl 3.1.5 (skillopt/continual_eval/runtime/requirements-native.txt:4-10)
  [LO F29-F30, SF F25].
- `calls.Slots` for a sandbox pool [LO F12].

**Copy and parameterize:**
- The hardened `docker run` flags and forced cleanup of `_native` (backends.py:153-212: `--network=none --read-only
  --user=65534:65534 --cap-drop=ALL ...`, then `docker rm --force`), paired with a route-B worker. `native_worker.py` is
  SpreadsheetBench-specific, discards stdout/stderr and reports only the exception class (native_worker.py:86-115)
  [SB F13, LO F31].
- D3's replay container flags (FD/D3/result.json:12: `--pids-limit=64 --memory=1024m --cpus=1`, image `b8fe4ce3655e`) and
  the `lt_replay.py` contract [FP F10].
- D6's `sandbox_runner.py` RESULT contract and import whitelist (dl:/data/feasibility/D6/pilot/sandbox_runner.py:14-56).
  It is only a host-process guard (exec/eval stay available), so it must run inside a container [FP F33, G5].

**Write new:**
- The worker protocol: input = public view + procedure source; output = bounded JSON; deterministic. It should return
  the exception class AND its message, so the engineer gets usable feedback.
- Per-call timeout and memory limits.
- A determinism check: a re-execution must reproduce identical requests (cells.py:144) [CI G16].
- A decision between a container per call, a long-lived container per episode, and a restricted in-process runner.
  Container start cost is unmeasured, and 6 ALFWorld + 3 SpreadsheetBench + recalc already compete for 7 CPUs [LO §5].

### 2.3 Engineer role (writes and revises procedures)

**Import unchanged:**
- From roles.py:21-142: `roles.Roles(endpoint).ask(role, system, user, *, label, check=None)`, `.plain`, `.count`; the
  validators `parse`, `fields`, `text`, `items`, `fit`, `message_bytes`; and `Invalid`.
- The role settings: GLM-5.3, temperature 0, reasoning low, ROLE_MAX_TOKENS 16384, read timeout 900 s, ROLE_INPUT_BYTES
  220000 (protocol.py:30-32, :245) [CM F1-F5].
- The answer views `examiner.task_view`, `answer_text`, `reference` and `step.answers`/`answer_of` (step.py:228-254).
  They carry `private` (step.py:251, re-checked), so strip it before anything is passed toward procedure code
  [CM F10].

**Copy and parameterize:**
- `analyst.payload`, `propose`, `_check`, `_row`, `evidence_problem`, `deduplicated` (analyst.py:125-276), turned into
  code fields, with per-row validation and `ANALYST_ATTEMPTS = 2` kept.
- `SELFTEST_SYSTEM`/`_revisions` (step.py:405-443) as one "fix or drop" round.
- `leakage.Corpus`, `findings`, `mechanical`, `adjudicate` (leakage.py:62-291), applied to the description, every string
  the procedure injects and the code's literals.

  Sources: [CM 4.1 #9, 4.2 #8-#10].

**Write new:**
- A code-inside-the-reply convention robust to JSON escaping. The v3 analyst needed a second attempt in 3 of 10 stages,
  and D13 found 21 of 49 proposals died of small faults [CM §5.2].
- AST extraction of literals, regexes and dict keys for the leakage check.
- A replay-test runner on the D3 pattern: zero solver tokens, 2.8 s for 7,524 steps [FP R1].
- Checks for "zero crashes on all trajectories" and "the format guard is untouched".
- Call ceilings for code-writing roles. The D3 tracker came from one call of 4,986 tokens [FP F1].
- Note: replay proves determinism and the absence of crashes, not repair [CM §5.9].

### 2.4 Examiner role (detectors, generators, generation policy)

**Import unchanged:**
- `TAXONOMY` (protocol.py:146-219) as the initial failure classes [CM F25].
- `forward.evaluate`, `literals`, `rounded`, `identity` (forward.py:196-231) as the exact-arithmetic truth kernel
  [SF F27].
- `qualify.qualify` (qualify.py:85-131: two v7 scorings of the reference submitted as the answer) for any
  SpreadsheetBench item set [SF F24].

**Copy and parameterize:**
- The examiner's acceptance discipline (examiner.py:267-309, :417-421): the panel is fixed before judging, an invalid
  verdict counts as wrong, and both a minimum gain and a minimum net count are required. Reuse it for detector
  precision/recall on held-out trajectories [CM 4.2 #7].
- The forward drop accounting (`DROPS`, counts, per-round records; forward.py:53-54, 384-443) for generator gates.
- D6's `gen_livemath2.build` and `run_program_check` (dl:/data/feasibility/D6/v2/gen_livemath2.py), with the critic's
  fix: "the independent program must be one of the agreeing pair" [FP F27, G4].

**Write new:**
- Detector code with a sandboxed runner that gets no reference at run time.
- A label source. Only pass/fail is anchored; categories come from a GLM diagnosis that sees the reference
  (examiner.py:481-498) [CM §5.5].
- Per-bench generators:
  - OfficeQA perturb-and-recompute needs a table extractor over Treasury page text. There is no cell grid, and
    `forward._office` assumes Wikipedia tables (forward.py:255-276) [SF G5].
  - LiveMath symbolic variants follow D6's rules: balanced key letters, exclude integrals/series sympy leaves
    unevaluated, validate numerically at 50 digits [SF G6].
  - SpreadsheetBench synthetic workbooks need cached answer values, then a qualification run [SF G7, R5].
  - ALFWorld "new environments" means choosing unused existing `game.tw-pddl` files. No environment generator exists;
    the backend loads only existing files under `ALFWORLD_DATA` (backends.py:666-698) [SF F26, R9].
- A 20–80% saturation gate and a predictive-validity gate. Neither has code or a passing precedent [FP K4].
- The options-only shortcut probe (design-v0 §2 step 3).
- SearchQA paraphrase probes. Who certifies that the answer is unchanged is open [CM Q7].

### 2.5 Judge

**Import unchanged:**
- `backends.score` for all five benches [SF U1, F8]. This holds only if the shell emits today's prediction shapes:

  | Bench | Prediction shape |
  |---|---|
  | QA (SearchQA, OfficeQA, LiveMath) | the raw reply string |
  | SpreadsheetBench | `{code, cases}` |
  | ALFWorld | `{won, steps}` plus trace |

  Source: backends.py:436-452, :771-773.
- `outcomes.classify`, `preflight`, `Verdict`, `finalize`, `undelivered`, and the two-field cell record `final` +
  `official` (cells.py:221-230) [SF U2].
- `checks` with `last_answer` (checks.py:12-105) [SF F10].
- `code_delivery.extract_python`.
- The v7 SpreadsheetBench chain [SF U4]:
  - `sheet_numeric_adapter.score` (:87-151);
  - `sheet_recalc.evaluate_pair` (:579-615);
  - `spreadsheet_compat.evaluate` (:203-265).
- `scoring.lenient` (scoring.py:76-93), descriptive only [SF F9].

**Copy and parameterize:**
- `REQUIRED_FORMAT` (protocol.py:127-128, re-checked) into the new protocol, adding ALFWorld flags; today ALFWorld's
  entry is `()` [SF G4].
- The shape of `smoke.format_check`: 20 items, floor 9/10, margin 1/20 (smoke.py:71-77, 275-313) [SF U3].

**Write new:**
- Scorer v2 as a new versioned module; never edit `_score_answer_tag` or the env evaluators. Verdict = official pass OR
  JSON-extracted pass, so v2 ≥ official on every cell; make that a unit-test invariant. The E10-critic prototype computes
  this as `ja = max(st, ...)` [SF 3b.2].
- Per-bench format flags [SF 3b.4].
- Both the raw-reply score and the guarded-answer score, plus `guard_changed_answer`. A format guard that transforms the
  output is answer repair [SF R2].
- `numeric_equal_but_em_fail` for OfficeQA [SF R4].

### 2.6 Registrar (interleaved arms, paired statistics, acceptance, batch ledger)

**Import unchanged:**
- `stats.bounds`, `total`, `unknown_share`, `sign_test`, `bootstrap` (stats.py:19-56, re-checked). L counts unknown as
  fail for the candidate; H counts unknown as pass for comparators [CM F38].
- `calls.Slots`, `budget.Budget`.

**Copy (do not import step)** [CI 3.9]:
- From step.py: `run_round` (:105-121), `_order` (:79-80), `table_of` (:124), `shared_unanswered` (:139), `guard`
  (:150), `violations` (:160), `key`, `bench_of`, `pool_tasks`; about 100 lines in all.
- Change `arms` from Skill TEXT to a package, and hash the package at every identity site that hashes only text:
  cells.py:222, evaluation.py:356/366, step.py:825, chain.py:290 [FP F13, G3].
- `readout.Readings` with `holds_large`, `holds_small`, `noninferiority`, after parameterizing ORDER and the chain names
  (readout.py:103-142 are tied to ORDER) [CM 4.1 #4].

**Write new:**
- Version-level acceptance:
  - four arms (S', S, task-card only, placebo procedure) in one seeded, interleaved round;
  - mean paired accuracy against a registered minimum effect per bench;
  - multiplicity over 3 contrasts, which scales the MDE by about ×1.2–1.3 [DP §5].
- A write-once registry of consumed ids, written before dispatch.
- One seeded order per bench, cut into consecutive slices. Independent tags overlap by chance (29 / 18 / 60 items)
  [DP F6, §4.3].
- The D1 decision rule (FD/D1/result.json:8) is a usable template, but it accepted a placebo (+0.036) on the scaffold
  when replayed on cal-1 [FP F37, F41].

### 2.7 Step and chain orchestration

**Copy (VERSION-stamped):**
- `units.run_unit`, `complete`, `unit_path`, `cell_context` (units.py:126-157) [CI 3.5].
- The chain.py patterns (chain.py:153-314) [CI §4]:
  - evaluation in child processes with sealed stdout (`_child`, `launch_child`, `_failed_start`, `_status`);
  - terminal markers;
  - `terminate` only when idle;
  - the `_verified` code check before every stage.

**Generalize** [CI 3.3-3.5]:
- `units.Setting`'s v3 fields (regression, tolerance, rubrics, instructions, sources; units.py:49-75).
- `CHAINS` (units.py:37-46).
- `endpoints`/`solver_endpoint`, which use model-keyed `SOLVER_MAX_TOKENS` and `SLOTS` (protocol.py:327-331).
- The budget scope helpers: `step_scope`/`deepseek_scope` accept only the kinds learning and evaluation (budget.py:55,
  70).

**Write new:**
- The route-B step: run → diagnose → generate → engineer → selftest → accept → freeze → read the test sets.
- A new protocol module with `ORDER = ("spreadsheetbench", "officeqa", "livemath", "searchqa", "alfworld")`. v3's ORDER
  is built into the Skill render, step identity, regression keys, readout, smoke and research.rewrite [CM 4.2 #1].
- A stop rule for when the fresh supply runs out [DP §4.4].

### 2.8 Test reading

**Copy:**
- `evaluation.contained`, `consent`, `attempts`, `recovered`, `_next_attempt`, `test_tasks`, `_registry`,
  `_sheet_qualification`, `monitor` (evaluation.py:43-426) [CI 3.6].
- `data.TestAccess`/`test_panel` (data.py:232-239, 332-358).

**Generalize** [CI F24-F26, G5, G13]:
- `evaluate` runs one arm per unit (evaluation.py:376-378).
- `unseal` is keyed by task_id only (:451-454).
- Reuse is decided by the Skill-text digest alone (:366).
- `configuration()` digests only model + max_tokens + runtime (:308-311). Add the procedure-library hash and the
  shell/router/guard code hashes.
- `_own` is tied to the coevo5 package directory (:267).

**Write new:**
- A multi-arm, interleaved evaluation unit, with its own consent wording.
- Whether to read the test sets every step or once at the end is the owner's choice (design-v0 §3, cost).

### 2.9 Smoke and pre-launch

**Keep the pattern** (smoke.py:86-162, 316-337; prelaunch.py:463-474) [CI 3.12]:
- the sealed spec is the smoke's run id;
- a pre-launch ledger `<P>/ledger`;
- a unit-by-unit summary;
- `changed_since`.

**Write new:**
- An endpoint smoke [SB K2]. Confirm the first real responses and check:
  - `returned_model`;
  - prompt_tokens ≤ request bytes + 512;
  - completion_tokens ≤ max_tokens;
  - reasoning tokens;
  - one deliberately small-max_tokens request.
- The solver-equivalence test.
- A sandbox smoke.
- A zero-model qualification smoke of 5–10 generated SpreadsheetBench items [SF R5].
- An ALFWorld shell smoke.
- A format check under the new endpoint.

### 2.10 CLI and ops

**Copy:**
- The subcommand pattern of `scripts/run_coevo5.py:238-311` [LO §3]. The file itself cannot be reused: its VERSION,
  CHAINS and manifest keys are v3's.
- The ops skeletons prep / prep-launch / launch / run-chain / poll / show, with `EXIT` markers, the
  `tmux has-session` refusal and `bash -i` sessions [LO F24-F27].
- The credential-free recipe in linux-ops.md §7:

  | Item | Name |
  |---|---|
  | snapshot | `/data/execskill-20261021-source` |
  | ops | `/data/execskill-20261021-ops` |
  | run | `/data/execskill-20261021-run` |
  | manifest | `/data/execskill-20261021-run-manifest.json` |
  | tmux | `execskill-<arm>` |

**Write new:**
- A `probe` subcommand.
- `unset OPENAI_API_KEY OPENAI_BASE_URL` in every run script.
- `PYTHONDONTWRITEBYTECODE=1`.
- The `.env` leak check in the rsync dry run [LO §7].

### 2.11 Manifest, ledger, budget, client

**Import unchanged:**
- `budget.Budget` (declare / reserve / settle / halt / resume / snapshot) and the scope strings [CI 3.3].
- `ledger.reservation`, `settle`, `attempt_bound`, as long as the client keeps ≤ 4 attempts per call and the same receipt
  shape [CI F10].
- `calls.Slots`, `Endpoint`, `Recorder` [CI 3.1].

**Copy and parameterize** [CI §4]:
- From manifest.py: `FIELDS` (:34-35), the VERSION check (:119), `loaded_code` (:37, 51-61), `_clients` (:95-113; it
  routes only `deepseek-v4-flash`, :109), `pin_code`/`environment`/`verify_code` (:44-81) and `load` (:116-151).
- The prelaunch helpers `engine_runtime`, `qualify_training_sheet`, `ledger_of`, `prelaunch_budget`, `prior_usage`,
  `record_consent`, `role_client`.

**Write new:**
- A client for `deepseek-v4.1-flash-1017` [SB 3.3]:
  - subclass `weak_solver_probe.Client` WITHOUT calling `super().__init__`, which refuses models outside MODELS
    (weak_solver_probe.py:232-233);
  - set `backend = "elucid"`;
  - read URL and key by path from `/root/.config/weak-solver/elucid.env` with `_read_env`/`_validated_url` (:115-137);
  - leave `thinking = None`, so `_receipt` never marks `thinking_mismatch` (:295-296);
  - set `effort` according to the registered reasoning mode (`reasoning_effort: "none"` switched reasoning off in the
    probe, docs/project-status.md:14);
  - set `response_model_ids` to the echoed model id;
  - make an explicit, registered proxy decision;
  - record `completion_tokens_details.reasoning_tokens`.
- A new scope helper (kinds generation / selftest / acceptance / test, and per role) that keeps the `rooted` rule
  (budget.py:59-64, re-checked).
- New registered caps.

### 2.12 Data (fresh batches)

**Import unchanged** [DP §4]:
- `data.ranked` (data.py:173-176, re-checked) and the `pin`/`_checked` pattern.
- `pool`, for the leftovers: 45 SearchQA and 141 LiveMath items.
- `qualified`, `test_ids`, `TestAccess`, `item_hash`.
- The logic of `make_searchqa_fresh_sample.build` (scripts/make_searchqa_fresh_sample.py:39-101). Extending `--count`
  keeps the first 4,000 unchanged [DP F15].

**Write new:**
- A fresh-batch reader with a consumption ledger [DP §4.3].
- For SearchQA, an exclusion of test ∪ reserve (1,000) ∪ blocks A–D ∪ the pool. It reads sealed ids outside evaluation,
  so it must be registered [DP §4.2, F16].
- An ALFWorld items file (gamefile, id, task_type) [DP §4.7], with:
  - task-type stratification;
  - test exclusion by path, run with test access;
  - a new id namespace (not `train:NNNN`);
  - optionally, a zero-call qualification.

## 3. Hard constraints

### 3.1 Test isolation

**Access control:**
- Only evaluation creates `data.TestAccess(unit)` (evaluation.py:231; data.py:232-239).
- Test reading requires `shared/consent.json` with exactly {test_evaluation, sheet_test_qualification, by, date, note} and
  `by == "owner"` (evaluation.py:43, 152-159) [CI F23].

**Gaps in the existing firewall:** `_refuse_tests` (data.py:120-124) knows only the split's `test` part. It does not
refuse the SearchQA reserve (1,000 ids from the same HF validation split) or the sealed blocks C/D [DP §4.2].

**Sealed hold-outs, do not touch** [DP F10, F15]:
- SearchQA blocks C and D, 2,000 items (docs/handoff/active-evidence-learn-from-b-design-20261012.md:29).
- LiveMath evaluation blocks (project-status.md:119): e01 was read on 10/14 (inferred), e02 in part, e03–e08 unread.

**ALFWorld test set:** that it is `valid_unseen` is INFERRED (134 = TEST_SIZES). Never sample from it; verify with code
that holds test access [DP F13].

**What procedures, predicates, detectors and generators must never receive** [SB F22, CM F10]:
- `private`, which `step.answer_of` puts in every answer dict (step.py:251);
- in train mode, `infos.extra.expert_plan` and `extra.gamefile`
  (dl alfworld/agents/environment/alfred_tw_env.py:254, 263-266).

**Generators read only the training pool** [DP F11, §6.6]:
- OfficeQA train and test share 40 bulletins (current-workflow.md:56).
- dl lacks `treasury_bulletins_parsed/transformed`.

**In-sample hindsight:** D14's "55 of 57 objects on open surfaces" comes from training walkthrough METADATA, which the
solver never sees. A procedure built on it is in-sample [FP K3].

### 3.2 Frozen protocol identities

**v3 itself:**
- `VERSION = "fivebench-coevolution-v3"` (protocol.py:10, re-checked).
- The package constant still says v1 (skillopt/coevo5/__init__.py:8), but nothing reads it [CI F1].
- Locally, the coevo5 tree, the continual_eval tree, scripts/ and tests/ are byte-identical to
  `dl:/data/coevo5-20261019-v3-source-f`; only docs/ differs (as of ~17:06) [CI F3, LO F21].

**Git state:**
- `skillopt/coevo5/`, `scripts/run_coevo5.py` and `scripts/weak_solver_probe.py` are untracked.
- `skillopt/continual_eval/backends.py` is modified relative to HEAD (git status, re-checked).
- The new branch `research/exec-skill-coevolution` (docs/project-status.md:14) must carry these files.

**Output directories:**
- Use new directories only. `/data/execskill-ops/` and `/data/execskill-probe.py` belong to another agent's probe
  [LO F2].
- Route-B paths must be real paths: `safe_path` refuses any symlink component (continual_eval/core.py:35-39) [LO F45].

**Records and artifacts:**
- `qualify.load` refuses another VERSION (qualify.py:134-138). Reusing v3's 91-item training qualification needs an
  explicit importable-version list [CI F38].
- `write_json` is write-once: "Immutable artifact differs; use a new output directory" (validator_pilot/api.py:44-71)
  [CI F4].

**Snapshot hygiene:** pilots wrote nine .pyc files into snapshot f (FD/D6/critic-result.json:6). Always run with `-B` or
`PYTHONDONTWRITEBYTECODE=1` [FP F34].

### 3.3 Ledger and budget

**Reservation and halt** [CI F10]:
- A reservation is 4 × (request bytes + 512 + max_tokens) (ledger.py:26-36; protocol.py:278-279, re-checked).
- `settle` requires 1–4 attempts.
- A global halt (`AssumptionBroken`) fires when `prompt > bytes + 512` or `completion > max_tokens` (ledger.py:67,
  re-checked).

**The new gateway breaks the halt assumption.** It ignored `max_tokens: 2`: 21 tokens came back with finish "stop"
(docs/project-status.md:14; no reader saw the log itself). Consequences:
- one reply over the cap halts every chain's ledger;
- truncation cannot be read from `finish_reason`.

The PJLAB gateway was also seen adding about 90 prompt tokens to a one-sentence request (docs/project-status.md:201)
[SB K2].

**The ledger is a lower bound:** client-internal retries keep only the last attempt's usage [LO F9].

**Scopes:**
- `rooted` (budget.py:59-64): a call names either `overall` (GLM) or only `deepseek`-prefixed scopes.
- `step_scope` and `deepseek_scope` accept only the kinds learning and evaluation (budget.py:55, 70) [CI F11].

**Halt generation:** build one Endpoint per unit attempt. It takes the halt generation at construction, so after any
halt it refuses all later reservations, even after a resume (calls.py:145; budget.py:294-297) [CI F7].

**v3 caps and spend:**
- Caps: OVERALL_CEILING 1,170M; DEEPSEEK 430M; chain caps I-ds/E-ds 200M each, NoSkill-ds 30M; PRELAUNCH_CAP 30M
  (protocol.py:317-322, re-checked; prelaunch.py:131).
- Spend: 139,024,462 deepseek + 7,804,250 GLM tokens; 56,220 reserve/settle pairs; no halt [CI F13].
- Route B needs new registered caps. design-v0 estimates 60–100M for a pilot and 400–600M for the full run.

**Cost anchors per cell:**

| What | Tokens | Source |
|---|---|---|
| SearchQA, D1 fresh pilot | 1,531 | [FP F35] |
| SearchQA, cal-1 real (max_tokens 32,768) | ~3,400 | [FP F61] |
| I-ds stage-entry, LiveMath / SearchQA / OfficeQA / SpreadsheetBench | 3,969 / 4,088 / 7,927 / 4,273 | [FP F32] |
| E-ds stage-entry, same order | 1,251 / 1,236 / 4,690 / 2,010 | [FP F32] |
| ALFWorld episode, E-ds / I-ds (task card) | 28.5k / 105.7k | [FP F17] |
| ALFWorld prompt per step, E-ds / I-ds | 807 / 3,364 | [FP F17] |
| ALFWorld per call, tracker arm / control | 1,225 / 873 | [FP F2] |

**Slot pools are per root directory** (calls.py:39-122; manifest.py:149). Experiments with different roots do not share
provider concurrency limits [CI F6].

### 3.4 Endpoint and network

**Allow-lists.** `deepseek-v4.1-flash-1017` appears in none of [CI G8]:
- `MODELS` and `ROUTES` (weak_solver_probe.py:76, :88, re-checked);
- `SOLVER_MAX_TOKENS`, `SLOTS`, `DEEPSEEK_ROUTE` (protocol.py:327-331, re-checked);
- `manifest._clients` (manifest.py:109, re-checked);
- `units.CHAINS`.

**Reasoning** (docs/project-status.md:14):
- Reasoning is on by default, and `thinking: disabled` is not honoured.
- `reasoning_effort: "none"` switched it off in the 17:0x probe.
- 8 of 8 concurrent requests were delivered.
- The owner's line says to register the model as "optional reasoning, checked per call".
- The frozen route sends `thinking: disabled`. Any reasoning reply is then `thinking_mismatch`: two resends 300 s apart,
  then unknown (weak_solver_probe.py:295-296; outcomes.py:66-67) [SB K1].

**Proxy** [LO F15, F41]:
- The Client accepts only None or `GATEWAY = http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`
  (weak_solver_probe.py:71, re-checked), and it sets `trust_env=False`.
- The elucid host is not in NO_PROXY. Direct egress is untested.
- Any other proxy destination needs review (AGENTS.md).

**Shell environment on dl** [LO F18-F19]:
- Every `bash -i` shell runs `proxy_on` automatically and exports an unrelated `OPENAI_API_KEY`/`OPENAI_BASE_URL`
  (.bashrc:148-150).
- Plain non-interactive ssh loads nothing (.bashrc:6).

**Read timeout:** `READ_TIMEOUT_SECONDS = 2400` (protocol.py:92, re-checked) turned one upstream stall into a 51-minute
smoke unit. Register a timeout for this solver [LO F37].

**Credentials:** read only by path. elucid.env defines `ELUCID_CHAT_URL`, `ELUCID_API_KEY` and `ELUCID_MODEL` (mode 600,
no `export`). Never print the values [LO F17].

### 3.5 Docker and execution

**Machine:** dl has 7 CPUs, 15 GiB RAM and Docker 26.1.3 with data-root /data/docker. `/` is 71% used; `/data` has 395G
free [LO F1, F29].

**Images and qualification present** [LO F29, SF F25]:
- native `sha256:0a0a5dcb...0f0dd`;
- recalc `sha256:f7f6f598...c4d790`;
- python base `sha256:b8fe4ce3655e...`;
- the v7 qualification file, with the pinned sha256.

**v3 container settings** (backends.py:119-129, 169-178) [SB F12, F14]:
- values: 300 s, 4096 MiB, 1 CPU, `--network=none`, read-only, uid 65534;
- allowed ranges: 5–600 s, 256–32768 MiB, (0, 8] CPUs;
- containers are started with the docker CLI through subprocess; there is no docker SDK [LO F31].

**Host packages** [LO F5-F6, §4.9]:
- The host env lacks sympy, pandas, scipy and the docker SDK.
- sympy exists only in the image (pinned 1.13.3) or in D6's `--target` tree (1.14.0). Pick one and pin it.

**Slots:** `SLOTS = {glm-5.3: 10, deepseek-v4-flash: 12, spreadsheet-native: 3, alfworld-episode: 6}`
(protocol.py:331, re-checked). They are file-lock slots shared by every process that uses the same root
[LO F11-F12].

**Leftover processes:** about 21 orphaned D3/D14 spawn workers and 8 resource trackers (~2.7 GB) are still alive. They
make a "no leftover ALFWorld worker" check ambiguous [LO F39].

### 3.6 ALFWorld

**Environment** [LO F33, SB F21-F23]:
- `ALFWORLD_DATA` must equal the runtime path before launch. The run script sets it in-process
  (scripts/run_coevo5.py:75); the backend never sets it (backends.py:669-673).
- Each episode runs in its own spawned process. Runtime (protocol.py:355-356; backends.py:605-698):
  - queue timeout 60 s;
  - max_steps 50;
  - seed 42;
  - split "train";
  - trace version `alfworld-public-transitions-v1`.

**Prompt and action** (backends.py:744-762) [SB F19-F20]:
- The view is `{initial_observation, observation, admissible_commands, recent_history[-5:]}` (backends.py:744-746,
  re-checked).
- The action is the first `<action>` tag, otherwise the whole reply.
- An empty action or one over 1000 chars is `invalid_action_format`.
- Admissibility is never checked.

**Failures:** any exception in the loop becomes `alfworld_environment_error`: row 8, an infrastructure unknown, restarted
only if it happened before the first call. An infrastructure share above 1/10 pauses the unit (outcomes.py:298-303;
protocol.py:84) [SB K6].

**Games:** only existing `game.tw-pddl` files under the data root can be loaded [DP F13, SF F26]:
- train: 3,553 games, 3,514 of them outside the pool;
- valid_seen: 140 games, 122 outside the pool.

**Speed** [LO F36]:
- Training-side episodes take a median 290–348 s under contention, p90 up to 1,929 s.
- One ALFWorld test pass of NoSkill-ds took about 5.3 h.

**Action format:** in D14's frozen loop the provider wrote wrapper-form actions on 29–65% of steps. Whether the new model
does the same is unknown [FP F20, Q5].

### 3.7 Data freshness per bench (numbers from [DP §5])

| bench (design-v0 order) | pool | method-side never used | fresh real supply outside the pools (owner release needed) | design-v0 minimum effect | items needed per acceptance (1 run, paired, two-sided .05, power .8) |
|---|---|---|---|---|---|
| SpreadsheetBench | 120 (91 qualified) | 0 | none: Verified 400 fully placed; all_data_912 not on dl, not qualified | ~7 pts | 279–338 |
| OfficeQA | 74 | 0 | none: upstream 246 = 50 + 24 + 172 | ~10 pts | 75–102 |
| LiveMath | 283 | 141 | eval blocks e03–e08, 150 unread (sealed) | ~5 pts | 500–606 (at most 291 exist) |
| SearchQA | 600 | 45 (37 counting generator sources) | 11,380 never-sampled HF validation rows; blocks C/D 2,000 (sealed) | 3–4 pts | 712–1,112 (3 pts); 400–625 (4 pts) |
| ALFWorld | 57 | 0 | 3,514 train + 122 valid_seen games | ~10 pts | 109–134 |

**Reading the table** [DP F7-F9, §5]:
- "Never used" holds only on the method side. Every pool item was an input to the v1 baselines or to older learners.
- The MDEs are scaled from earlier test-panel estimates. Multiply by about 1.2–1.3 for Holm over 3 contrasts, and expect
  2–3x drift in discordance between time windows.

**D1's smallest certifiable effects at pool sizes** [FP F40]:
- SearchQA 0.042 (300 items × 2 runs);
- LiveMath 0.056 (233 × 2);
- OfficeQA 0.103 (37 × 4);
- SpreadsheetBench 0.122 (46 × 2);
- ALFWorld 0.153 (29 × 2).

More items buy more power than more runs.

**SpreadsheetBench cases:** every training task in both panels has exactly one input case [SB F16].

### 3.8 Scorer facts

**Official scorers per bench** (backends.py:491-563) [SF F3-F6, F21-F23]:

| Bench | Official rule |
|---|---|
| SearchQA | exact match on the last `<answer>` tag; without a tag, the last non-empty line (envs/searchqa/evaluator.py:28-47) |
| OfficeQA | exact match on the last tag, no numeric tolerance: "12.50" ≠ "12.5", "12%" ≠ "12", "thousand" is kept |
| LiveMath | one letter A–E after dropping one trailing `.`, `)` or `:` |
| ALFWorld | `infos["won"]` within 50 steps |
| SpreadsheetBench (v7) | both sides recalculated; the reference must match its own cached values; round(float, 2); strict types; every case must pass |

**JSON answers** [SF F30, FP F43]:
- Replies wrapped as JSON scored 0 of 364 (D5 critic), although 324 of 414 tagged twins passed.
- Rescoring moved the recipe placebo from −9.8 to −0.25.

**Scorer v2 does not exist** [SF F31]. Only SearchQA-only, untagged-only prototypes exist, in the session scratchpad.
Owner decision #2 is pending (direction-recommendation-20261021.md:100).

**Truncation** [SF F7, F14]:
- Official: unknown.
- Completion-aware `final`: fail (outcomes.py:69-72, 261-262).
- v3 gates read `final.token` (step.py:125, 170).

**Unknowns and stops:**
- Unscorable SpreadsheetBench formulas give unknown (sheet_recalc.py:46-48, 198-246) [SF F22]:
  - NOW, RAND, INDIRECT, HYPERLINK and the other forbidden functions;
  - `_xlfn.` / `_xlws.` functions;
  - structured references.
- A blank reference is a configuration stop: `invalid_answer_tag_score_input` (outcomes.py:57) [SF R8].
- Formulas written by openpyxl have no cached values, so the item would be excluded as a cache mismatch. This is
  inferred from code, not run [SF R5].

**Source-tree dependency:** the v7 scorer re-validates the 23-control qualification on every call and imports
`scripts.replay_sheet_v6`. The source tree must therefore include scripts/ and the pinned /root qualification path
[SF R10].

**Lenient score:** `scoring.lenient` has no production caller [SF F12].

### 3.9 Measurement facts any acceptance must respect

**Serving drift:**
- In cal-1 the share of terse replies per 15-minute bin ranged from 5% to 96% (D11).
- The same text on the same 60 OfficeQA items differed by +22.5 and +24.2 points across time windows (D11).
- Identical requests sent within 1 s came back reformatted (E4).

So all arms must run co-scheduled in one interleaved round [FP F45, F51].

**The instrument is noisy:**
- Placebos are not inert: in cal-1 they moved SearchQA by −9.8 to +3.6 points, mostly through the JSON scoring artefact
  [CM F47].
- v3's C1 passes a text against itself 13.6–17.3% of the time. That figure is D8's 2-run simplification; the full gate's
  false-pass rate is about 0.5% [FP F48].

**Generated items have not predicted real effects:**
- OfficeQA-style: +13 on generated items, 0 on real ones (E1).
- E9's generated panel was saturated (empty scaffold 0.891) and missed a real −9.5 harm.
- The 20–80% band was never reached.

Sources: [FP F50, F52, K4].

**Format conflicts:**
- Answer-format conflicts across benches cost −9.5 to −33 points on OfficeQA (E4/E9).
- Keep the format guard fixed per bench and identical across arms.
- The v3 whole-Skill render shows every bench's format advice to every task (skill.py:63-74) [FP K7, CM F55].

**D3's executable-skill result is confounded.** The only positive result (26/42 vs 16/42) has seven problems:
- the behavioural sentence was in arm T only;
- the parser rescued 41% of T steps vs 13% of control steps;
- max_tokens was 512;
- the arms were not co-scheduled;
- there was no placebo program;
- each arm ran once;
- only the empty scaffold was tested.

In the frozen loop the tracker hurt [FP K1].

## 4. Contradictions between readers, and with design-v0

R = resolved; F = flagged / unresolved.

1. **(R, updated) Reasoning on the new endpoint.**
   - [SB] and [LO] report reasoning always on and `thinking: disabled` ignored, from the probe-1 log (5 calls).
   - docs/project-status.md:14, re-read at ~17:30, adds three facts:
     - `reasoning_effort: "none"` switched reasoning off (0 reasoning tokens);
     - 8 of 8 concurrent requests were delivered;
     - `max_tokens: 2` was not enforced.
   - The scratchpad script `execskill/probe/probe_elucid2.py:31-40` sends exactly these request variants.
   - No reader read the probe-2 log itself ([SB] was refused), so these facts rest on the status line alone.
2. **(R) Docker images on dl.** [SB F14, Q10] did not check; [SF F25] and [LO F29] verified both pinned images present.
   Treat them as present.
3. **(F, different units) ALFWorld split sizes.**
   - [DP F13] counts games: train 3,553, valid_seen 140, valid_unseen 134.
   - [LO F32] counts task directories: train 2,435, valid_seen 242, valid_unseen 85.
   - This is not a conflict, but 242 task directories against 140 games in valid_seen is unexplained. Recount before
     drawing from valid_seen.
4. **(R) SearchQA never-used items.** The E5 critic says 59 of 600; [DP F8] finds 45, or 37 counting E10 generator
   sources, because the critic omitted E8. Use 45/37.
5. **(F) LiveMath reuse.** critiques/stoploss-evidence.md F7 says 154 non-meta items were reused by v3 stage 3, D7, D9
   and D10. [DP Q7]'s scan finds only focal ∪ regression (142 items). Unreconciled.
6. **(R) Source of "0/364".** The task brief pointed to D9. [SF F30] and [FP F42-F43] both place it in D5's critic
   (with E7). D9's sections D and E are cal-1 totals and learned-rule effects.
7. **(R) SpreadsheetBench focal tolerance.** `TOLERANCE_FOCAL` says 9; the v3 manifest says 7. The manifest recomputes it
   with `data.sheet_tolerances` (prelaunch.py:414-426), and the v6 registration table was superseded [CM F40].
8. **(R, trivial) Line numbers.** The maps give MODELS as lines 76-85 or 77-86. `MODELS = {` starts at
   weak_solver_probe.py:76 and `ROUTES` is at :88 (re-checked).
9. **(F) What the "task card" is.**
   - design-v0 calls the cards frozen, human-written texts, "the same as v3".
   - In v3, `texts.CARDS` are agent/human-written descriptions (texts.py:31-96).
   - But chain I and cal-1's ids-full arm used the five GLM-written instructions (texts.json;
     cal1-registration-20261020.md:42) [CM Q1].
   - The answer fixes what the task-card-only arm contains.
10. **(F) design-v0 claims against the evidence.**

    | design-v0 claim | What the readers found |
    |---|---|
    | "D3 tracker: zero errors on 228 episodes / 7,524 steps" | True for exceptions and property checks. Agreement with the hand tracker was 7,350 of 7,524. The episode gain is confounded and the tracker hurt in the frozen loop. "Induction" was a transcription of a dictated spec, one sample [FP F1, F6-F9]. |
    | "55 of 57 objects on open surfaces" | Comes from walkthrough metadata, i.e. in-sample [FP F16]. |
    | "D6 generated items 52/52 correct" | Keys 52/52, references 51/52. The LiveMath mirror forms derive from LiveMath training labels, which conflicts with registration v6 §2.2 [FP F26, F31]. |
    | "repaired scorer v2" | Does not exist [SF F31]. |
    | "ALFWorld samples new environments in the simulator" | No environment generator exists; only unused existing game files can be chosen [SF R9]. |
    | "each batch decides once and is never reused", with minimum effects of 7 (SpreadsheetBench), 10 (OfficeQA), 5 (LiveMath) | Not reachable on fresh real items (§3.7) [DP §5]. |
    | "the task card gets about a quarter of OfficeQA right" | Verified by no reader. The nearest figures are D6's "real ~22%" (FD/D6/result.json:7; the reader did not state the conditions) and GLM-5.3's instruction at 0.601 on the 74 real items (E1) [FP F28, F50]. |
    | "non-inferiority on dissimilar benches of about 4–5 points" | D8 proposed margins of 6/10/9/15/25 points. D6's critic: a 3-point margin needs ~550 items × 2 runs; 200 × 2 supports 5 [FP F32, F48]. |
    | "a test read costs ~52–57M per step, ALFWorld more than half" | Consistent with my arithmetic from the readers' anchors (inferred, not measured): 3 arms × (400×4,088 + 172×7,927 + 125×3,969 + 279×4,273 + 134×105.7k) ≈ 56.7M, of which ALFWorld is about 75%. |
    | "a literature check is still needed (D10 missed executable-skill libraries)" | True of D10 [FP F55]. docs/project-status.md:14 records a later check, docs/handoff/related-work-execskill-20261021.md: FlowEvo, CoEvoSkills and GRASP are the nearest precedents, and one 2026 study found code-form skills transfer worse than text. No reader read that file. |

## 5. Blockers and questions for the owner

### Blockers

These must be resolved before registration or implementation can be finished.

- **B1. Fresh data.**
  - SpreadsheetBench and OfficeQA have 0 fresh real items, and they are steps 1 and 2.
  - LiveMath has at most 291, against the 500–606 needed for 5 points.
  - SearchQA needs a new HF-validation block or blocks C/D.
  - New ALFWorld games need an items file and a test exclusion run with test access.

  Sources: [DP §5, §6].
- **B2. Scorer v2.** It does not exist, and owner decision #2 is pending. On SearchQA the JSON-format channel dominates
  measured differences [SF F30-F31].
- **B3. No sandbox for model-written code** (checks.py:3). Choose the runner and the CPU/slot budget on 7 CPUs [CI G1,
  LO §5].
- **B4. The new endpoint is unregistered:**
  - it is absent from every allow-list;
  - it ignores `max_tokens`, which conflicts with the ledger halt rule (ledger.py:67);
  - the reasoning mode is not registered;
  - slot count and read timeout are not registered;
  - the proxy route is not chosen;
  - the probe-2 log was read by no reader.

  Sources: [SB K1-K4, LO §6].
- **B5. No decision-table rows for procedure/shell/router failures.** Such failures fall into row 11 and count as
  infrastructure unknowns; above 1/10, the unit pauses (outcomes.py:304; evaluation.py:392) [CI G2].
- **B6. Test reading needs new machinery before any test read:**
  - evaluation is one arm per unit;
  - `unseal` is keyed by task_id;
  - the identity sites hash only text.

  So a multi-arm test read and package hashing must exist first [CI G5, FP F13].
- **B7. No anchored label for failure categories.** Detector acceptance would rest on model labels unless the
  categories are decidable mechanically [CM §5.5].
- **B8. Generators and their gates:**
  - OfficeQA tables are page text with no grid, and dl lacks `parsed/transformed`.
  - SpreadsheetBench references written by openpyxl lack caches.
  - No ALFWorld generator exists (selection only).
  - The saturation and predictive-validity gates have no precedent.

  Sources: [SF G5, G7, R5, R9; FP K4-K5; DP F11].
- **B9. Untracked files.** coevo5, run_coevo5.py and weak_solver_probe.py are untracked in git. The new branch must
  include them, and publishing v3 is a separate, pending task.
- **B10. Leftover workers.** About 2.7 GB of orphaned D3/D14 workers are alive on dl. Removing them needs an owner
  decision [LO F39].

### Questions for the owner

1. **Fresh sources.** Which do you release?
   - a new SearchQA HF-validation block, or blocks C/D;
   - LiveMath evaluation blocks e03–e08 (and e01/e02?);
   - ALFWorld train games outside the pool;
   - a SpreadsheetBench all_data_912 download, or newer LiveMath months.
2. **OfficeQA and SpreadsheetBench.** Should acceptance run on reused pool items labelled "not fresh, adaptive reuse"?
   Should those benches have only a generated-item screen? Or should the bench order change so the first steps have
   fresh supply?
3. **"Never used".** Does it mean never used in route B's own history, or never used by anything (the absolute sense,
   which gives 0 everywhere in the pools)?
4. **Task card.** Is it `texts.CARDS` or the GLM-written instructions? Is only the active bench's card shown (router),
   or all five as in v3? Do the format guards replace the format bullets inside the instructions?
5. **Scorer v2 scope and decision metric.**
   - Scope: JSON inside tags? `\boxed{}` and bare letters for LiveMath? JSON numbers for OfficeQA?
   - Decision metric: official (truncation = unknown) or completion-aware final (truncation = fail)?
6. **Format guard.** Is it an instruction only, or an output transformer? If it transforms output, its effect must be
   reported separately as answer repair, not as a learned effect.
7. **Solver for the pilot and the full run.** Is it deepseek-v4.1-flash-1017 via elucid throughout, or only in the
   smoke? Which reasoning mode (`reasoning_effort: "none"`, or reasoning on)? Which max_tokens, read timeout and slot
   count? Which proxy route (PJLAB gateway or direct)?
8. **Sandbox placement and versions.** Where do procedures run: a container per call, a container per episode, or a
   restricted in-process runner? Which sympy version?
9. **Procedure failures.** Are they a fail of the candidate arm or an infrastructure unknown? Does the L/H conservatism
   carry over to acceptance?
10. **Detector ground truth.** Mechanical categories, model labels, or pass/fail only? Which held-out trajectories?
11. **Predictive validity.** The rule "two consecutive disagreements void a generator" requires reusing generators
    across steps. Is that intended?
12. **SearchQA paraphrase probes.** Who certifies that a paraphrase keeps the answer? That would be a model anchor on
    the examiner side.
13. **ALFWorld baseline loop.** Frozen verbatim (32,768-token cap, no canonicaliser), or a new loop with the
    canonicaliser for every arm? This choice flips the sign of the tracker effect. Keep split "train", which puts the
    expert plan in `infos`?
14. **Extra solver calls.** May procedures make them (the exact-computation tag loop)? If so: the expression grammar, how
    a failed computation is scored, and the placebo's call count.
15. **Test reading.** Every step or once at the end? Should the task-card-only and placebo arms also be read on the test
    sets, which needs a multi-arm unit and new consent wording?
16. **Budget caps.** What caps apply for the new model, GLM, each role and the pilot? Does the old 1.44B coevo5 envelope
    still apply?
17. **Reuse of v3 assets.** Reuse v3's SpreadsheetBench engine and training/test qualifications, or re-certify under the
    new version? Keep the research role and the archive?
18. **Batch registry.** Per chain or shared? May items consumed in the pilot be reused in the full run?
19. **Per-procedure attribution.** Is there attribution before a procedure is labelled "general" or "this bench only"?
    The related-work note suggests adding a randomized procedure-removal control.
20. **LiveMath generators.** May they use regularities learned from training labels (the meta option is always the key)?
    The D6 critic says this conflicts with the registration.
21. **Leftover workers.** Who removes the orphaned D3/D14 workers?
22. **Slot root.** A machine-wide slot root, or exclusive scheduling?
23. **Identity strategy.** Approve the closed-set copy with a new VERSION (§2.0)?
24. **Process.** The relayed user request (a best-case data summary) appears to be handled by
    docs/handoff/best-case-summary-20261021.md. Please confirm. This map did not touch it.
