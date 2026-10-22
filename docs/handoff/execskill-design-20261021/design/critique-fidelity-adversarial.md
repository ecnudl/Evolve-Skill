# Critique of spec-fidelity.md -- LENS 2 (engineering and adversarial: try to break the runtime)

Critic: adversarial reviewer (read-only). Date: 2026-10-21 (first pass 18:08-19:10 wrote F1-F2; restarted 19:20 after the
agent limit and completed). Target:
/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/spec-fidelity.md
(cited as `spec:<line>`). Code citations are repo-relative to /Users/dulin/Documents/Paper/SkillOpt. Map citations:
`SP/understand/<file>.md:<line>`. No pytest, no model call, no test-pool path, nothing outside this file written.
Status: COMPLETE.

Verdict: **needs_revision**. 0 fatal, 18 major, 9 minor. The spec is the most faithful of the drafts to design-v0 and to
the reviewed v3 machinery, but as written its runtime can be stopped by one careless line of model-written code, two of
its acceptance-side checks (replay tests, detector acceptance) and the examiner's headline claim on ALFWorld are trivially
satisfiable, the copied cell layer keeps two v3 behaviours that break every two-call cell, and the leakage pipeline it
copies would drop the flagship procedure of design-v0.

Conventions: "measured (source)" = a number read from code, logs or a reader map; "estimate (assumptions)" = mine.

---------------------------------------------------------------------------------------------------------------------

## A. Findings (numbered; severity in brackets; most severe first within each class)

### F1 [major] `reasoning_mismatch` cannot be resent with the modules the spec imports unchanged
- Attacked text: spec:53-55 "Import unchanged ... `skillopt.coevo5.{budget, ledger, calls, outcomes, ...}`" together with
  spec:434-435 "`reasoning_mismatch` joins `UNDELIVERED_ERRORS` (resend <= 2 after a 300 s cooldown, then infrastructure
  unknown)" and row 12e (spec:353).
- Why it breaks: the resend decision is taken inside the imported, frozen `calls.Recorder.__call__` (calls.py:268-279),
  which calls the frozen `outcomes.undelivered` (outcomes.py:176-182) over the frozen set (outcomes.py:66-67). A new error
  type that exists only in an execskill copy of `outcomes` is invisible to the frozen Recorder: the reply is never resent.
  In addition, the inherited `Client._receipt` keeps only `prompt_tokens/completion_tokens/total_tokens`
  (scripts/weak_solver_probe.py:220-224 `_usage`, used at :289), and raises `thinking_mismatch` only when
  `self.thinking == "disabled"` (:295-296) -- but the spec sends no thinking field. So
  `usage.completion_tokens_details.reasoning_tokens`, the first half of the registered test, is dropped before any check can
  read it. As written the per-receipt check is unimplementable without editing a frozen file or silently copying more
  modules than spec:53-60 lists. The spec also contradicts itself: spec:53 imports `outcomes` unchanged, spec:343 adds rows
  12a-12e to a "copied `outcomes.classify`".
- Fix: (a) the elucid subclass overrides `_receipt`/`_usage` to keep `completion_tokens_details` and the
  `reasoning_content` length; (b) when reasoning appears it returns `error_type = "thinking_mismatch"` (already in the frozen
  UNDELIVERED_ERRORS, so the frozen Recorder resends and frozen row 4 applies) plus a receipt field
  `reasoning_mismatch: true` that the execskill report counts; (c) state which functions of `outcomes` are copied
  (classify with rows 12a-12e) and that the copy imports the exception classes and `undelivered` from
  `skillopt.coevo5.outcomes`; (d) unit test: a fake receipt with reasoning tokens -> exactly 2 resends, then row 4.

### F2 [major] Re-execution (`_replay`) breaks on every two-call cell
- Attacked text: spec:60 "Copy with the new VERSION ... `cells.py`" (no change listed), 1.6.2 (repair = two calls),
  spec:316-317 test 5 "Re-execution of any cell from stored replies reproduces identical request hashes (cells.py:139-149)
  including the firing plan and the sandbox outputs".
- Why it breaks: the frozen remedy replays only the LAST send: `reply, request = recorder.receipts[-1],
  recorder.sends[-1]["request_sha256"]` and `require(_request_hash(system, user) == request)` (cells.py:139-149). It is
  triggered for SpreadsheetBench `native_timeout` and execution-environment failures (outcomes remedy REEXECUTE; loop at
  cells.py:208-209). On a repair cell the re-executed shell issues call 1 first, whose hash differs from `sends[-1]`
  (call 2), so `require` raises -> generic exception path -> unit Pause (cells.py:215-218, 232-233). Worse, a re-execution
  re-runs the repair PRE-CHECK, i.e. the SOLVER's program (model output, not bound by the procedure determinism rules: it
  may time out near the limit), so the branch (call 2 or not) can differ on replay. Test 5 asserts a property the copied code
  does not have.
- Fix: register a generalised `_replay` that replays the ordered list of sends (hash i == `sends[i]`, reply i ==
  `receipts[i]`) and store the pre-check result (exception class + message + "output written") as a cell artifact that
  replay READS instead of re-executing. Unit tests: a two-call compute cell and a two-call repair cell, each with a
  `native_timeout` on the final program, re-execute without a Pause.

### F3 [major] One careless line of procedure code stops the chain: worker death and protocol corruption are classified as infrastructure (row 12c -> Pause), contradicting A6
- Attacked text: spec:329-336 (long-lived worker, line-delimited JSON over stdin/stdout, "per-request CPU limits (RLIMIT_CPU
  inside the worker)"); row 12c spec:351 "worker protocol breaks without a procedure-attributable error ... one retry ...
  then `Pause("sandbox_unavailable")`"; spec:172-174 forbidden names (no `print`).
- Why it breaks (each is a plausible accident, not only an attack):
  1. `print` is not forbidden (spec:172-174). The worker's stdout IS the protocol channel (spec:330). A debug `print()` in
     `applies` writes a non-JSON line; the host cannot parse it -> "protocol breaks" -> 12c -> retry (same code, same
     print) -> Pause. The zero-fault sweep (spec:558-560) runs every candidate in the sandbox on every recorded trajectory
     BEFORE acceptance, so the chain pauses inside the engineer unit on the first such candidate.
  2. RLIMIT_CPU is cumulative per process, so "per-request" limits need the soft limit re-armed before each request and a
     SIGXCPU handler; a long C-level call (regex backtracking on a 30,000-character OfficeQA context, a pandas/numpy
     operation) does not return to a Python handler, the hard limit sends SIGKILL, the worker dies -> 12c -> Pause.
  3. `--memory=1024m` (spec:324) is a cgroup limit: an allocation above it makes the kernel OOM-kill the worker (the
     container's only process) -> 12c -> Pause. Smoke S2's "2 GiB allocation vs 1 GiB" (spec:882) counts this as
     "contained", but in production the same event is a chain stop.
  4. `load` (top-level code of the procedure source) and `state_init` have no limit at all (spec:333-334 list applies, run,
     advise, state ops, evaluate, detect, generate only): a module-level loop hangs until the per-worker wall limit.
  5. After an owner-approved resume the same procedure kills the worker again: the pause is deterministic and the spec has no
     remedy, so the batch can only be burned.
- Fix: (a) the worker dups the protocol onto a private fd (e.g. fd 3) at start and points fd 1/2 at a bounded capture
  buffer; captured output beyond a cap is a procedure fault; (b) per-request host-side wall timeout in addition to the CPU
  limit; `RLIMIT_AS` re-armed per request below the cgroup limit so Python raises MemoryError instead of being OOM-killed;
  (c) any worker death, timeout or unparsable line while a request is in flight is attributed to that request's
  `(proc_id, op)` -> row 12a/12b/12d (procedure fault, fail-open), the worker is respawned WITHOUT that procedure (for
  ALFWorld the remaining `state` procedures are rebuilt by replaying `state_update` from step 0, they are deterministic);
  (d) 12c is reserved for: container cannot start, cleanup unconfirmed, or two consecutive deaths with NO request in flight;
  (e) limits for `load` (2 s) and `state_init` (2 s); (f) smoke S2 adds probes for `print`, reading stdin, `os._exit` reached
  through an allowed library, catastrophic regex, 2 GiB allocation, module-level infinite loop -- each must end as a logged
  procedure fault with the cell scored, never as a Pause.

### F4 [major] The worker wall limits contradict measured episode and call durations
- Attacked text: spec:334 "per-worker wall limit 900 s (episode) / 300 s (cell)"; spec:329-330 one worker per ALFWorld
  episode and per QA/Sheet cell with post-call execution; spec:444 read timeout 600 s, client attempts <= 4.
- Why it breaks: v3 ALFWorld training episodes took median 290 / 348 s and p90 785 / 1,929 s per episode under
  contention -- measured (SP/understand/linux-ops.md:80-81, I-ds / E-ds s5). An episode worker that must live for the whole
  episode is killed by its own 900 s limit in a large share of slow episodes (p90 1,929 s > 900 s), i.e. mostly in
  serving-slow windows; the spec does not say whether that is 12c (Pause) or 12d (procedures disabled mid-episode). Either
  way the outcome depends on gateway latency and is arm-dependent (arm C has no worker). A QA cell worker started with the
  cell dies after 300 s while call 1 may legitimately wait 600 s per attempt (spec:444) -- one ReadTimeout already exceeds
  the worker's life; the v3 smoke had a dozen requests hang to the read timeout simultaneously -- measured
  (SP/understand/linux-ops.md:86).
- Fix: no wall-lifetime limit tied to solver latency. Limits are per request (CPU + wall, F3); an idle worker waits as long
  as its cell is alive; QA/Sheet workers start lazily after reply 1; register a separate idle cap (e.g. 3,600 s) that is
  larger than the measured episode p90 and a smoke assertion that no worker died of the idle cap.

### F5 [major] The AST denylist is not a sandbox, and "pure / deterministic / no I/O" is asserted but not enforced; cross-item state allows transduction over test inputs
- Attacked text: spec:170-176 (allowed imports incl. `sympy`, `pandas`, `numpy`, `openpyxl`; forbidden names; "no clock, no
  randomness, no I/O"; "checked twice per replay test"); spec:240-242 "Because predicates and `note` bodies are pure
  functions of the public view, the plan is exact"; spec:335-336 "Each `load` execs the procedure source in a fresh module
  namespace" (one namespace per worker lifetime, not per item).
- Why it is wrong: the allowed libraries contain exactly the forbidden capabilities -- `sympy.sympify`/`parse_expr` evaluate
  strings with Python `eval`; `pandas.eval`/`DataFrame.query` evaluate strings; `pandas.read_*`, `numpy.load`/`fromfile`,
  `openpyxl.load_workbook(path)` do file I/O; `pandas.Timestamp.now()` is a clock; `numpy.random` is randomness; `print`,
  `id`, dunder ATTRIBUTE access (`x.__class__.__mro__`, `f.__globals__`; only getattr/setattr CALLS are banned) and
  `str.format` field traversal are all allowed. Two concrete consequences:
  1. `compute`: the `<calc>` text is written by the SOLVER (spec:266-270) and handed to the procedure's `evaluate`; an
     `evaluate` that uses `sympify` executes solver text inside the worker (contained by docker, but it can print/exit ->
     F3).
  2. Module globals, `functools.lru_cache`, mutable default arguments and class attributes persist across items inside one
     firing-plan batch worker (one worker for ALL items of a round, spec:329). A procedure can therefore carry state from
     item i to item j: notes depend on plan order (the "plan is exact" and re-execution claims fail), and at the test read
     a procedure can accumulate the public views of all test items and emit cross-item content (transduction over the test
     set). "Checked twice" does not catch it if both executions run in fresh workers, or if the state only matters after
     the 9th call (replay tests are 1..8).
- Fix: state plainly that the container (no network, read-only, no secret mounted) is the only security boundary and the
  AST rules are hygiene; pin the worker-dir contents (only `execworker.py`, sha-pinned, as `_native` does,
  backends.py:162-168); enforce purity by construction: re-exec the procedure module in a fresh namespace for every
  (procedure, item) call (cheap), ban `global`/`nonlocal` statements, mutable defaults, class-level mutation and
  `lru_cache`/`cache` decorators; ban by name `sympify, parse_expr, eval, query, read_*, load, fromfile, loadtxt,
  load_workbook, now, today, random`; provide a shell-owned exact evaluator (`forward.evaluate`, an AST-whitelisted exact
  arithmetic evaluator, forward.py:196-203) that `compute` bodies call instead of sympy on solver text; determinism check =
  the plan computed twice in two fresh workers with two different item orders, byte-compared.

### F6 [major] Replay tests are trivially satisfiable, and an ALFWorld tracker can be wrong without any check noticing
- Attacked text: spec:162-167 (`ReplayTest{trace_ref, expect_fires, property_src}` -- all written by the engineer);
  spec:556-557 "Replay test passes iff `applies` returns `expect_fires` ... `check(inputs, outputs)` is True, and a second
  execution is byte-identical"; spec:561 "Replay proves determinism and absence of crashes, not repair".
- Why it is wrong: the engineer writes the predicate, chooses `expect_fires` and writes `check`; `def check(i, o): return
  True` with `expect_fires=True` on a predicate that always fires passes. design-v0 asks for replay on "它声称能修的那些
  失败记录" (SP/design-v0.md:7); the spec keeps the name but drops the content, and nothing replaces it. On ALFWorld this
  leaves the lens question "what if the tracker is wrong" unanswered: the D3 learned tracker disagreed with the hand tracker
  on 174 of 7,524 steps -- measured (spec:122, FP F1/F6-F9) -- and a wrong "已去过、都没有目标物" note actively steers the
  agent away from the target. No runtime or pre-acceptance check compares a learned tracker with the simulator facts.
- Fix: register FIXED, hook-specific properties that the engineer cannot write: `state` must expose
  `facts() -> {location, holding, visited: {receptacle: [objects seen]}}` and agree with the registered reference tracker
  (`tracker_ref.py`, D3's 62-line hand tracker) on >= 97% of steps of all recorded run trajectories, incl. "Nothing happens."
  steps (no location change after an inadmissible action); `advise` entries must be admissible and justified by `facts()`
  (e.g. `go to X` only if X is visited-empty); `compute.evaluate` must equal the shell's exact evaluator on every recorded
  expression it accepts; `note` emissions pass the lint and byte caps. Non-triviality: the predicate must fire on >= 1
  targeted failure trace AND not fire on >= 1 recorded trace, and its fire rate on the run batch must lie strictly in (0, 1)
  or be justified as "all items of hook kind". Rename the owner-facing term to "可靠性检查" unless a repair property exists.

### F7 [major] Detector acceptance -- and therefore "examiner evolved" -- is satisfied by re-expressing the verdict
- Attacked text: spec:669-671 (the detector's trajectory view includes `steps`, `format_flags`, `activation`);
  spec:674-677 (precision/lift/binomial/recall thresholds); spec:731 "Examiner evolved at step g iff >= 1 model-written
  detector passed 6.1".
- Why it is wrong: in ALFWorld every v3 failure was a 50-step timeout (68/68 and 56/56 -- measured,
  SP/understand/feasibility-prototypes.md:111), and an episode stops early exactly when it is won
  (backends.py:768-770 `if won or dones[0]: break`). So `len(traj["steps"]) == 50` has precision 1.0 and recall 1.0 on the
  verdict. On QA, `format_flags["truncated"]` is a fail by definition of the decision metric (spec:478-479); on
  SpreadsheetBench `no_output_written` / `program_crash_precheck` nearly are. Any detector written in terms of these (or of
  correlates such as "visited >= 20 receptacles") passes 6.1 with n_f >= 12 and makes "examiner evolved" true without
  diagnosing anything the mechanical library (spec:528-532) does not already know.
- Fix: (a) accept a model-written detector only on the RESIDUAL: precision, lift and recall computed on CHECK-half cells on
  which no mechanical or previously accepted detector fires; (b) model-written detectors see an ALFWorld trajectory truncated
  to a registered prefix (e.g. the first 30 steps) and a QA/Sheet view without the verdict-defining flags (`truncated`,
  `empty_reply`, `no_output_written`); (c) "examiner evolved" requires >= 1 accepted residual detector; report how many
  accepted detectors are logically implied by mechanical ones.

### F8 [major] On ALFWorld an identity "generator" passes G1-G4, so the examiner's headline claim is trivially satisfiable on the recommended pilot bench
- Attacked text: spec:705-707 "ALFWorld: a selection program over the GEN region ... truth = the simulator's `won`";
  spec:712-713 (band [0.20, 0.80]); spec:719-723 (G4 sign agreement); spec:732 "Examiner validated (the headline claim of the
  examiner side) iff >= 1 generator has >= 1 eligible agreement and no retirement"; spec:39-41 owner summary recommending the
  ALFWorld pilot because "考官两半都能进化".
- Why it is wrong: `generate = lambda src, rng: src` (select games at random) passes G1 (simulator truth), G2 (v3 pass rates
  on training games were 40.4% and 50.9% -- measured, SP/understand/feasibility-prototypes.md:108-109 -- inside the band),
  G3 is N/A (spec:718), and G4 compares S'-S on a second random batch of the same game distribution with S'-S on the
  acceptance batch -- a replication test, which agrees whenever the real effect is non-trivial. So "examiner validated" and
  novelty claim (1) (spec:813) can be earned by a no-op examiner, precisely on the bench the spec recommends as the pilot.
- Fix: register a NULL selection generator (seeded uniform draw from the GEN region) run beside every model-written one; a
  selection generator counts only if its `G_self` set differs from the null draw by a registered amount in its declared
  target feature (e.g. share of games whose goal object starts inside a closed receptacle, readable from the initial
  observation) AND its G4 agreement is reported next to the null's; or exclude ALFWorld selection generators from the
  "examiner validated" claim and say "on ALFWorld the examiner selects, it does not generate".

### F9 [major] The 3-slot native deadlock is not removed by the copied cell layer
- Attacked text: spec:285-286 "The native slot is taken only after the FINAL reply, never between calls, to avoid the 3-slot
  deadlock" together with spec:60 (cells.py copied with only a new VERSION).
- Why it breaks: the frozen `_solve` installs `on_reply` that enters `context.native.hold()` (cells.py:126-132) and the
  Recorder calls `on_reply` after EVERY reply (calls.py:277-278). A two-call repair cell therefore takes a native slot after
  call 1, keeps it through the pre-check and call 2, and tries to take a second one after call 2. With 3 native slots and
  12 cell workers, three such cells each hold one slot and wait for another forever (`Slots.hold` polls without a timeout)
  -- the reader map flagged exactly this (SP/understand/solver-backends.md:363-366, G3). The spec states the intention but
  not the code change.
- Fix: list the change in the copied `cells._solve`: no `on_reply`; the shell takes the native hold once, after the final
  reply, around the frozen per-case execution only; unit test with 3 native slots, 12 workers and only two-call repair cells
  must finish.

### F10 [major] The SpreadsheetBench pre-check does not reproduce the frozen execution, and runs unrestricted solver code inside the procedure worker
- Attacked text: spec:278-286 ("the shell runs the program once in the route-B sandbox on the single public input case ...
  The frozen per-case `_native` execution ... then run on the final program") and the sandbox command spec:322-327.
- Why it breaks: the route-B command differs from the frozen one (backends.py:169-178): `--pids-limit=64` vs 128,
  `--ulimit=nofile=64:64` vs 256, tmpfs 64m vs 256m, no `--shm-size=64m`, no `OMP_NUM_THREADS=1` /
  `OPENBLAS_NUM_THREADS=1` / `MPLCONFIGDIR`, no `--no-healthcheck`. A program can crash in the pre-check and run in the
  frozen execution (or the reverse), so repair rounds are triggered on programs the frozen scorer would have accepted
  (call 2 may replace a working program) and missed on programs it rejects. Second, the SOLVER's program needs `open`/`os`
  and is not under the AST rules; if it runs in the same long-lived worker that hosts the procedure's `advise`
  (spec:329-330), it can print into the protocol channel, `os._exit`, or overwrite the procedure's namespace.
- Fix: the pre-check is a separate one-shot container launched with the frozen command line and environment byte-for-byte
  (a copy of `native_worker.py` that additionally returns exception class + 500 B of message), holding the native slot only
  for that execution and releasing it before call 2; `advise` runs in the procedure worker on the returned error dict only;
  the pre-check record is stored for replay (F2); test-read items with several cases pre-check case 1 only (state it).

### F11 [major] The `repair` placebo removes the shell's own error feedback, so S' > P can be passed by trivial advice
- Attacked text: spec:603-604 "`repair`: same trigger ...; call 2 carries only the fixed text 'The program did not run
  successfully. Return the complete program again.' (no error message, no advice)".
- Why it is wrong: in S' call 2 carries `previous_program` + `execution_error` + `advice` (spec:282-283). The error message
  and the second attempt are produced by FIXED shell code, not learned; only `advice` is learned. With the sham stripping
  the error message, D2 (S' - P > 0, spec:623-624) measures "error feedback + advice" vs "blind retry": a repair procedure
  whose advice is "Fix the error." passes D2 on the strength of the shell. This is the "answer repair is not Skill evolution"
  boundary (AGENTS.md) inside the acceptance rule.
- Fix: the sham call 2 carries the same `previous_program` and `execution_error` and a length-matched irrelevant `advice`
  from the placebo corpus; report the within-cell `first_reply_v2` vs final (spec:480) per arm so the shell's own repair
  effect is visible separately.

### F12 [major] The copied leakage pipeline, applied to emissions, mechanically drops the flagship context-extraction procedures
- Attacked text: spec:177-180 "the mechanical checks run on the description, every string the procedure EMITS on the replay
  inputs, and every string/number literal ... compared against the active bench's training pool surfaces and references;
  any non-`answer_word` hit drops the procedure".
- Why it breaks: v3's mechanical checks drop on 8 shared consecutive words with an item's task surface (question + context
  pages) and on any number equal to an OfficeQA reference with >= 3 significant digits (leakage.py:7-14). A `note` that
  re-presents table rows of the item's own context ("抽取数字", design-v0's OfficeQA example, SP/design-v0.md:15) shares
  8-grams with that item's surface by construction, and on look-up questions it reproduces the reference number. The
  pipeline was built for text rules that must not quote training items; a procedure's emission on item i is SUPPOSED to
  quote item i's public text. As specified, the best-motivated procedure class cannot be accepted.
- Fix: check emissions only for content that is NOT present in the same item's public view (subtract own-surface n-grams and
  own-context numbers before the check), check code literals/regexes against the surfaces and references of all pool items,
  and register a unit test that the S3 fixture notes ("numbers in the context with their years and units") pass the
  pipeline.

### F13 [major] LiveMath: a procedure can encode the "meta option is always the key" label regularity; the spec forbids it for generators only
- Attacked text: spec:687-691 (the label-regularity ban applies to generators); 3.2 (the engineer sees run-slice references);
  the emission lint spec:231-233; no options-only probe for procedures.
- Why it is a hole: the LiveMath meta option appears in 129/283 training items and is the key in all 129; "pick it whenever
  present" was estimated at 76% vs the task card's 33%, and 42-84% of earlier LiveMath gains came from it -- measured
  (SP/understand/feasibility-prototypes.md:303-305, :368). The engineer sees references of failures, so the regularity is
  visible. A note whose predicate is `re.search("stronger result", choices)` and whose emission is neutral mathematics
  ("Check whether a stronger statement than the listed ones can be proven") escapes `option_text` (it checks that the whole
  correct option text appears, leakage.py:14-16), escapes the lint, and may pass the adjudicator; acceptance on fresh LiveMath
  items then rewards a dataset artefact, and the LiveMath test set very likely shares it.
- Fix: apply the G3 idea to procedures: at LiveMath acceptance add arms S'_masked and S_masked on A* with the question
  replaced by "[question withheld]" (as G3, spec:715); reject S' if S'_masked - S_masked >= 0.10; report every LiveMath
  contrast split into meta-present / meta-absent items and require the own-gain claim to hold on meta-absent items;
  the engineer's LiveMath evidence shows the meta option's key status blinded.

### F14 [major] With max_tokens unenforced, COMPLETION_BOUND turns a single runaway reply into a global ledger halt; "safe either way" is wrong
- Attacked text: spec:101-107 (C1: the bound rule "is safe either way"); spec:436-440 (`COMPLETION_BOUND = 2 x max_tokens`;
  "global halt only if `completion_tokens > bound`"); spec:881 (S1: "not enforced: the bound rule of 3.1 stays the only
  protection").
- Why it is wrong: the frozen settlement marks a breach when `completion > max_tokens` of the Endpoint (ledger.py:67), and
  the Endpoint then raises `AssumptionBroken(BREACH)` (calls.py:184), which halts the shared ledger for every process. If the
  gateway does not stop generation, nothing bounds a degenerate repetitive reply except the model's server-side maximum and
  the 600 s read timeout; a reply that finishes inside 600 s above 2 x 16,384 tokens halts the whole chain. "Safe" here
  means "budget-safe by stopping everything", and the runaway rate is unmeasured. Also, a ReadTimeout attempt is charged
  only its bound while the provider may have billed more (ledger counts the last attempt's usage, SP/understand/linux-ops.md
  F38).
- Fix: if S1 shows non-enforcement, enforce the cap client-side: stream the completion and close the connection at the
  nominal max_tokens (or a registered character equivalent), so `completion <= bound` holds by construction and the reply is
  marked truncated (= fail). Otherwise register `completion > bound` as a per-cell `over_bound` event charged at reported
  usage with reservations sized to the model's documented maximum output, not a global halt; S4 reports the observed share
  of replies above nominal per bench.

### F15 [major] The smoke would not catch the defects the v2/v3 format checks caught on the new paths, and never exercises the fault paths
- Attacked text: spec:884 S4 "per bench 20 items ... x arm C x 1 run ... required-format pass >= 9/10"; spec:883 S3 pass
  criterion (no format rate); spec:878-887 (no stage for reasoning_mismatch, over_nominal_completion, worker-death
  attribution or pause/resume).
- Why it is insufficient: v3's format check ran three Skills and failed a Skill whose share was below the floor OR more than
  1/20 below the empty Skill's (smoke.py:71-77, :300-309); it also recorded that an unchanged prompt moved from 20/20 to
  16/20 between two runs (smoke.py:74-75, measured), i.e. 20 single-run items is a noisy floor. Route B's new format risks
  are in the procedure paths -- reply 2 of the `<calc>` round trip (does it still carry `<answer>`?), reply 2 of `repair`
  (does it still deliver a fenced program?), notes-induced verbosity on ALFWorld (> 1,000 untagged characters is an
  instant malformed episode, backends.py:754-756) -- and S4 tests none of them (arm C only); S3 exercises them on 4 items
  with no format criterion. The smoke also never forces the error paths this spec adds (F1, F3, F14) or a resume.
- Fix: S4 = arms C and F_fixture (fixture compute/repair/state firing) x 20 items x 2 runs per bench, floor 9/10 on the
  scored reply of F_fixture AND margin 1/20 below C, reported separately for reply 1 and reply 2; ALFWorld per-step action-tag
  and > 1,000-char rates; zero-call fake-receipt tests for reasoning_mismatch (2 resends then row 4) and
  over_nominal_completion; S2 fault probes of F3 must end as procedure faults; a pause/resume drill in S7 (kill the unit
  mid-round, resume as attempt-2, assert no duplicate registry lines and identical plan/twins).

### F16 [major] The 2% fault cap (D3) can be evaded through plan-time faults
- Attacked text: spec:625 "(D3) S' cells with >= 1 fault of a procedure in N <= 2% of S' cells"; spec:638-645 (A* = items
  where some procedure of N fires; `A \ A*` is never dispatched).
- Why it is a hole: a procedure that faults in `applies` during the firing plan is recorded as not fired on that item
  (12a); if no other procedure of N fires there, the item leaves A* and is never run, so its fault never appears among S'
  cells. A predicate that crashes on 30% of real items passes D3 with 0 counted faults and is accepted; at the test read the
  same items silently run without it.
- Fix: D3's numerator and denominator include plan-time faults over the whole acceptance slice A (faults of N's procedures on
  any item of A / |A|) plus run-time faults over S' cells; the same count is reported per bench at the test read.

### F17 [major] Replay-test properties are said to run "on the host-side replay record"
- Attacked text: spec:166 "`property_src` ... run on the host-side replay record".
- Why it matters: read literally, model-written code runs on the host, outside the sandbox (violating A3), where it could read
  `/root/.config/weak-solver/elucid.env`, the ledger, sealed test files; read charitably, the record it receives may be the
  host-side cell record, which carries the verdict and the reference. Either reading breaks the input whitelist of spec:181-184.
- Fix: one sentence: properties run in the sandbox like every other model-written function, on a whitelisted replay record
  `{view (whitelisted), procedure outputs, fault}`, never the verdict, reference, `private` or paths.

### F18 [major] The format guard is outside the learnable part only for the system prompt; answer-form advice can still enter through notes, and later benches are unprotected
- Attacked text: spec:221-233 (1.4: contract sentence fixed; emission lint
  `<\s*/?\s*(answer|action)\b|```|\bjson\b|\breturn only\b|\bformat\b|\bletter\b|...`); 4.7 scope rule (spec:582-585, earlier
  benches only).
- Why it is risky: the measured negative transfer of E4/E9 was format conflict, -9.5 to -33 points (spec:210, FP F51-F52).
  The lint is a short blacklist: "Respond with just the number, no units", "give the value rounded to two decimals",
  "write only the option" pass it; scope "all" notes fire on every bench where their predicate holds, and the only
  cross-bench format check (self-test, spec:570-571) covers EARLIER benches' generated sets -- a note learned on
  SpreadsheetBench that fires on LiveMath (a later bench) is checked by nothing before the test read. The lint also has false
  positives: `\bformat\b` rejects legitimate SpreadsheetBench notes about number or date formats.
- Fix: replace the word list by a registered answer-form phrase list (imperatives about final-answer shape: "answer with",
  "respond with", "only the", "final answer", "units", "decimal places", "round", "letter", "tag") applied to emissions, with
  a domain exception for SpreadsheetBench cell formats; put notes under a fixed shell header ("Background notes; they do not
  change the required answer format"); at the test read report each procedure's withholding contrast on the FORMAT flags
  (from the twin cells already run) and label `harmful (format)` when its CI lies above zero.

### F19 [minor] Input whitelist contradiction: `_PUBLIC` contains host paths
- spec:181-184 filters by `_PUBLIC` (backends.py:57-62), whose SpreadsheetBench entry includes `input_files` (host paths
  containing task ids) and whose ALFWorld entry is `game_file` (a path that names goal object and receptacle), while the same
  sentence says "never ... file paths". A procedure could key behaviour on a task id that the leakage checks (surface/answer
  based) never see. Fix: procedures get the solver's rebuilt view (backends.py:406-409: instruction, workbook_preview,
  input_path "input.xlsx", required_answer_position) plus the shell-parsed sheet view (F21); ALFWorld only the step view.

### F20 [minor] Stale identity premise
- spec:48-50 says the v3 files are "still untracked" on the branch; they are committed (git ls-files lists 32 files under
  skillopt/coevo5 plus scripts/run_coevo5.py and scripts/weak_solver_probe.py; HEAD 010d453). Fix: pin the import base by
  that commit hash in the manifest and say so.

### F21 [minor] Raw workbook bytes into procedures: memory, time and response-size limits will fault systematically
- `note`/`repair` get `input_workbook_base64` (spec:182) and may load it with openpyxl/pandas under `applies` 2 s and 1 GiB
  (spec:322-334); workbooks up to 8 MiB are allowed (backends.py:37 MAX_WORKBOOK) and openpyxl's memory use is a large
  multiple of file size (estimate) -- large items fault (shrinking firing and inflating D3), and SpreadsheetBench generators
  returning two workbooks may exceed the 65,536 B response line cap (spec:332-333). Fix: the shell parses the workbook once
  (outside procedure accounting) into a bounded structured view (frozen `_sheet_preview` plus sheet names/dimensions); raise
  or exempt the response cap for `generate` with workbooks written to /tmp and returned by hash.

### F22 [minor] `advise` depends on an unnamed state procedure; withholding entangles procedures
- `advise(view, state_text)` (spec:158) does not say which `state` procedure's render it receives, and withholding a
  state tracker also changes what `advise` sees, so tau_p of the tracker includes the adviser's response (5.5). Fix: declare
  dependencies in the Procedure object (`requires: [proc_id]`); the router passes `facts()` of the named procedure; the twin
  that withholds p also reports which dependants lost input, and the label table marks entangled pairs.

### F23 [minor] Firing-plan computation is unbounded
- One batch worker per round (spec:329) evaluates every legal procedure on every item; at the registered caps the worst case
  for a SearchQA acceptance slice is 24 procedures x 1,000 items x (2 s + 5 s) ~= 46 h -- estimate (MAX_PROCEDURES 24,
  spec:192; per-request limits spec:333-334; every call at its limit). Fix: a per-procedure CPU budget per round (e.g. mean
  <= 0.2 s per item, else suppressed for the round as 12a) and the plan sharded over the sandbox pool.

### F24 [minor] Manifest and identity gaps
- ALFWorld items are identified by "sha12 of gamefile path" (spec:388) -- content is not hashed; the host's
  TextWorld/ALFWorld package versions are not pinned (manifest `environment()` pins only python and openpyxl,
  manifest.py:64-68); `evaluation.configuration()` digests `context.endpoint.max_tokens` (evaluation.py:308-311), which under
  the spec's implementation note is the BOUND, not the nominal value or `reasoning_effort` sent; send records label the bound
  as `max_tokens` (calls.py:153-154); the cell record's `skill_sha256 = digest(skill)` (cells.py:222) must include the
  arm_spec, or twin and placebo cells are recorded under S''s identity. Fix: hash game files; pin host package versions;
  digest the full request template (model, nominal max_tokens, bound, reasoning_effort, temperature, URL sha); record both
  nominal and bound; cell identity = (package sha, arm_spec digest).

### F25 [minor] Sandbox environment drift from the frozen native command
- spec:321-327 omits `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MPLCONFIGDIR`, `--shm-size`, `--no-healthcheck` that
  the frozen command sets (backends.py:169-178): numpy/OpenBLAS thread counts then follow the 7 visible host CPUs, which
  can change floating-point reductions between restarts (determinism check failures) and consume pids under
  `--pids-limit=64`. Fix: copy the frozen environment flags.

### F26 [minor] ALFWorld hook details left open
- `state.update(action, observation)` does not say whether `action` is the raw reply, the stripped string or the canonical
  admissible string actually sent (spec:291-292); it must be the string sent to `env.step`. Whether empty `notes` /
  `not_recommended` keys are omitted (byte-identity with the twin on steps where nothing fires) is not stated for ALFWorld
  (it is for QA, spec:247). A `state_fault` at step t (12d) disables the procedure, but its shadow in the placebo arm
  (spec:605) is not said to be disabled at the same rule -- state both.

### F27 [minor] Twins, placebos and the native image are fine on paper but one sentence each is missing
- The sham `advise` entries "none" (spec:606) are not admissible commands; state that they are rendered but never offered
  to the canonicaliser. The sham `compute` invitation is identical, but the sham evaluator's "unavailable" reply is the
  only difference -- good -- record it in the activation log so the twin-shape test (S3) can check it.

---------------------------------------------------------------------------------------------------------------------

## B. Best ideas of spec-fidelity worth keeping in the synthesis

1. Closed-set copy with one exception-class set imported from `skillopt.coevo5.outcomes` (spec:53-60) -- prevents the
   STOP_KINDS identity trap; keep, but list every behavioural change of the copies (F1, F2, F9).
2. Pre-dispatch firing plan for QA/Sheet sealed by hash, and the decision subset A* of items where a new procedure fires,
   with byte-identity of S'/S/P requests checked before dispatch (spec:239-243, 637-645): an honest, zero-call way to drop
   pure-noise items. Keep, with F16's fault accounting.
3. Placebo twins that keep predicate, slot and call trigger (spec:595-606), and the D1 AND D2 intersection-union rule
   (spec:620-630) -- keep, with F11's correction for `repair`.
4. Random withholding twins drawn before dispatch from the firing plan (spec:647-660), never a decision criterion, and the
   "identical by construction" rule that refuses to spend tokens on arms that cannot differ (spec:753-757).
5. Procedure faults fail open with their own decision-table rows instead of falling into the infrastructure-unknown row
   (spec:343-356) -- the right principle; F3 makes it actually hold.
6. Completion-aware truncation that does not rely on `finish_reason` alone, the explicit `over_nominal_completion` flag,
   and the C1/C2 contradiction paragraphs reading the probe log line by line (spec:101-107, 441-443).
7. The canonicaliser registered for every arm with the rescued-step share reported beside every ALFWorld contrast
   (spec:293-297, R9).
8. Scorer v2 as four recorded blocks with the invariant v2 >= official and `v2 = official` written explicitly for
   SpreadsheetBench and ALFWorld (spec:469-480).
9. The registered structural-limit statements (generator retirement cannot fire on one-step benches, spec:725-728; small
   pools only certify ~10-12 point effects, spec:377-379) -- unflattering and correct.
10. The consumption registry written before dispatch, append-only, never reset (spec:403-411), and the 600 s read timeout
   justified by the v3 smoke stall (spec:444-446).

## C. 给负责人的白话摘要（中文）

**结论：需要修改（needs_revision）。没有"致命"问题，但有 18 个"重要"问题和 9 个小问题。** 这份设计稿（"保真"版本）
最忠实于您认可的设计稿，也最多地复用了第 3 版（v3）审查过的代码；但从"故意找茬、想把运行弄坏"的角度看，下面几类问题
必须在建设前改掉。下面的"过程"指包里被学习的小程序；"沙箱"指只允许它们在里面运行的断网 docker 容器；"工作进程"指
沙箱里长时间运行、负责执行这些小程序的那个程序；"暂停"指整条链停下来等您决定。

1. **一行粗心的代码就能让整条链暂停。** 设计稿把"沙箱工作进程死掉或输出乱码"一律当成基础设施故障、直接暂停，而不是
   当成这条过程自己的故障。可是：过程里写一句调试用的 `print`（设计稿没有禁止）就会把通信通道弄乱；占内存太多会被系统
   杀掉；某些长时间的计算无法被时间限制打断而被强杀。恢复后同一条过程还会再次把它弄死。**修法**：通信改走专用通道；
   工作进程死掉时，算到"当时正在执行的那条过程"头上，按"过程故障"处理（该过程本题不启用，照常做题），再重开一个工作
   进程。冒烟测试要专门放这几种"坏代码"进去，确认都只记故障、不暂停。（F3）
2. **时间上限和实测矛盾。** 设计稿规定 ALFWorld（文字家务游戏）每局的工作进程最多活 900 秒，但 v3 实测一局的 90% 分位
   要 785–1,929 秒（实测，linux-ops.md:80-81）；问答题的工作进程只活 300 秒，而一次模型调用允许等 600 秒。**修法**：只限制
   每次执行的时长，不限制进程等模型的时间。（F4）
3. **"回放测试"和"检测器验收"都能被空过。** 回放测试的判断条件由工程师（写过程的 GLM 角色）自己写，写一句"永远返回
   通过"就过；ALFWorld 里 v3 所有失败都是走满 50 步（124/124，实测），所以考官写一个"走满 50 步就算失败"的检测器就能
   百分之百命中，"考官进化了"这个结论就成立了，但它什么新东西也没诊断出来。**修法**：回放测试改成登记好的、固定的检查
   （例如 ALFWorld 的"状态记录"要和手写参考记录器在 97% 以上的步数上一致）；检测器只在"现有固定检测器没覆盖的失败"上
   算查准率，并且看不到"走了多少步、是否被截断"这类等于答案的信息。（F6、F7）
4. **ALFWorld 的"出题程序"其实只是"挑已有的局"。** 一个"随便挑"的程序就能通过全部四道关，所以"考官一侧被验证"这一
   主要新意，在您被推荐的 ALFWorld 试点上可以被一个什么都不做的考官拿到。**修法**：加一个登记好的"随机挑选"对照，
   只有明显不同于随机挑选、而且方向判断正确的出题程序才算数；否则报告写"ALFWorld 上考官只是在挑题"。（F8）
5. **复制来的 v3 代码有两处会坏在"一道题调两次模型"的格子上**：重跑时只认最后一次调用，会导致暂停；表格题会在两次调用
   之间占住评分容器的名额，3 个名额可能全部互相卡死。**修法**：这两处明确改写，并各加一个单元测试。（F2、F9）
6. **表格题"先试跑一次再给提示"的试跑环境和正式评分环境不一样**（进程数、文件数、临时空间、线程设置都不同），可能把
   本来能过的程序当成出错、反而让模型重写坏；而且试跑的是做题模型自己写的、不受限制的代码，却放在过程的工作进程里。
   **修法**：试跑用和正式评分一模一样的容器命令，单独一个容器。另外，这类"修复回合"的安慰剂把错误信息也拿掉了，于是
   "比安慰剂好"这一关会把固定外壳给的错误信息的功劳算到学到的提示头上；安慰剂应保留错误信息，只把提示换成无关文字。
   （F10、F11）
7. **照搬 v3 的"泄题检查"会把最有用的过程误杀。** v3 的检查会丢弃"和题目原文连续 8 个词相同"或"出现了答案数字"的规则；
   而"把表格里的数字抽出来给模型看"这类过程，输出本来就是该题自己的原文，必然命中。**修法**：只检查"该题公开内容里
   本来没有的东西"。（F12）
8. **LiveMath（数学选择题）有一个已知的捷径**：训练集 283 题里有 129 题含"还能证明更强结论"这个选项，而且它在这 129 题
   里全是正确答案（实测）；"见到就选它"估计能从 33% 提到约 76%。设计稿只禁止出题程序利用它，没禁止过程利用它。**修法**：
   在 LiveMath 验收时加一组"遮住题干只看选项"的对照，提升若主要来自这个选项就不收；所有 LiveMath 结果按"含/不含这个
   选项"分开报告。（F13）
9. **接口不执行 max_tokens（回复长度上限）时，一次失控的超长回复会让整个账本全局停机。** **修法**：若冒烟证实接口不执行
   上限，就在我们这边边收边数、到上限就断开（算作截断、判错），而不是靠全局停机兜底。（F14）
10. **冒烟测试查不出新路径上的格式问题**：格式检查只测"只有任务卡"那一组，没测"精确计算/修复回合"的第二次回复是否还带
    答案标签，也没测各种故障路径和"暂停后恢复"。**修法**：格式检查同时测带过程的组，并与只有任务卡的组比差距；加入故障
    与恢复演练。（F15）
11. 其余重要问题：故障上限（2%）可以被"在启用判断阶段就出错"绕过（F16）；回放检查的代码写着"在主机上运行"，必须改为
    沙箱内运行（F17）；格式护栏只管系统提示里那句话，过程输出的笔记仍可能夹带"只写数字""保留两位小数"这类格式指令，
    而且对后面才轮到的 bench 完全没有检查（F18）。小问题（F19–F27）是文件路径、版本锁定、记录字段等细节。

**值得保留的好想法**：只在"新过程会启用的题"上做验收比较、发请求前就核对各组请求是否一字不差；安慰剂和"随机撤除"对照
都在发请求前抽好；过程出错时"当没启用、照常做题"的原则；不只靠"结束原因"判断截断；所有组都用同一个 ALFWorld 动作
规范化；事先写明"一步的 bench 无法淘汰出题程序""小题池只能认出约 10–12 分以上的效果"这些不好听但真实的限制。
