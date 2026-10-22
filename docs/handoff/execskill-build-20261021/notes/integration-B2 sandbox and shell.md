# Integration B2 (sandbox and shell): rows A5-A7 wired together

Protocol `fivebench-execskill-v1`. Plan §3, §4, §7, §8 and §9 (the B2 rows and gate (i)); registration §2.3-§2.6,
§4.1, §4.4, §6.2, §6.4 and the S0 table (where plan and registration disagree, the registration wins). Build tree
`/data/execskill-dev` (mounted on the Mac at `/Users/dulin/remote/dl`), HEAD `010d453` plus the untracked route-B
files. Inputs: notes A5-A7, tickets A5-1, A5-2, A6-1, A6-2, A7-1, A7-2. Done 2026-10-22 01:20 CST. No model call, no
credential file opened, no test-pool data read, no git command that changes state, no `.pyc` written. One
real-container check on dl (docker 26.1.3, 7 CPUs, 15 GiB), also without any model call.

## Gate (i): PASS

- **T-SOLVER-1.** The empty package reproduces the frozen `backends.solve` on both registered projections (request
  bytes and hashes; the prediction without `shell`, registration §2.3) on all five benches:
  `tests/test_execskill_solver.py -k t_solver_1`, 5 passed (SearchQA, OfficeQA, LiveMath: 3 layouts x 6 reply kinds
  x 3 cards; SpreadsheetBench: v2 layout with fences extraction, historical layout, invalid preview; ALFWorld:
  `tag_exact` episodes under both trace versions, an episode cut by a truncated step, the unsupported layout). A6 runs
  them with `worker=None`. The new integration file repeats gate (i) with A5's real `sandbox.client.Worker` in the loop
  (below).
- **T-CANON-4.** `tests/test_execskill_canonical.py::test_canonicaliser_divergence_starts_at_the_first_non_exact_step`
  passes. It runs the frozen v3 loop (`backends._solve_alfworld`) twice on the same replies, once raw and once through
  `canonical.canonical` alone. The requests are identical up to and including the first `tag_level1` step and differ
  at every later step; at that step v3 executes "Action: go to fridge 1" ("Nothing happens.") and route B "go to
  fridge 1" ("You arrive at fridge 1."). The divergence is the canonicaliser's alone, which is why gate (i) compares
  ALFWorld only on `tag_exact` episodes.
- **Sandbox with FakeDocker.** `tests/test_execskill_sandbox.py` (T-SBX-1..13): 20 passed.
- **Real container (one check, below).** The pinned image starts through `sandbox.client` with the registered argv,
  answers ping, turns a crash, an endless loop and a 2 GiB allocation into procedure faults and is removed with its
  own name confirmed. The escape probe passes every check of the S0 escape-probe row. One registrar item: the env list
  that row calls "registered" must name the 8 keys the image and docker add (open item 3).
- One fix (solver.py, fix 1). No test was weakened: no assertion in A5-A7's test files was changed. No frozen file was
  edited.

## pytest (dl, Python 3.11.16, `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider`)

| File | Before integration | After |
|---|---|---|
| test_execskill_protocol.py (A1) | 17 | 17 |
| test_execskill_budgets.py (A1) | 8 | 8 |
| test_execskill_slots.py (A1) | 7 | 7 |
| test_execskill_client.py (A2) | 73 | 73 |
| test_execskill_package.py (A3) | 65 | 65 |
| test_execskill_policy.py (A3) | 118 | 118 |
| test_execskill_notes.py (A3) | 33 | 33 |
| test_execskill_compute.py (A3) | 60 | 60 |
| test_execskill_canonical.py (A3) | 21 | 21 |
| test_execskill_registry.py (A4) | 8 | 8 |
| test_execskill_supply.py (A4) | 10 | 10 |
| test_execskill_exclusion.py (A4) | 4 | 4 |
| test_execskill_integration_b1.py (B1 integrator) | 9 | 9 |
| test_execskill_sandbox.py (A5) | 20 | 20 |
| test_execskill_solver.py (A6) | 27 | 27 |
| test_execskill_router.py (A6) | 5 | 5 |
| test_execskill_judge.py (A7) | 98 | 98 |
| test_execskill_outcomes_ext.py (A7) | 23 | 23 |
| test_execskill_stats_ext.py (A7) | 16 | 16 |
| test_execskill_integration_b2.py (integrator, new) | - | 7 |
| **route B** | **622** | **629** |
| test_coevo5_core.py (frozen) | 71 | 71 |
| test_weak_solver_probe.py (frozen) | 19 | 19 |
| **total (0 failed)** | **712** | **719** |

- The gate command (all route-B files plus the two frozen files) passed 719 in 16.4-16.5 s in each run after the fix.
  Before the fix it passed 712: no existing test covered the defect of fix 1.
- B1's T-ID-1 scan globs `skillopt/execskill/**` and the route-B test files, so it now covers the B2 modules
  (`sandbox/client.py`, `sandbox/worker.py`, `solver.py`, `router.py`, `precheck.py`, `precheck_worker.py`,
  `judge.py`, `outcomes_ext.py`, `stats_ext.py`) and passes: no B2 file defines a stop class or imports one from
  anywhere but `coevo5.outcomes` or `execskill.errors`.
- `git status`: no tracked file is modified; no `__pycache__` or `.pyc` in the tree. No `execskill-sbx-` container
  is left on dl.

## What was checked across the rows

- Imports and names: every name one B2 row takes from another exists with the meaning the importer assumes. A6's
  shell drives A5's `Worker` (`start(package, kind=, inputs_dir=)`, `ping`, `call(proc_id, fn, args, timeout_s=)`,
  `close`) and `client.with_worker`. A7's `judge` and `outcomes_ext` read A6's shell keys (`deciding_receipt`,
  `calls[i].reason`, `fallback`, `worst_delivery`, `alfworld_steps[i].how`). A6's `FakeSandbox`
  (`tests/execskill_fakes_env.py`) has the real `Worker`'s interface; the integration file swaps the real one in.
- Signatures: `solver.solve(...)` as in ticket A6-2 item 1, with an unstarted `client.Worker(docker=, limits=, live=,
  per_call=, scratch=)`; `router.plan(candidate, parent, bench, views, workers, *, unit)` with `workers` =
  `client.with_worker`; `outcomes_ext.preflight`/`classify(..., deciding=outcomes_ext.deciding_receipt(prediction,
  receipts))`; `judge.judge(bench, public, private, prediction, receipts, *, runtime, score, verdict, deciding)`; the
  frozen `backends.score` and `outcomes.finalize` on the shell's prediction.
- Record keys: `deciding_receipt` indexes the logical receipts as the frozen Recorder keeps them (one per logical call
  that returned, resends only in `sends`, calls.py:261-279). Each `calls[i].reason` is the frozen `_response` reason.
  The sealed `shell`, `route`, `firing-plan` and pre-check records carry `version` and `evidence` (T-ID-2, checked with
  `protocol.verified`).
- Exception classes: B2's stops leave with their kind. `SandboxUnavailable` (image missing) leaves `solver.solve` as
  "sandbox"; `CleanupUnconfirmed` leaves `Worker.close` and `drain_check` as "cleanup". A
  `ConfigurationError("slot_lock_order")` or a `BudgetStop` raised inside the call function is recorded as
  `model_call_exception:<Class>` in `shell.calls[i].reason`, and `outcomes_ext.preflight` raises it with its kind.
- Sandbox policy: the worker checks a loaded source with `policy.check(source)` (bench=None), the call package
  validation makes, so a package valid on the host loads in the container.
- ALFWorld routing views: items built with `supply.routing_view` (the `supply.prereset` shape) pass the shell's view
  and hash checks against the live reset view (ticket A6-2 item 6).

## Fix (minimal; in the file it touches)

1. **`skillopt/execskill/solver.py` (A6's row): every ALFWorld shell carries `alfworld_steps`.** A6 set
   `shell.steps = []` in `_solve_alfworld` only after `shell.route_on(...)`, so an ALFWorld prediction that ended
   earlier carried a shell without the step log. One such ending reaches the judge: `invalid_prompt_layout`
   (backends.py:372) is not in the frozen CONFIGURATION set (outcomes.py:53-58), so the frozen table makes it a row-11
   unknown (`_unavailable`, outcomes.py:293-304), not a stop. `judge._alfworld_format` (judge.py:223-240) then raised a
   plain ValueError ("An ALFWorld shell logs every step's canonicalisation", reproduced on dl), so that cell could get
   no judge record. The other early endings (`invalid_code_extraction_version`, `invalid_public_contract`,
   `invalid_alfworld_trace_version`, `invalid_alfworld_step_budget`) are row-1 configuration stops that never reach
   the judge, but they now carry the list too. Change: `_Shell.__init__` sets `self.steps = [] if bench == "alfworld"
   else None` (solver.py:230), the late assignment in `_solve_alfworld` is removed, and the module docstring says that
   every ALFWorld prediction carries `alfworld_steps`, empty when the episode ended before its first step, and that
   `deciding_receipt` indexes the logical receipts the call function returned (solver.py:54-57). The judge is
   unchanged: ticket A7-1 item 4 (the judge raises when an ALFWorld shell lacks the list) is now met by the shell. For
   such a prediction the judge returns row 11 with format `{"steps": 0, "admissible_steps": 0, "violation": None}`.
   A6's and A7's tests are unchanged and green.
2. **New `tests/test_execskill_integration_b2.py` (7 tests, the integrator's file).** Offline and deterministic:
   FakeDocker runs the real `worker.py` in local subprocesses, FakeSolver answers through the real ElucidClient
   (`tests/execskill_fakes.py`), FakeAlfEnv and FakeNative stand for ALFWorld and the native containers.
   - `test_gate_i_empty_package_equals_the_frozen_solver_with_the_real_worker_on_five_benches`: SearchQA, OfficeQA and
     LiveMath (2 items x 2 runtimes each), SpreadsheetBench (2 items), ALFWorld (3 games x 2 trace runtimes, `tag_exact`
     replies). Both projections equal the frozen `backends.solve`. QA and SpreadsheetBench cells start no container;
     each ALFWorld episode starts exactly one (the card arm's ping, registration §6.2) and removes it (6 containers in
     all, `drain_check` passes). Every shell passes `verified(shell, "shell")`.
   - `test_outcomes_and_judge_read_the_records_of_the_real_shell`: P5, a `<calc>` first reply and a truncated second
     reply: `deciding_receipt` 0, `fallback` "second_call_fallback", call reasons `model_response_available` and
     `model_response_truncated`, `worst_delivery` "truncated" (never deciding), verdict pass row 10, judge v2 pass with
     the flag `second_call_fallback`. A `ConfigurationError("slot_lock_order")` and a `BudgetStop` raised by the
     second call: the prediction stays available, `calls[1].reason` is `model_call_exception:<Class>`, and
     `outcomes_ext.preflight` raises it with its kind. Chain D's margin rule (`nominal_tokens` = M, a reply of M-10
     visible tokens with an unclosed `<answer>`): reason `model_response_truncated`, row 5 noncompletion fail, judge
     flag `truncated`.
   - `test_every_alfworld_prediction_carries_the_step_log_the_judge_reads`: `invalid_prompt_layout` gives
     `alfworld_steps == []` and judge row 11 with the empty format above; an episode with a level-1 reply and a
     "dance" reply gives `how` = `whole_level1`, `unchanged`, `tag_exact`, ...; the judge's v2 token is pass and its J4
     violation is True (admissible share below 9/10).
   - `test_procedures_run_in_the_real_worker_behind_the_shell`: SpreadsheetBench `sheet_feedback` reads the public
     workbook through the read-only `/input` mount (`public_workbook()`: 5 filled cells) and its note reaches the
     repair request; the pre-check report is a sealed record. ALFWorld `alf_before_step` notes reach every step with
     the state kept by the host (`alf_after_step`; one state hash per step). A predicate returning a non-bool (P2
     `not_bool`) and a hook raising ZeroDivisionError (P1) drop their procedure; the frozen request is unchanged and
     the route record verifies.
   - `test_the_worker_shell_and_model_slots_keep_the_registered_lock_order`: three SpreadsheetBench cells in threads
     with A1's pools (`execskill-sandbox-live` limited to 2, the SpreadsheetBench unit cap; the per-call sandbox pool;
     the native pool): each of the 6 model calls holds exactly `(execskill-sandbox-live,)` and takes a model slot
     without a lock-order refusal; each of the 3 pre-checks and 3 case runs holds `(execskill-sandbox-live,
     spreadsheet-native)`. An ALFWorld episode under the episode slot: its model calls hold `(alfworld-episode,
     execskill-sandbox-live)`, and the live slot goes with the container.
   - `test_router_plan_routes_the_candidate_and_its_parent_in_real_workers`: `router.plan` with `client.with_worker`
     on 4 OfficeQA items: the candidate's procedure fires on all 4, the empty parent on none, decision
     `not_run_small_astar` (4 < MIN_ASTAR); 4 containers (the candidate's), all removed; a second run gives the same
     plan; the plan verifies as `firing-plan`.
   - `test_t_id_1_b2_stops_reach_the_caller_with_their_kind`: a missing image gives `SandboxUnavailable` out of
     `solver.solve` with kind "sandbox"; a container that will not go gives `CleanupUnconfirmed` from `Worker.close`
     and from `drain_check`; after `client.cleanup` the drain passes.

## Break-the-code checks (a throwaway copy `/tmp/b2-mut` on dl, deleted afterwards)

Each mutation went into the copy, the integration file was run, and the copy was restored.

| Mutation | Result |
|---|---|
| none (baseline) | 7 passed |
| M1: ALFWorld shell without a step log before the loop (fix 1 reverted) | 1 failed |
| M2: `outcomes_ext` ignores the shell's call reasons | 1 failed |
| M3: native slot held across the repair call | 1 failed |
| M4: public workbook not mounted in the sandbox | 2 failed |
| M5: ALFWorld card arm not pinged | 1 failed |
| restored | 7 passed |

## Real-container check on dl (one run, no model call)

Scripts outside the tree, in `/tmp/b2-integ` on dl (volatile): `real_container.py` (sha256 `6327e19a…4df4700`)
drives `skillopt.execskill.sandbox.client` against the real docker CLI; `escape_probe.py` (sha256
`fd769fba6e2a8a9d8bfee7cb024d66c6dbf66454da937c8517ca5657e08090c5`, appendix A) is the probe;
`real_container.out.json` holds the output. Exit 0, empty stderr.

1. Image: the tag `evolve-skill-native:smoke-20260928` resolves to the registered ID
   `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd` (= `client.IMAGE`); image user
   `65534:65534`; image ENV keys GPG_KEY (a 40-hex release-key fingerprint), LANG, PATH, PYTHONDONTWRITEBYTECODE,
   PYTHON_SHA256 (a 64-hex source checksum), PYTHON_VERSION.
2. Registered argv (`client.argv_template("cell")`, digest
   `f826e69d648ef0885fd37bf596545239f6d1f5a6c0b0b256ef9f17360109c0d1`):
   `docker run -i --pull=never --name execskill-sbx-<uuid4> --network=none --read-only --user=65534:65534
   --cap-drop=ALL --security-opt=no-new-privileges=true --pids-limit=64 --memory=768m --memory-swap=768m --cpus=0.5
   --ipc=private --shm-size=16m --no-healthcheck --log-driver=none --ulimit=nofile=64:64 --ulimit=core=0:0
   --env PYTHONHASHSEED=<0|1> --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 --env MKL_NUM_THREADS=1
   --env EXECSKILL_SANDBOX=execskill-worker-v1 --mount type=bind,source=<runner>,target=/runner,readonly
   --mount type=bind,source=<input>,target=/input,readonly --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m
   --workdir=/tmp --entrypoint=python sha256:0a0a5dcb… -s -B -P /runner/worker.py`.
   Worker sha256 `5b0421e1683c84a3f0c03c73c1412152846c4c539736b2e7b99e3daec8b212b6`, policy sha256
   `d19cbe494f0c098f583af6c7a40a8ccd1f0a17f6c026885643ae4d8f5132fc7d`.
3. `client.Worker().start(package, kind="cell", inputs_dir=<a 5-row workbook>)` (two fixture procedures, lazy start):
   first ping 2.62 s after `start` (container boot and library imports). Ping: python 3.11.16, numpy 1.26.4, openpyxl
   3.1.5, pandas 2.2.3, sympy 1.13.3, worker `execskill-worker-v1`, hashseed "0", `worker_sha256` equal to the
   host's, VSZ 173,792 KiB, RSS 111,932 KiB.
4. Calls, each in a fresh forked child of the same container:

   | Call | Result |
   |---|---|
   | `applies` | ok, True; cpu 3 ms; child RSS 84,348 KiB |
   | `before_call` using `public_workbook()`, `safe_sympify` and `sympy.factor` | ok, facts ["filled cells: 5", "factored: (x - 1)**2"]; cpu 59 ms; RSS 87,908 KiB |
   | printing to stdout (`calendar.prmonth`) | ok; frames intact (the child's stdout is /dev/null) |
   | a 2 GiB `bytearray` | fault `memory` (MemoryError) |
   | an endless loop, timeout 2 s | fault `timeout`, wall 2.0 s |
   | `1 / 0` | fault `exception` (ZeroDivisionError) |
   | a calm call after the three faults | ok |

   One container served all seven calls (the worker restarted nothing: `dropped` [], `rejected` {}); after them the
   worker had VSZ 173,936 KiB and RSS 112,052 KiB. `close()` removed it and confirmed its own name (`docker ps -a`
   by exact name: empty).
5. Hash seeds: two workers with PYTHONHASHSEED 0 and 1 returned equal sorted output and different set iteration
   order (the seed reaches the worker; registration §2.6 engineer checks).
6. `client.drain_check()` passed after the workers and again after the probe.

## Escape probe (plan §4; registration S0 table, escape-probe row)

Started with the registered argv, identical except that `/runner/escape_probe.py` replaces `/runner/worker.py`
(`worker.py` and `policy.json` mounted beside it, read-only), as the container's pid 1; exit 0 in 1.9 s; the
container was removed with `client.cleanup`.

| Check | Measured | Result |
|---|---|---|
| no network | TCP to 1.1.1.1:53 and 8.8.8.8:443: ENETUNREACH; UDP: ENETUNREACH; DNS: gaierror; interfaces: `lo` only; a worker child's connect: `[Errno 101] Network is unreachable` | pass |
| `/` and `/runner` read-only | creating a file in `/`, `/etc`, `/usr`, `/runner`, `/input`: EROFS; mounts `/` overlay ro, `/runner` ro, `/input` ro; `/tmp` tmpfs `rw,nosuid,nodev,noexec,size=16384k`, mode 1777, writable; executing a file from `/tmp`: EACCES | pass |
| uid 65534 | uid and gid 65534, groups [65534]; all five capability sets 0, NoNewPrivs 1, Seccomp 2 (filter) | pass |
| only registered env keys | 13 keys: the 5 registered `--env` keys (PYTHONHASHSEED=0, OMP/OPENBLAS/MKL_NUM_THREADS=1, EXECSKILL_SANDBOX=execskill-worker-v1), the 6 image ENV keys above, and HOSTNAME and HOME (set by docker); nothing else, no credential | pass, list to register (open item 3) |
| no `*.env`, key, ledger or consent files | a name scan of the whole container file system (except /proc, /sys, /dev) for `*.env`, `*key*`, `consent*`, `ledger*`: 31 hits, all files of the image itself (Python stdlib and pandas/pytz/setuptools names containing "key" or "Turkey", 4 CA certificate files, Debian archive keyrings and their dpkg records, `pam_keyinit.so`); no `*.env`, `consent*` or `ledger*` name at all; nothing under `/runner`, `/input`, `/tmp` or `/home`; `/root` not listable (EACCES); `/data`, `/var/run/docker.sock`, `/run/docker.sock`, `/root/.config/weak-solver/elucid.env`, `/data/skillopt-work/.env` do not exist inside | pass |
| pids and memory limits | forking stops at 63 children with EAGAIN (`--pids-limit=64`, the probe included); a child that sets oom_score_adj 1000 and allocates 1 GiB is killed by SIGKILL (cgroup 768 MiB) while pid 1 survives | pass |
| the worker child (`worker.run_call` of the real worker.py, in the real container) | RLIMIT_CPU [6, 7] for a 5 s call; RLIMIT_AS 2 GiB; RLIMIT_FSIZE 0 (a file write fails with `[Errno 27] File too large`); RLIMIT_NOFILE 32; oom_score_adj reads 1000; fds 0/1/2 are /dev/null; a 2 GiB allocation is fault `memory` | pass |

Python flags: `-P` is accepted (`sys.flags.safe_path` True), `-B` gives `dont_write_bytecode` 1. The probe read
`sys.flags.no_site` (0), but `-s` sets `no_user_site`, not `no_site`: a slip of the probe, not a finding (the argv
carries `-s`). A13's version should read `no_user_site`.

## S0 values measured here (for the registrar; nothing was registered by the integrator)

- Worker container with numpy, openpyxl, pandas and sympy preloaded, idle after start: VSZ 173,792 KiB, RSS
  111,932 KiB; after seven calls including three faults: 173,936 / 112,052 KiB.
- Call child peak RSS (`wait4`): 84,348-84,744 KiB for trivial hooks, 87,908 KiB with sympy work.
- First ping 2.62 s after `start`; the escape probe ran 1.9 s.
- A5's "for S0" items: the tmpfs mode is 1777 (A5 deviation 8); `-P` is accepted; the `oom_score_adj` write works in
  the child; the image's own ENV keys are the 6 listed above.
- RLIMIT_AS (A5's placeholder 2,048 MiB) is above the container's 768 MiB. An allocation that fits under AS but not
  under the cgroup ends as an OOM kill of the child (the worker's fault `killed`, worker.py:449-452), not as
  MemoryError (fault `memory`). Both are P1 procedure faults. Registering AS below the container cap would make them
  `memory`; the registrar's choice at S0 (ticket A5-1).

## Frozen code relied on (read-only, mirror at 010d453)

- `continual_eval/backends.py:364-455` `solve` (`invalid_prompt_layout` at :372), `:715-783` `_solve_alfworld` (gate
  (i) and T-CANON-4 call them), `:517` `score`, `:153-214` `_native` (the sandbox argv copies its hardening: name at
  :158, argv :169-178, exact-name removal :190).
- `coevo5/outcomes.py:53-58` CONFIGURATION (no `invalid_prompt_layout`); `:71-72` NONCOMPLETION_REASONS (row 5);
  `:185-204` classify; `:207-228` preflight; `:293-304` `_unavailable` (row 11 for any other unknown reason).
- `coevo5/calls.py:125` `_request_hash` (the shell's `request_sha256`); `:261-279` Recorder: one receipt per logical
  call (`receipts.append` at :276), resends only in `sends`.
- `coevo5/protocol.py:346`: the pinned native image digest.
- `validator_pilot/api.py`: `digest`, `write_json`.

## Tickets

- **A7-1 (A7 -> A6): resolved.** A6 kept the names of items 1-4 and put item 5's margin rule into the shell
  (`nominal_tokens`, reason `model_response_truncated`, A6 deviation 10). Item 4 ("every ALFWorld shell has the
  list") was not met for predictions that end before the step loop; fix 1 closes it. The integration file checks
  items 1-5 on the real shell's records.
- **A6-2 (A6 -> A8, cc A4/A13): open for B3.** Item 6 is checked here (items built with `supply.routing_view` pass
  the shell's checks). Items 1-5, 7 and 8 are A8's wiring; the integration file uses them as the ticket states.
- **A6-1 (A6 -> A9): open for B3.** One discouragement draw rule (`placebo.sham_discourage` calls or is
  `solver.sham_discouraged`) and the placebo data shape.
- **A7-2 (A7 -> A8): open for B3.** `test_outcomes_and_judge_read_the_records_of_the_real_shell` makes the calls of
  items 2 and 4 on the real shell's records; items 1 (token), 3 (P3 replay) and 5 (item scores) are A8's.
- **A5-1 (A5 -> A1): open; registrar at S0.** The constants stay in `sandbox/client.py`; moving them into
  `protocol.py` would change no value. RLIMIT_AS and the frame cap still need registered values (measurements above).
- **A5-2 (A5 -> A12/A13, registrar): open; decision before chains G and D run concurrently.** Not changed here (the
  ticket's options 1-3).
- **A3-1 (from B1): open; owner, before S2.**

## Open (not closed in B2)

1. Ticket A5-2: the prefix-wide `drain_check` would raise a spurious `CleanupUnconfirmed` while a unit of the other
   chain has live containers. Until it is decided, call `drain_check` only where no other route-B unit runs.
2. Ticket A5-1: register RLIMIT_AS and the frame cap at S0 from the values above (and see the OOM note).
3. The S0 escape-probe row says "env keys only the registered ones". The container has 13: the 5 registered `--env`
   keys, the 6 the pinned image defines (GPG_KEY, LANG, PATH, PYTHONDONTWRITEBYTECODE, PYTHON_SHA256,
   PYTHON_VERSION) and HOSTNAME and HOME from docker. None is a credential (A5's note foresaw this). The registrar
   should register this 13-key list; A13's `sandbox-selftest` should then require equality with it.
4. A13 (S0): adopt the probe of appendix A as the fixed registrar code for `sandbox-selftest` (with `no_user_site`
   and the list of item 3). Still to run in the real container at S0: the sandbox row's NaN, oversized output,
   module-level loop, deep nested state, killed child, worker SIGKILL and banned-name cases (here only with
   FakeDocker), the p99-size workbook fixture, the two-seed/two-order determinism on fixture procedures, the real
   docker pre-check (A6 "not covered"), and T-JUDGE-1's archived-cell check (A7's note).
5. B3 wiring: tickets A6-1, A6-2 and A7-2 (above); the copied cell loop must look stops up in `errors.STOP_KINDS`
   (B1 open item 2).
6. Throughput (owner, A6/A8; not a mismatch): a QA or SpreadsheetBench cell's container, and with it an
   `execskill-sandbox-live` slot, lives for the whole cell, across its model calls, although no hook runs after the
   first request (QA) or after `sheet_feedback` (SpreadsheetBench). That is as registered (§2.6: one container per
   cell, the slot held as long as the container lives), but with 6 live slots machine-wide (2 per SpreadsheetBench
   unit), cells with procedures queue for slots while containers idle through model calls. Option: close the worker
   after the cell's last hook (still one container per cell). Not changed.
7. Cosmetic: `_solve_sheet` deletes its input directory before `solve` closes the worker, so the read-only bind source
   disappears a moment before the container is removed. Harmless; not changed.
8. Ticket A3-1 (B1): the lexicon rule, owner before S2.

## Notes for later batches

- Give `solver.solve` an unstarted `Worker` per cell or episode; the shell starts, pings (ALFWorld) and closes it.
- Pass the full `recorder.receipts` to `outcomes_ext.deciding_receipt`; the shell's `deciding_receipt` indexes that
  list.
- ALFWorld items must carry `routing_view` and `routing_view_sha256` exactly as `supply.prereset` returns them.
- The scripts in `/tmp/b2-integ` on dl will not survive a reboot; appendix A keeps the probe verbatim (its sha256
  above).

## Appendix A: the escape probe, verbatim (`/tmp/b2-integ/escape_probe.py` on dl)

```python
"""Escape probe of the route-B sandbox (implementation plan §4; registration S0 table, escape-probe row): fixed
registrar code, started with the registered container argv in place of /runner/worker.py. It prints one JSON report on
stdout and changes nothing outside the container."""
import errno
import fnmatch
import importlib.util
import json
import os
import socket
import sys
import time
import signal

PATTERNS = ("*.env", "*key*", "consent*", "ledger*")
SKIP = ("/proc", "/sys", "/dev")
CHILD = '''
import os
import resource
import socket


def write_file():
    fd = os.open("/tmp/probe-child-file", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.write(fd, b"x")
    finally:
        os.close(fd)
    return "written"


def oom_score_adj():
    with open("/proc/self/oom_score_adj") as handle:
        return handle.read().strip()


def limits():
    return {name: list(resource.getrlimit(getattr(resource, name)))
            for name in ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_NOFILE")}


def standard_streams():
    return [os.readlink("/proc/self/fd/%d" % fd) for fd in (0, 1, 2)]


def connect():
    sock = socket.socket()
    sock.settimeout(2)
    sock.connect(("1.1.1.1", 53))
    return "connected"


def allocate():
    return len(bytearray(2 << 30))
'''


def name_of(error):
    if isinstance(error, OSError) and error.errno:
        return errno.errorcode.get(error.errno, str(error.errno))
    return type(error).__name__


def tcp(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect((host, port))
        return "connected"
    except OSError as error:
        return name_of(error)
    finally:
        sock.close()


def udp(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"x", (host, port))
        return "sent"
    except OSError as error:
        return name_of(error)
    finally:
        sock.close()


def dns(host):
    try:
        socket.getaddrinfo(host, 443)
        return "resolved"
    except OSError as error:
        return type(error).__name__


def write(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        return name_of(error)
    try:
        os.write(fd, b"x")
    except OSError as error:
        return "created_then_" + name_of(error)
    finally:
        os.close(fd)
        os.unlink(path)
    return "writable"


def execute_from_tmp():
    path = "/tmp/probe-exec.sh"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
        os.write(fd, b"#!/bin/sh\nexit 0\n")
        os.close(fd)
    except OSError as error:
        return "not_created_" + name_of(error)
    pid = os.fork()
    if pid == 0:
        try:
            os.execv(path, [path])
        except OSError as error:
            os._exit(100 + (error.errno or 0) % 100)
        os._exit(99)
    _, status = os.waitpid(pid, 0)
    os.unlink(path)
    code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
    if code == 0:
        return "executed"
    return "refused_" + errno.errorcode.get(code - 100, str(code)) if code >= 100 else "status_%d" % code


def listable(path):
    try:
        os.listdir(path)
        return True
    except OSError as error:
        return name_of(error)


def status_fields():
    keep = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb", "NoNewPrivs", "Seccomp")
    fields = {}
    with open("/proc/self/status") as handle:
        for line in handle:
            key, _, value = line.partition(":")
            if key in keep:
                fields[key] = value.strip()
    return fields


def secret_names():
    hits = []
    for root, dirs, files in os.walk("/", onerror=lambda error: None):
        dirs[:] = [d for d in dirs if os.path.join(root, d) not in SKIP]
        for name in dirs + files:
            if any(fnmatch.fnmatch(name.lower(), pattern) for pattern in PATTERNS):
                hits.append(os.path.join(root, name))
    return sorted(hits)


def pids_limit(cap=200):
    children, stopped = [], None
    for _ in range(cap):
        try:
            pid = os.fork()
        except OSError as error:
            stopped = name_of(error)
            break
        if pid == 0:
            time.sleep(30)
            os._exit(0)
        children.append(pid)
    for pid in children:
        os.kill(pid, signal.SIGKILL)
    for pid in children:
        os.waitpid(pid, 0)
    return {"forked": len(children), "stopped_by": stopped}


def memory_limit(mib=1024):
    pid = os.fork()
    if pid == 0:
        try:
            with open("/proc/self/oom_score_adj", "w") as handle:
                handle.write("1000")
            block = b"x" * (mib << 20)
            os._exit(0 if block else 1)
        except MemoryError:
            os._exit(3)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        return "killed_by_signal_%d" % os.WTERMSIG(status)
    return "exited_%d" % os.WEXITSTATUS(status)


def worker_child():
    """The real worker's per-call child (worker.run_call) inside the real container."""
    spec = importlib.util.spec_from_file_location("sandbox_worker", "/runner/worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = compile(CHILD, "<escape probe>", "exec")
    limits = {"address_space_mb": 2048, "frame_bytes": 1 << 20}
    out = {}
    for fn in ("write_file", "oom_score_adj", "limits", "standard_streams", "connect", "allocate"):
        channel = os.open(os.devnull, os.O_WRONLY)
        try:
            out[fn] = module.run_call(code, fn, [], 5, limits, channel)
        finally:
            os.close(channel)
    return out


def main():
    report = {
        "identity": {"uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups(), "pid": os.getpid()},
        "python": {"version": sys.version.split()[0], "safe_path": sys.flags.safe_path, "no_site": sys.flags.no_site,
                   "dont_write_bytecode": sys.flags.dont_write_bytecode, "isolated": sys.flags.isolated},
        "env_keys": sorted(os.environ),
        "env": {key: os.environ.get(key) for key in ("PYTHONHASHSEED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                     "MKL_NUM_THREADS", "EXECSKILL_SANDBOX")},
        "network": {"tcp_1.1.1.1_53": tcp("1.1.1.1", 53), "tcp_8.8.8.8_443": tcp("8.8.8.8", 443),
                    "udp_1.1.1.1_53": udp("1.1.1.1", 53), "dns_example.com": dns("example.com"),
                    "interfaces": sorted(os.listdir("/sys/class/net"))},
        "writes": {where or "/": write(where + "/probe-write") for where in ("", "/runner", "/input", "/etc", "/usr",
                                                                             "/tmp")},
        "tmp": {"mode": oct(os.stat("/tmp").st_mode & 0o7777), "exec": execute_from_tmp()},
        "mounts": [line.split()[:4] for line in open("/proc/self/mounts")
                   if line.split()[1] in ("/", "/runner", "/input", "/tmp")],
        "status": status_fields(),
        "host_paths": {path: os.path.exists(path) for path in ("/data", "/var/run/docker.sock", "/run/docker.sock",
                                                               "/root/.config/weak-solver/elucid.env",
                                                               "/data/skillopt-work/.env")},
        "root_listable": listable("/root"),
        "secret_names": secret_names(),
        "pids": pids_limit(),
        "memory": memory_limit(),
        "worker_child": worker_child(),
    }
    sys.stdout.write(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
```
