# Critique of spec-engineering.md -- LENS 2: engineering and adversarial (try to break the runtime)

Critic: adversarial engineering reviewer, read-only on the repo and on dl. Date: 2026-10-21 (restarted; the 18:08 stub of
an earlier attempt was empty and is replaced).
Target: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/spec-engineering.md
(cited as "spec §x" or "spec:line").
Status: COMPLETE (34 findings: 1 fatal as written, 15 major, 18 minor), 2026-10-21 19:42 CST.

Conventions: repo paths are repo-relative and cited path:line; `dl:` = the Linux machine. Every number is marked
"measured (source)" or "estimate (assumptions)". Severity: fatal / major / minor. Findings are written for implementers
(English); the owner summary at the end is plain Chinese.

## Method and provenance

- Read in full: the target spec; design-v0.md; the frozen code paths cited below (skillopt/coevo5/{ledger,calls,cells,
  outcomes,budget,stats,data,smoke,roles,step,leakage,qualify}.py, skillopt/continual_eval/{backends,native_worker}.py,
  scripts/weak_solver_probe.py, scripts/make_searchqa_fresh_sample.py); the understand/ maps by grep for the facts cited.
- On dl (BatchMode ssh, aTrust up, ls/cat/head only): `ls` of /root/continual-spreadsheet-20260928-a/{,prepared,prepared/assets};
  `cat` of the v3 TRAINING sheet qualification record (ids only were used; a temporary local copy was deleted at once);
  `ls -la` of the 91 qualified TRAINING item directories to obtain first-case workbook sizes. No test-pool path, no
  .env, no key, no model call, no pytest, no docker command.
- Labels: "measured" = read from code or files as cited; "estimate" = stated assumptions; "[LO Fn]", "[DP]", "[FP Fn]",
  "[SB]" refer to the understand/ maps (linux-ops, data-and-pools, feasibility-prototypes, solver-backends).

## Findings

### E1 [fatal as written] The worker's 65,536-byte line cap cannot carry the SpreadsheetBench view; the smoke cannot see it
- Severity note: fatal if "max line 65,536 bytes" governs request lines, which is how §1.8 reads ("line-delimited JSON on
  stdin/stdout ... max line"); if it was meant for responses only, the same items still carry up to 11 MB of base64 into
  every forked call and the memory limit of E5 becomes the binding fault source (then major).
- Attacked text: §1.5.3 "Procedures receive the view ... plus `input_workbook_b64` of the FIRST input case only (public;
  <= `MAX_WORKBOOK_BYTES` = 8 MiB ...)" together with §1.8 "line-delimited JSON on stdin/stdout ... max line 65,536 bytes"
  and §9 S2 "fixtures ... SpreadsheetBench 6".
- Why it breaks: base64 inflates by 4/3, so any first-case workbook above ~48 KiB makes every hook request of that cell
  (including `applies`, which also receives the view) exceed the line cap -> `malformed`/worker restart -> procedure fault.
  Measured (dl `ls -la /root/continual-spreadsheet-20260928-a/prepared/assets/spreadsheetbench_verified_400/spreadsheet/<id>/1_<id>_init.xlsx`
  for the 91 ids in `/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json` "qualified"; 89 files matched):
  median 10,238 B, p90 29,669 B, max 599,328 B, **8 of 89 above 48 KiB**. So ~9% of SpreadsheetBench items fault for
  EVERY procedure of the candidate; at 46 x 2 acceptance cells that is ~8 faulted cells of 92 (estimate, same share) =
  ~8.7% > the 2% fault cap of §5.3 condition 4. Every SpreadsheetBench candidate is rejected on faults regardless of
  merit -- on the first bench of the default pilot. The smoke uses 6 registrar-written fixture workbooks (§9), almost
  certainly small, so S0-S4 pass and the defect first appears in the pilot's acceptance. In addition the child limit
  `RLIMIT_AS` 384 MiB (§1.8) has to hold the parsed workbook (openpyxl's in-memory expansion of a 600 KB file is large;
  not measured) -> a second fault source correlated with workbook size, i.e. with item difficulty.
- Fix: (a) never inline workbooks in the protocol line: the host writes the first-case workbook into a per-cell,
  read-only bind-mounted directory (`/input/workbook.xlsx`) and the view carries only the path and its sha256; (b) S0 must
  compute, with zero calls, the view-size distribution of EVERY training pool item of every bench (SearchQA/OfficeQA
  `context`, ALFWorld observations, Sheet workbooks) and register the line cap as >= 2 x the measured maximum; (c) the
  SpreadsheetBench and OfficeQA fixtures of S2 must include the largest real training view's size class (a fixture whose
  workbook is >= the measured p99 size); (d) register that a fault correlated with input size is reported per size
  quartile.

### E2 [major] A procedure can desynchronize or pause the shell through the protocol channel itself
- Attacked text: §1.8 threat model "must not ... desynchronize the shell" and "printing to stdout"; worker protocol "EVERY
  call runs in a freshly os.fork()ed child ... returns through a pipe"; AST policy (the forbidden list has no `print`);
  host client "On worker death, EOF, a malformed line or a seq mismatch: restart the container ONCE ...".
- Why it breaks: (1) `print` is allowed and a forked child inherits fds 0/1/2, and fd 1 IS the protocol channel
  (`docker run -i ... worker.py` talks over stdin/stdout). Any debug `print` in a model-written hook -- common in
  generated code -- injects a non-protocol line: restart, retry, same print, fault -- at least one container restart per call (two if
  the retry's malformed line also counts as a worker failure, which the spec leaves open; estimate 2-6 s each, not
  measured). Library file APIs reach the same fds without `open`
  (`pandas.read_csv("/dev/stdin")` steals the next request; `DataFrame.to_csv("/dev/stdout")`). The frozen native worker
  at least redirects stdout/stderr around the executed program (skillopt/continual_eval/native_worker.py:111); the spec
  does not even require that. (2) Byte caps are not depth caps: a hook may legally return a 16 KB `state` or a 32 KB value
  that is a list nested ~5,000 deep; the host's `json.loads` raises `RecursionError` (not `ValueError`). Unless the host
  client catches it, the copied cell runner turns it into stop kind `exception` (cells.py:217-218) -> `Pause`
  (cells.py:232-233): model-written code pauses the unit, contradicting A6. The frozen `_native` had to catch exactly this
  case (`except (ValueError, KeyError, TypeError, RecursionError)`, backends.py:211).
- Fix: in the child, before running any procedure code, `os.dup2` /dev/null onto fds 0, 1, 2 and write the result to a
  dedicated pipe fd only; the PARENT enforces the wall limit with SIGKILL (not only an in-child alarm); a JSON nesting cap
  (e.g. depth <= 32) is checked in the child AND the host client treats every parse exception (including RecursionError
  and MemoryError) as `malformed` -> procedure fault, never a cell exception; add S0 probes: `print` in every hook kind,
  `read_csv("/dev/stdin")`, a depth-5,000 state, each must yield exactly one procedure fault and no restart storm.
- Related: "stderr discarded inside the container" is not a mechanism. With `docker run -i` attached, the container's
  stderr reaches the host subprocess; if the host opens it as a pipe and never drains it, repeated warnings from forked
  children (pandas/sympy FutureWarning/DeprecationWarning are re-emitted per child, because the warnings registry is per
  process) fill the 64 KiB pipe and block the worker -> 6 s time-outs and restarts at a rate that grows with call count.
  Register: the worker `dup2`s /dev/null onto fd 2 at start, the host uses `stderr=DEVNULL`, and `warnings` are set to
  `ignore` in the worker before loading procedures.

### E3 [major] "Hidden state is impossible" and "restart without losing information" are false
- Attacked text: §1.8 "(ii) module-level state mutated in one call vanishes, so hidden state is impossible ... (iii) the
  worker can be restarted at any time without losing information"; container `--tmpfs=/tmp:rw,...`; allowed imports
  include numpy, pandas, openpyxl, sympy.
- Why it breaks: the tmpfs is shared by all forked children for the container's whole life (a whole ALFWorld episode).
  `numpy.save/load`, `DataFrame.to_pickle/read_pickle`, `openpyxl.Workbook().save/load_workbook` give file I/O although
  `open` is forbidden, so a tracker can keep state across steps in /tmp outside the host-held `state`. Replay in one worker
  reproduces it, but the registered restart-once-and-retry (§1.8 host client) silently loses it mid-episode, so behaviour
  changes after a restart with no fault recorded, and the twin / re-execution pairing is no longer what the hash log
  claims. `read_pickle`/`numpy.load(allow_pickle=True)` on bytes the procedure wrote itself, and `sympy.sympify(<str>)`
  (eval-based) or `pandas.eval` let code reach `time`, `random`, `os` without any forbidden name in the AST. The container
  still bounds damage, but the determinism/hygiene layer the replay claims rest on is bypassable by accident (sympify is
  the natural LiveMath tool) and by design.
- Fix: set `RLIMIT_FSIZE = 0` in every procedure child (any file write fails -> fault) and mount no writable tmpfs for the
  procedure worker (the worker needs none after load); forbid the attribute names `read_pickle`, `to_pickle`, `save`,
  `load`, `tofile`, `fromfile`, `eval`, `query` in the AST policy; offer a fixed `safe_sympify(expr)` helper (parse with
  `transformations` that reject names outside a whitelist) and forbid raw `sympify`/`parse_expr` on non-literal strings;
  S0 probes: write-then-read across two calls must fault; a restart in the middle of a fixture episode must not change
  any later output hash.

### E4 [major] The double-run determinism check cannot see hash-order nondeterminism (and S0.5 would fail as written)
- Attacked text: §1.8 "Iteration over set/frozenset whose order matters ... caught by the double-run check"; "Every replay
  and every zero-crash call is executed twice in separate children"; container command `python -I -B /runner/worker.py`;
  S0.5 "set-order nondeterminism -> caught by the double run".
- Why it breaks: `-I` implies `-E`, so `PYTHONHASHSEED` is ignored and str/bytes hashing is randomized per INTERPRETER.
  Two forked children of the same worker inherit the same hash secret, so a string-set iteration gives the SAME order in
  both runs: the double run passes. Across workers (each QA cell and each ALFWorld episode has its own container, §1.8
  Lifetime) the order differs. Consequences: notes/vetoes that list a set of strings differ between the cell, its replay,
  its re-execution and its twin; RouteLog re-routing (§5.4 last bullet) and REEXECUTE comparisons report
  `nondeterministic` faults at ACCEPTANCE time instead of at the engineer check; S0.5's own required test cannot pass, so
  the launch blocks until the design is changed.
- Fix: production workers run with a fixed hash secret (start the interpreter with `-s -B -P` and `--env
  PYTHONHASHSEED=0`, assert `sys.flags.hash_randomization == 0` in the `ping` reply and pin it), and the engineer-check
  double run executes the two copies in TWO workers started with different seeds (0 and 1), which is what detects order
  dependence. Register both, and keep `hash` forbidden.

### E5 [major] The registered sandbox limits are likely unworkable and the memory-failure path can pause the chain
- Attacked text: §1.8 container command ("copied from `backends._native` hardening ..., tightened"; `--pids-limit=64`,
  `--memory=384m`, "No `--env` carries anything but the fixed marker"), child limits "`RLIMIT_AS` 384 MiB (ALFWorld 256
  MiB)", "resident memory of a loaded worker is estimated at 100-200 MB (not measured)", host client "If the restart
  itself fails ... -> `SandboxUnavailable` -> cell stop, unit pause".
- Why it breaks: (1) the frozen hardening sets `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MPLCONFIGDIR` and
  `--pids-limit=128`, `--memory` default 4,096 MiB (measured: skillopt/continual_eval/backends.py:121, 171-175); the spec
  drops the thread variables while halving pids, so a numpy import in the worker starts one BLAS thread per visible CPU
  inside a 64-pid budget (risk of thread-creation failure; not measured). (2) `RLIMIT_AS` limits VIRTUAL size; a child
  forked from a parent that preloaded numpy/pandas/sympy/openpyxl inherits the parent's virtual size, which with BLAS
  thread arenas is plausibly above 256-384 MiB (estimate: typical Linux post-import VSZ 0.4-1 GB with multithreaded
  OpenBLAS; must be measured). If so, EVERY call fails with MemoryError at its first allocation: all procedures fault,
  every candidate dies on the 2% cap. (3) The container cgroup limit (384 MiB) counts the parent plus copy-on-write pages
  the child touches; when it is hit, the kernel OOM killer picks the largest process, i.e. the parent worker -> worker
  death -> restart -> retried call dies the same way. The spec does not say whether a worker death on the RETRIED call
  is a procedure fault or `SandboxUnavailable`; if the latter, a memory-hungry model-written hook pauses the unit (against
  A6).
- Fix: keep the frozen env variables (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`) and pids 128;
  in S0 measure the loaded worker's VSZ/RSS per bench package and register `RLIMIT_AS = measured VSZ + 256 MiB` (or use
  `RLIMIT_DATA`) and `--memory >= parent RSS + child cap + 128 MiB`; children write 1000 to `/proc/self/oom_score_adj`
  so the kernel kills a child, never the parent; register: a worker death during a call or its retry = procedure fault
  (`memory`/`crash`), and `SandboxUnavailable` only when a FRESH container cannot answer `ping` within 30 s.

### E6 [major] Re-execution of any two-call cell pauses the unit instead of producing "P3 unknown"
- Attacked text: §1.8 "re-execution of a cell (REEXECUTE remedy, cells.py:139-149) re-runs the shell, and a request-hash
  mismatch is recorded as fault `nondeterministic` ... it counts toward the fault cap and never pauses the unit"; §1.10 row
  P3; §0.3 cells "Copy with VERSION" (no behavioural change listed); §1.5.3 repair call.
- Why it breaks: the frozen replay takes `recorder.receipts[-1]` and `recorder.sends[-1]["request_sha256"]` and
  `require`s that the FIRST request the re-executed solver sends equals that LAST send (skillopt/coevo5/cells.py:141-145).
  In a SpreadsheetBench repair cell the last send is the repair call, so the re-executed shell's first call never matches:
  `require` raises, `run_cell` records stop kind `exception` (cells.py:217-218) and raises `Pause` (cells.py:232-233). The
  trigger is ordinary: a final program that times out natively (`native_timeout` -> REEXECUTE, outcomes.py:360-361) or an
  execution-environment failure (outcomes.py:362-363); CPU contention on 7 CPUs makes these plausible (spec R14). `sends`
  also contains resent attempts, so even one-call cells with a resend are fragile. Moreover re-execution re-runs the
  `sheet_feedback` PRE-CHECK, i.e. the solver's own program on the public input, whose timing is not deterministic, so the
  branch (repair or not) can legitimately differ; labelling that a procedure fault `nondeterministic` and scoring it
  "unknown = fail for S'" (L/H) charges infrastructure noise to the candidate.
- Fix: rewrite `_replay` in the copy to replay the ordered list of DELIVERED calls (call i must hash to delivered send i;
  reply i = receipt i), store the pre-check `run_report` as a cell artifact that replay reads instead of re-running, and
  implement P3 explicitly (catch the mismatch, record it, token `unknown`, `kind = infrastructure`, not a procedure fault).
  Unit tests: a one-call cell with one resend, a compute cell and a repair cell, each with `native_timeout` on the final
  program, re-execute without a Pause and with identical hashes.

### E7 [major] A reasoning leak is a GLOBAL ledger halt, not the resend of row P6; B = 2M makes that likely on ALFWorld
- Attacked text: §1.10 P6 "receipt has `reasoning_tokens > 0` ... -> resend <= 2, then infrastructure unknown"; §1.11
  "Endpoint ... constructed with `max_tokens = B` ... the breach check compares completion against B"; §3.1 "B = 2 x M
  (16,384 / 2,048), CONDITIONAL on smoke S1-b"; S1-b "3 calls with M in {16, 64, 256}".
- Why it breaks: the breach is evaluated inside `Endpoint.send` (`_record` -> `ledger.settle`, completion > max_tokens:
  skillopt/coevo5/ledger.py:67; calls.py:182-184) and raises `AssumptionBroken` BEFORE the Recorder's resend loop looks
  at the receipt (calls.py:273-275). A settled breach halts the whole ledger -- every scope, GLM included -- and every
  reservation of an attempt begun before the halt is refused even after the owner's resume (budget.py:8-11, 84-96). If
  `completion_tokens` includes reasoning tokens (the OpenAI-compatible convention; the 21-token reply to `max_tokens: 2`
  with reasoning on is consistent with it -- to be verified in S1), then any reply that ignores `reasoning_effort: "none"`
  and reasons for more than 2,048 tokens on an ALFWorld step halts the pilot. The leak rate with "none" is unknown:
  measured 0 reasoning tokens in a handful of probe calls (docs/project-status.md:15 as of 19:40; five small requests), and the same gateway returned
  reasoning even when `thinking: disabled` was sent ([LO F20]). The pilot makes on the order of 16,000 ALFWorld step calls
  in acceptance alone (estimate: 536 episodes x ~30 steps, §8.2) plus the test read, so a 1-in-10,000 leak already
  predicts about two global halts; in a test read (four bench children side by side in wave 1, §1.11) one halt voids every child's attempt (no
  splicing, §1.14).
  Three S1-b calls cannot establish enforcement on a load-balanced gateway either.
- Fix: register B as the gateway's HARD output ceiling (measured in S1 with reasoning ON and a long-output prompt, e.g.
  B = 32,768 or the documented maximum), not 2M, so that a leak is settled normally and handled by P6; re-size every
  per-step cap for the larger reservation (see E17); measure the leak rate in S1+S2 over >= 300 calls with "none" and make
  "0 leaks" a launch condition; list in the report every receipt with reasoning tokens and every halt.

### E8 [major] Procedure notes are an unguarded format channel; "format outside the learnable part" is not enforced
- Attacked text: §1.1 "No hook can ... (b) change the contract sentence, (c) change, extract or rewrite the final reply";
  §1.4 "Instruction only; no output transformation"; C8 "re-rendered requests ... have the parent's system-prompt sha256
  and the reply channel is untouched"; design-v0 §一.4 "格式不许进入可学习的部分".
- Why it breaks: a note is free text placed in the user JSON (§1.5.1). Nothing stops a learned note from saying "reply
  with the number only", "output a JSON object", "write the formula" or (ALFWorld) "answer as `action: ...`". That is the
  exact mechanism behind the E4/E9 harms the spec cites (-9.5 to -33 points from format advice in guidance text, §1.2).
  Cross-bench firing makes it worse: SearchQA and OfficeQA public views have IDENTICAL keys `question`, `context`
  (skillopt/continual_eval/backends.py:57-62) and hooks receive no bench name (§1.3 `sandbox.call(p.id, "applies",
  {"view": view})`), so an OfficeQA "number only" note can fire on SearchQA items. C8 checks only the system-prompt hash; C4
  checks answers in literals, not format directives.
- Fix: (a) a fixed note linter at C9 and at run time (note dropped + fault `format_directive`) with a registered pattern
  list: any contract tag (`<answer>`, `</answer>`, `<action>`), code fences, the words "format", "JSON", "final answer",
  "only the letter/number", "respond with"; (b) a GATING acceptance condition: S' minus S on the mechanical format
  detectors (`no_answer_tag`, `json_answer_untagged`, `multiple_answers`, `excel_formula_only`, `invalid_action_format`)
  must not exceed +2 points (registered), and the same per-bench table on test reads; (c) record per note whether the
  linter fired, so the report can separate content help from format effects.

### E9 [major] Replay tests are trivially satisfiable; C7 is a determinism check with a misleading name
- Attacked text: §1.7 "A test passes iff the procedure, executed twice ... returns identical outputs both times and the
  property holds"; the closed property set `applies_true`, `note_contains`, ...; engineer manifest `claimed_failures`,
  `replay_tests` 1..10; design-v0 "回放测试，即它声称能修的那些失败记录，必须在上面跑通".
- Why it breaks: the engineer chooses both the procedure and its properties. `applies = lambda v: True` plus a constant
  note satisfies `applies_true` + `note_contains` on any trajectory; nothing ties a test to a claimed failure (no rule
  that each `claimed_failures` id has a test, or that the property concerns the failing step), nothing requires the
  property to be FALSE for the parent package (so a test need not distinguish S' from S), and there are no negative tests
  on passing trajectories. The gate therefore certifies only determinism and absence of crashes, which C6 already checks.
  Calling this "the procedure repairs the failures it claims" in any report would be unfalsifiable.
- Fix: registrar-generated obligations, fixed code: (1) every `claimed_failures` id carries >= 1 test whose `step` is in
  that trajectory; (2) differential: the property must hold for S' and FAIL for S on that trajectory; (3) negative tests
  on every PASSED run trajectory of the bench: an ALFWorld procedure never vetoes the action the winning trajectory took
  at that step; a Sheet procedure never requests repair on a passed item; QA `compute` requests, if any, must evaluate
  without error; (4) firing rate on passed trajectories reported next to the test result. Rename C7 "claim tests" and
  report pass counts of (1)-(3) separately.

### E10 [major] The detector gate accepts restated outcome proxies and the detector's input is undefined
- Attacked text: §4.2 "accept iff Wilson 90% lower bound of precision > base, AND precision / base >= 1.2, AND recall ...
  >= 0.10" computed on the HOLD half; §3.3 `detect(trajectory_view) -> bool`; §1.9 the trajectory record "containing ...
  the judge blocks and the decision token".
- Why it breaks: (1) the gate is computed on all hold-half cells, not on the residual that the mechanical and already
  accepted detectors leave uncovered. A model-written copy of `step_budget_exhausted` (an ALFWorld episode that used all 50
  steps has failed by construction, except a win on exactly the 50th step: the loop stops at `won or dones[0]`,
  backends.py:768-770) has precision ~1, lift
  1/base and high recall, so it is "accepted" while adding nothing; the examiner-side count of accepted detectors becomes
  inflatable. (2) `trajectory_view` is never defined; the stored trajectory contains the judge blocks and the decision
  token, and for QA the format flags are partly verdict-derived. Unless the projection is a whitelist, `detect` can read
  the verdict and every detector passes.
- Fix: define `trajectory_view` as a registered whitelist (views, replies, actions, post-observations, enabled ids,
  procedure notes; never judge, verdict, token, reason, finish, format flags, step count beyond the per-step records);
  compute precision, lift and recall on hold-half cells NOT fired by any mechanical or accepted detector; require Jaccard
  overlap < 0.8 with every existing detector's fired set; count and report "accepted detectors" only under this rule.

### E11 [major] ALFWorld pre-routing and in-cell routing see different views -> spurious `nondeterministic` faults
- Attacked text: §2.2 ALFWorld items file stores `initial_observation` only; §5.4 "ALFWorld routes on the
  `initial_observation` stored in the items file ... each cell re-routes and must reproduce the same RouteLog (else fault
  `nondeterministic`)"; §1.3 "once per episode on the reset view".
- Why it breaks: the reset view the copied loop builds is `{initial_observation, observation, admissible_commands,
  recent_history}` (frozen layout, skillopt/continual_eval/backends.py:744-746). A predicate that reads
  `admissible_commands` (the natural signal for "has receptacles to search") returns a different value in pre-routing
  (key absent) and in the cell, so every such episode is a `nondeterministic` fault, the P0 firing set and the twin
  selection are computed on the wrong view, and the 2% fault cap rejects the candidate.
- Fix: register the ALFWorld routing view as exactly `{initial_observation, admissible_commands_at_reset}`; `make-items`
  stores both from the zero-call reset; the in-cell router uses the same projection (not the full step view); S0 test:
  pre-routing and in-cell routing of a fixture package agree on 4 smoke games.

### E12 [major] Recovery redoes whole units but the step caps count the paused attempt: the redo can hit a BudgetStop
- Attacked text: §1.14 "A redone unit re-runs ALL its cells ... acceptance on ALFWorld runs in 4 blocks"; §8.3 per-step
  solver caps (e.g. SearchQA accept 14M) against §8.2 estimates (SearchQA accept 8.8M).
- Why it breaks: the paused attempt's spend stays settled in the same scope; admission requires settled + open + R <= cap
  and refuses when nothing is open (skillopt/coevo5/budget.py:3-6). A SearchQA acceptance (about 4,000 cells, 5-7 h, one
  unit: only ALFWorld is blocked) paused after ~60% has spent ~5.3M; a full redo needs ~8.8M: 14.1M > 14M -> BudgetStop
  inside the redo (estimate from the spec's own numbers). The same arithmetic applies to a test read redo after a ledger
  halt (E7) or a cleanup pause. Recovery therefore needs an owner `raise` that the spec does not mention. In addition,
  the owner's established practice for test-eval stops was to archive the faulty cell attempt and score clean cells
  (auto-memory "test-eval stop recovery"); the spec's no-splicing rule silently reverses it.
- Fix: per-attempt sub-scopes (`...:accept:a<N>`) with the step cap applying per attempt plus a registered stage-level
  redo reserve (e.g. +1 x the largest unit estimate); block SearchQA and OfficeQA acceptance like ALFWorld (e.g. 4 x 250
  items, all arms interleaved per block); list "no splicing" as an owner decision with the drift evidence that motivates
  it ([FP F45]).

### E13 [major] The smoke would not catch the format defects the v3 smoke caught
- Attacked text: §9 S2 "Format check: C arm on the 20 real SearchQA items: required-format share >= 9/10 ...; fixtures
  descriptive"; "NO real OfficeQA, LiveMath or SpreadsheetBench item is used".
- Why it breaks: v3's smoke gated the answer form on 20 real training items of FOUR benches with a 9/10 floor and a 1/20
  margin against the empty Skill (skillopt/coevo5/smoke.py:69-77, 275-278); that check is what produced the
  SpreadsheetBench contract v2 ("a formula alone is not an answer", fence on its own line: backends.py:48-56). Route B
  changes the model (deepseek-v4.1-flash-1017, reasoning off, new gateway) and adds notes and second calls, yet gates the
  format only on SearchQA; LiveMath single-letter, OfficeQA tag, SpreadsheetBench program delivery and the ALFWorld action
  tag are "descriptive". A new-model regression in any of them passes the smoke and surfaces in the pilot's acceptance
  (where it is charged to arms and, under fail-on-format, looks like a method effect).
- Fix: gate the format share for EVERY bench and arm of S2 (fixtures are fine: format compliance does not need truth)
  with the v3 floor 9/10 and margin 1/20 versus arm C; build fixtures with the shape of real training views (OfficeQA
  long multi-page contexts, LiveMath 5 options, Sheet workbooks up to the measured p99 size, see E1); for ALFWorld gate the
  `<action>` tag share and report the canonicaliser rescue share; record the reasoning-leak count (E7) in the same table.

### E14 [major] Sandbox stops raised inside the copied ALFWorld loop are swallowed by the frozen catch-all
- Attacked text: §1.5 "A copy of `backends.solve` (:364-455) and `_solve_alfworld` (:715-783) with explicit hook points";
  §1.8 "an unconfirmed cleanup raises `CleanupUnconfirmed` (outcomes row 3: the cell stops, the unit pauses)" and "If the
  restart itself fails ... -> `SandboxUnavailable` -> cell stop, unit pause"; §1.10 P4.
- Why it breaks: the frozen episode loop wraps everything after `env.reset()` in `except Exception as exc: return
  _prediction_unknown("alfworld_environment_error:" + type(exc).__name__ ...)` (skillopt/continual_eval/backends.py:774-776).
  A copy "with hook points" keeps that block, so a `SandboxUnavailable` or `CleanupUnconfirmed` raised by a hook call in
  step i becomes `alfworld_environment_error:CleanupUnconfirmed`. The frozen stop test only recognises the fixed reason
  strings (`container_cleanup_unconfirmed`, `alfworld_cleanup_unconfirmed`, ...: outcomes.py:62-63, 289-290), so the cell is
  scored as row 8 infrastructure-unknown (outcomes.py:302-303) -- or row 7 with a RESTART when it happened before the
  first model call (outcomes.py:300-301) -- while a sandbox container may still be alive. That breaks the v3 cleanup
  invariant the spec claims to copy, and a dead docker daemon degrades into a slow stream of "unknown" episodes instead of
  one pause. (In the QA path the same exception escapes `solve`, because its except clause lists only OSError, ValueError,
  KeyError, BadZipFile: backends.py:454 -- provided the new classes do not subclass those.)
- Fix: in the copied loops, re-raise every route-B stop class before the catch-all (`except (SandboxUnavailable,
  CleanupUnconfirmed, ConsumptionConflict): raise`), require that the new classes derive from neither OSError nor
  ValueError, and add the reason strings `sandbox_unavailable` / `sandbox_cleanup_unconfirmed` to the copied `outcomes`
  stop rows as a second line of defence. Unit test: a fake sandbox that fails cleanup at step 3 of a fixture episode must
  produce a `cleanup` Pause, not a scored cell.

### E15 [minor, launch-blocking] The escape probe can never pass as written
- Attacked text: §1.8 escape probe "no file under `/` matches `*.env`, `*key*`, `consent*`, `ledger*`"; S0.6.
- Why: every CPython image contains `.../lib/python3.X/keyword.py`, and Linux exposes `/proc/keys`; a recursive walk of
  `/` also enters `/proc` and `/sys` (huge, with self-referencing links). The probe either fails on benign files or gets
  loosened ad hoc at launch time.
- Fix: probe what matters: `/proc/self/mountinfo` shows no bind mount other than `/runner` (read-only) besides the
  standard /proc, /dev, /sys, /dev/shm and (if kept, see E3) /tmp mounts (in particular no `/data`, `/root`, run root,
  ledger, slot root, credential dir); `os.environ` equals the recorded list;
  `stat` of the host paths `/data`, `/root/.config/weak-solver` fails; network unreachable.

### E16 [minor] A "copied worker that returns the traceback" requires a copied `_native`
- Attacked text: §1.5 "importing every helper unchanged (... `_native` ...)" vs §1.5.3 "from a COPIED worker that returns
  it, unlike native_worker.py:113-114".
- Why: `_native` always ships the frozen file next to backends.py (`Path(__file__).with_name("native_worker.py")`,
  skillopt/continual_eval/backends.py:167); an unchanged `_native` cannot run another worker.
- Fix: the pre-check uses a copied `_native_precheck` (same flags, including the frozen env variables of E5) with the
  copied worker, pinned in the manifest; the SCORED per-case execution keeps the frozen `_native` and worker unchanged.

### E17 [minor] "Caps are therefore not blocked by reservations" is false for the small caps
- Attacked text: §8.3 "x 8 slots ~ 0.74M reserved at most; caps are therefore not blocked by reservations".
- Why: Sheet run 0.5M, LiveMath run 0.5M, SearchQA examiner 0.5M and selftest 0.5M are below 0.74M; admission needs
  settled + open + R <= cap (budget.py:3-6), so those scopes run at most ~5 QA calls in flight and the last ~92k of each
  cap is unusable: the final call is refused -> BudgetStop -> Pause. With E7's larger B every reservation grows (~4 x 32k
  per QA call at B = 32,768, estimate), and transport time-outs charge each unrefused attempt its full bound
  (ledger.py:68-69).
- Fix: register every cap as >= estimate x 2 + slots x reservation, re-derived after S2 and after B is fixed.

### E18 [minor] The equivalence test contradicts the always-on canonicaliser
- Attacked text: §1.5 equivalence test "every prediction equals frozen `backends.solve` ... on fixture tasks of all five
  benches" vs §1.5.4 "registered canonicaliser ... for EVERY arm".
- Why: the frozen loop executes the raw tag content (backends.py:752-762); with a non-canonical fake reply the route-B
  trace differs. It also means route-B's card-only arm is not v3's card-only behaviour.
- Fix: run the equivalence test with fake replies that are exact admissible strings, plus a separate test whose only
  difference is the canonicaliser; state in the registration that ALFWorld numbers are not comparable with v3's.

### E19 [minor] Manifest gaps
- Attacked text: §1.13 FIELDS.
- Missing: content hashes of every ALFWorld game file of each slice (the items file pins only relative paths), the
  ALFWorld environment (alfworld/textworld versions, the venv `/root/continual-alf-prep-20260928/env` [LO]), the worker
  interpreter's version and `sys.flags` (E4), the absolute docker CLI path and daemon version, the S1 gateway fingerprint
  (enforcement result, reasoning-leak count, echoed ids, prompt overhead) and a salted hash of the elucid key (the gateway
  routes by key "group", per the 503 `No available channel ... under group` reply [LO F20], so a key swap can change the
  serving without changing url/model); the line cap and nesting cap (E1, E2).
- Fix: add them; `verify_code` already covers code.

### E20 [minor] Registry and smoke inconsistencies
- §2.3 `purpose in {smoke, run, accept, withhold, detector_holdout}` but §4.3 consumes ALFWorld examiner games "with
  purpose `examiner`": the registry would refuse or mislabel them. Add `examiner`.
- §3.3 `generator_write` takes "3-5 public training items of the run slice", but S3 runs a LiveMath-type generator in a
  smoke that has no real LiveMath item: say that the material is fixtures.

### E21 [minor] ALFWorld hook edge cases are not defined
- Vetoes naming commands outside the admissible list (ignore + count, or fault?); the floor rule "refuses a veto that
  would leave fewer than 2 commands" does not say which procedure's veto is dropped when several veto (register: apply in
  package order, drop the whole list of the procedure that would cross the floor); whether the fixed "Not recommended
  now: ..." text counts in the 1,500-char budget; the `alf_after_step` event has no flag telling the tracker that the
  executed text was not admissible (`how == "unchanged"` is implicit; add `executed_admissible: bool`).

### E22 [minor] Test-side fault messages can carry test text
- §1.5 stores `faults[].message` (<= 500 chars) and `procedure_events` in the prediction, and the copied cell stores the
  full prediction under `artifacts/` (cells.py:97-101) in evaluation units too. Exception messages often quote inputs
  ("could not convert string to float: '...'"). On test-side cells keep `exc_type` and a hash of the message only.

### E23 [minor] The send record states the wrong max_tokens
- The Endpoint records `"max_tokens": self.max_tokens` (calls.py:153-154) = B, while the body sends M. Add
  `nominal_max_tokens` to the receipt and the trajectory so audits do not misread B as the request.

### E24 [minor] Hook time per ALFWorld episode is unbounded in aggregate
- Per call up to 3 s wall, 2-4 hooks per step, 50 steps: up to ~600 s of hook time per episode without any fault
  (estimate from §1.8 limits). S' episodes can then run far longer than C episodes, which undoes the time co-scheduling
  the interleaving relies on (R7) and holds episode slots. Register a per-episode cumulative hook budget (e.g. 30 s; then
  the procedure is dropped as a fault) and report hook seconds per arm.

### E25 [minor] The scrubbed docker CLI environment is untested on dl
- `env={"PATH": "/usr/bin:/bin"}` drops HOME (docker CLI config) and any DOCKER_HOST; the frozen code resolves docker
  with `shutil.which` under the full environment (backends.py:136, 158). Pin the absolute docker path at make-manifest,
  pass `HOME`/`DOCKER_CONFIG` pointing to an empty directory, and run S0 with exactly that environment. Also give
  container start and the `load` op registered timeouts (e.g. 30 s / 60 s) -> `SandboxUnavailable`; today only calls are
  bounded (6 s), so a stalled dockerd blocks a cell thread indefinitely.

### E26 [minor] Placebo shadow execution has no fault accounting
- §5.2 runs S''s new procedures "in shadow mode" inside P cells to get note lengths; their faults/timeouts in P cells
  are assigned to nobody and leave the length undefined. Register `shadow_fault` (not counted for P or S'), and a fixed
  fallback length (the median S' note length from the pre-routing pass).

### E27 [minor] Test access outside the evaluation step needs an explicit firewall exception
- `data.TestAccess` is "Created by the evaluation step only" (skillopt/coevo5/data.py:232-233); `exclude-tests` (§1.15,
  §2.2, D3) creates it in a CLI command. Register it as a separate pinned command with its own consent record, that
  receives only supply ids/paths and returns counts and an exclusion hash, and that no unit can call.

### E28 [minor] P1 lists a fault kind the runtime cannot observe
- P1 includes "nondeterministic (at first execution)", but at run time each call executes once; nondeterminism is only
  visible at the engineer check, at re-routing and at REEXECUTE. Either drop it from P1 or register a run-time double
  execution on a seeded 5% sample of calls (cost: sandbox CPU only).

### E29 [major] Re-running the SearchQA sampler "with a larger count" materializes the sealed blocks C/D on dl
- Attacked text: §2.2 SearchQA "re-run the deterministic order of `scripts/make_searchqa_fresh_sample.build` ... with a
  larger count; ... rows at positions >= 4,001 are disjoint from blocks A-D BY CONSTRUCTION, and blocks C/D never have to
  be opened"; owner D3 text "SearchQA 封存的 C/D 块完全不用打开".
- Why it breaks: `build` writes EVERY chosen item, split into `count/blocks` equal blocks
  (scripts/make_searchqa_fresh_sample.py:92-99: `chosen[number * size:(number + 1) * size]` -> `block_<x>/items.json`),
  and refuses a count not divisible by the block count (:48-49). Re-running it with, e.g., count 15,000 writes positions
  1-4,000 -- the text of blocks A-D, including the sealed C/D that "stay on the operator's machine, unread, for the
  one-time hold-out read" ([DP] data-and-pools.md:244) -- into a new directory on dl, and the new block boundaries no
  longer coincide with A-D. The property "positions >= 4,001 are disjoint" is true of the ORDER, not of the files the
  script produces. The script also reads the HF dataset from the local cache ONLY, at the pinned revision (`--revision c1a97906...`,
  :117, :125-133: "the cached revision only, never the network"); whether that cache exists on dl is not stated, its path
  and hash are not in the manifest, and a download would be an owner decision.
- Fix: a copied `build_tail(start=4000, count=N)` that walks the same order and the same dedupe state in memory, checks
  that positions 1-4,000 reproduce the recorded block id lists and sha256s of `sample_manifest.json` (ids and hashes
  only, no text written), and writes ONLY the tail; it also excludes the reserve ids (which the script's native-dir
  exclusion does not cover: it reads only train/val/test, :51-56 [DP 314-317]); pin the HF cache path and revision;
  register the in-memory handling of C/D questions explicitly so the owner can accept or refuse it (D3).

### E30 [major] P3's "unknown" token feeds the infrastructure guard: a nondeterministic procedure can pause the unit
- Attacked text: §1.8 "the candidate's cell token becomes `unknown` and is scored by the L/H rule ... it counts toward
  the fault cap and never pauses the unit"; §1.10 P3; §4.1/§5.3 "Pause (not reject) if any arm's
  infrastructure-unknown share > 1/10".
- Why it breaks: the spec gives the P3 cell an `unknown` token but no verdict kind. The copied guard pauses a round when
  an arm has > 10% cells with outcome `unknown` and kind `infrastructure` or `unclassified` (skillopt/coevo5/step.py:128-130,
  150-157), and an unknown whose reason the table does not list defaults to row 11 `unclassified`
  (skillopt/coevo5/outcomes.py:304); the gate statistics also count every `unknown` token as an infrastructure unknown
  (stats.py:24-27, 40-44). A procedure whose output depends on hash order (E4) or on the pre-check timing (E6) therefore
  raises the S' arm's infrastructure-unknown share, and above 1/10 the copied guard pauses the unit -- model-written code
  stopping the chain, the exact outcome A6 forbids, and the opposite of the spec's "never pauses".
- Fix: the frozen `stats.OUTCOMES` admits only four tokens (stats.py:16, 23), so copy `stats` (it is protocol-free)
  with a fifth token `unknown_fault`: L = fail, H = pass (the conservative L/H reading for every arm), excluded from
  the infrastructure share and counted in the fault cap; give the P3 verdict the kind `procedure_fault`, which the copied
  guard does not count. Unit test: 15% P3 cells in an S' arm reject the candidate (fault cap) and do not pause; 15% P3
  cells in the parent arm count as passes for the parent and do not pause.

### E31 [minor] A runner crash leaves long-lived sandbox containers behind; recovery does not say how they are removed
- Attacked text: §1.8 lifetime "One container per QA/Sheet cell ... one per ALFWorld episode"; §1.14 "Cleanup-unconfirmed
  pauses additionally require: no `execskill-sbx-*` ... container in any state"; §1.15 `recover`.
- Why: v3's containers were short-lived per execution; route B's live as long as a cell/episode. If the runner process
  dies (OOM, reboot, tmux kill), up to 16 + 6 containers survive (running if the worker does not exit on stdin EOF;
  stopped otherwise, since there is no `--rm`), holding up to ~8 GiB of memory limits on a 15 GiB machine (measured RAM:
  [LO F1]). The registered pause condition then blocks every recovery until someone removes them by hand.
- Fix: the worker exits on stdin EOF; containers carry `--label execskill.attempt=<attempt id>`; `recover` lists and
  `docker rm --force`s exactly the containers of the dead attempt and confirms by label, recording the list.

### E32 [minor] "Route-B ALFWorld workers identified by command line" cannot work
- Attacked text: §1.14 "the leftover D3/D14 workers are excluded by command-line match"; R16.
- Why: ALFWorld episodes run as `multiprocessing` spawn children (backends.py:610-614); every spawn child of the same venv
  has the same `python -c "from multiprocessing.spawn import spawn_main; ..." --multiprocessing-fork` command line, exactly
  like the ~21 orphaned D3/D14 children on dl ([LO F39]).
- Fix: mark route-B processes positively: export `EXECSKILL_ATTEMPT=<id>` in the runner (inherited by spawn children) and
  match `/proc/<pid>/environ` (marker only, never print the environment) plus cwd under the snapshot.

### E33 [minor] Evidence citations point at a living document whose lines move
- The spec cites the elucid probe facts as "docs/project-status.md:14" (§0.1, §1.11, §3.1); at 19:40 that line is the
  GitHub-publication entry and the probe facts are on line 15 (the status file is rewritten after every event, per
  AGENTS.md). A registration must cite stable evidence: the probe logs on dl (`/data/execskill-ops/probe-20261021-*.log`,
  another agent's directory, so copy them into `/data/execskill-20261021-ops/evidence/` with sha256) and the probe
  script (scratchpad `execskill/probe/probe_elucid2.py`), not a line of the status page.

### E34 [minor] There is CPU arithmetic but no memory arithmetic
- §1.11 sizes CPU only. In test-read wave 1 (four bench children side by side) the registered limits add up to
  16 sandboxes x 384 MiB + 3 native executions x 4,096 MiB (the frozen SpreadsheetBench runtime, measured [LO F14]) +
  host processes ~ 18 GiB of limits on a 15 GiB machine with 11.8 GiB available (measured [LO F1, F39]), before E5's
  likely increase of the sandbox limit. Usage is probably far lower, but nothing measures it. Register a memory budget
  (sum of concurrent limits <= available RAM - 2 GiB) or measured peak RSS from S2, and make the wave composition depend
  on it.

## Severity index (most severe first)

- Fatal (as written): E1 (worker line cap vs SpreadsheetBench workbooks; measured 8 of 89 training first-case workbooks
  above the limit; invisible to the specified smoke).
- Major: E7 (reasoning leak = global ledger halt; B = 2M), E6 (re-execution of two-call cells pauses), E30 (P3 unknown
  feeds the pause guard), E14 (sandbox stops swallowed in the ALFWorld loop; cleanup invariant), E2 (protocol-channel
  desync and RecursionError pause; stderr pipe), E5 (sandbox limits likely unworkable; OOM path undefined), E4 (double run
  blind to hash order), E3 (hidden state via /tmp; eval/pickle bypass), E8 (notes as an unguarded format channel), E9
  (replay tests trivially satisfiable), E10 (detector gate accepts outcome proxies; undefined input), E11 (ALFWorld
  routing views differ), E12 (redo vs step caps; no SearchQA blocks), E13 (smoke does not gate format on four benches),
  E29 (SearchQA supply rebuild materializes sealed blocks C/D).
- Minor: E15-E28, E31-E34.

## Contradiction paragraph (working assumptions versus code facts)

- A4 ("reserves against a registered completion bound, e.g. 2 x max_tokens"): with a gateway that does not enforce
  max_tokens and may leak reasoning, a bound of 2M turns rare replies into GLOBAL halts, because the breach check runs
  before any resend (calls.py:182-184, ledger.py:67, budget.py:8-11). The "e.g." leaves room: register B as the measured
  hard output ceiling (E7).
- A6 ("faults never become infrastructure unknowns"): the spec's own P3 does exactly that through `stats.bounds`
  (E30), and the copied ALFWorld loop would turn sandbox stops into infrastructure unknowns (E14).
- A3 ("a re-execution must reproduce identical requests"): not achievable with `python -I` workers and fork-per-call
  double runs unless the hash secret is fixed (E4) and file I/O is blocked (E3).
- A5 (format guard = contract sentence as instruction + no reply alteration): necessary but not sufficient for the
  owner-approved rule "格式不许进入可学习的部分", because notes are learnable text (E8).

## Best ideas worth keeping in the synthesis

1. The container is the security boundary; the AST/import policy is declared hygiene only, and D6's host-process runner
   is rejected as a boundary (§1.8). Keep, with E2-E5 fixes.
2. A long-lived container per cell/episode with fork-per-call children and host-held explicit `state`, argued against
   container-per-call with a cost estimate (§1.8). Keep, with fd redirection, fixed hash secret, RLIMIT_FSIZE = 0.
3. Procedure faults are fail-open rows (P1-P7) placed in front of the frozen `classify` without editing it, plus a fault
   cap as an acceptance condition (§1.10, §5.3). Keep, with the E30 token fix.
4. The deciding-receipt rule for multi-call cells (rows 4-5 read only the receipt whose reply is final; all receipts
   charged), which closes a real v3 misclassification path (§1.5.2, R21).
5. The designer's own contradiction note: the `max_tokens: 2` probe was sent with reasoning ON
   (probe_elucid2.py:36), so non-enforcement is unproven; enforcement is a launch blocker (§3.1). Keep the blocker, change
   B (E7).
6. One exception-class set with a unit test that a `BudgetStop` inside a copied cell maps to stop kind `budget` (§0.3).
7. The zero-call equivalence test "empty package == frozen `backends.solve`" (§1.5), fixed for the canonicaliser (E18).
8. A write-once consumption registry fsynced before dispatch, spanning smoke, pilot and full run, with slices cut from
   ONE seeded order and `skipped` slices (§2.3).
9. The ALFWorld canonicaliser for every arm, its rescue share per arm, and the "interface-mediated" label rule (R5).
10. The native slot held only around each execution, never across a model call (fixes the v3 `on_reply` deadlock risk).
11. Separate solver scopes for examiner probing, so examiner work cannot starve acceptance (§1.11).
12. Test-side cells store hashes only; the multi-arm test unit is keyed `(arm, task_id, run)`; an evaluation is reused
    only when package, card, contract, shell/router/judge/sandbox code, client and runtime hashes all match (§7.1).
13. Blocked acceptance (ALFWorld 4 blocks) to bound redo waste -- extend it to SearchQA and OfficeQA (E12).
14. The honest selection-limit statement for predictive validity (the sieve hides generators that block good
    candidates) and the optional audit D12 (§6.3).
15. The evidence label `engineering_fixture`, fixtures never counted; the smoke with fault injection and a recovery drill
    (S2 `fx-crash`, S4) -- keep, with format gating on every bench (E13) and the escape probe fixed (E15).
16. `unset OPENAI_API_KEY OPENAI_BASE_URL` in every run script and a scrubbed docker CLI environment (§1.8, §1.15),
    with a pinned absolute docker path (E25).
17. Twins only when S' has >= 2 changes (with one change S'-p equals S), which saves cost without losing the causal
    reading (§5.4).

## 给负责人的简短说明（中文）

这份是对"工程与安全优先"那份设计稿（spec-engineering）的反方审查，专门找"运行时会不会坏"。总体结论：**需要修改后再登记**；
方向是对的，但有 1 处按原文会直接让第一个 bench 的验收失效，另有十几处会让实验暂停或测量失真。下面的编号 E1、E2……是本审查
文件里各条问题的编号。

- **E1（致命，按原文）**：设计规定"隔离箱"（运行模型写的小程序的 Docker 容器）和外面的"壳"（固定代码）之间，每条消息最长
  64 KB；但 SpreadsheetBench（表格题）要把整张输入表格塞进这条消息。我在开发机上量了 89 道训练题的第一张输入表：有 8 道超过
  这个长度。这些题上每个过程都会"出故障"，故障率约 9%，远超"故障率超过 2% 就不收"的规则，所以表格 bench 上任何候选都会被拒；
  而冒烟只用 6 个手写的小表格，查不出来。改法：表格作为只读文件交给隔离箱，不放进消息；冒烟前先量所有训练题的大小。
- **E7（严重）**：新接口如果偶尔不听"关推理"的设置，一条回答里的推理 token 会超过"账本"（记 token 用量的固定代码）假定的
  单次上界 B（设计里 ALFWorld 只有 2,048）。现有账本一旦发现超界，会**整机所有实验一起停**，而不是设计里写的"重发"。
  建议把 B 定为接口的硬上限，并在冒烟里用几百次调用量"漏推理"的比例。
- **E6、E30、E14（严重）**：几种情况会让模型写的代码把实验"暂停"，违反"过程出错只当它不存在"的原则：两次调用的题重跑时
  必然对不上号；"不确定性故障"被统计成基础设施故障，超过 1/10 就暂停；ALFWorld 循环里的隔离箱故障会被吞掉，
  可能留下没清理的容器。
- **E2–E5（严重）**：隔离箱的几处具体规定会出问题：程序里一个 print 就能搅乱壳与隔离箱的通信；"隐藏状态不可能"不成立
  （可以借 /tmp 文件）；"运行两遍比对"查不出 Python 集合顺序造成的不确定；内存上限很可能低于预加载计算库后的占用，
  导致每次调用都失败。都给了具体改法，冒烟时要逐条实测。
- **E8（严重）**：格式护栏只管了"系统提示和最终回答不被改"，但过程往提示里加的"说明文字"本身可以要求换答案格式——这正是
  昨夜 E4、E9 里 9.5 到 33 分负迁移的来源。需要固定的格式检查器，并把"格式错误率不得比旧版本高"写进验收条件。
- **E9、E10（严重）**：回放测试和检测器验收都能被轻易满足（例如"永远启用 + 固定一句话"就能通过回放测试；重复已有的
  "50 步用完"规则就能当新检测器被收下），需要加"新旧版本必须有差别""只在未被覆盖的失败上算准确率"等固定规则。
- **E12、E13、E29（严重）**：暂停后整单元重做会撞上本步预算上限；冒烟只在 SearchQA 上检查答案格式，查不出其他四个 bench
  的格式问题（第 3 版冒烟正是靠四个 bench 的格式检查发现了表格题的问题）；按原文重跑 SearchQA 抽题脚本会把封存的 C/D 块
  内容写到开发机上。
- 其余 18 条是小问题（逃逸探针按原文永远通不过、清单缺少若干钉死项、ALFWorld 否决动作的边界情况等），实现时顺手改。
- 值得保留的好做法见上一节（17 条），例如"容器才是安全边界"、"过程故障单独记账且有上限"、"只用决定性回执判定"、
  "题目消耗先登记后发出"、"测试格只存哈希"等。
