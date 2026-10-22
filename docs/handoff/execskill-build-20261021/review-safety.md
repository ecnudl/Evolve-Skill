# Review: sandbox, ledger and concurrency (route B, `fivebench-execskill-v1`)

- Lens: sandbox, ledger and concurrency (adversarial code review). Date: 2026-10-22.
- Tree reviewed: `dl:/data/execskill-dev` through the sshfs mount (`HEAD 010d453` plus the untracked route-B files).
  Frozen references: `skillopt/coevo5/*` and `skillopt/continual_eval/*` in the local repository.
- REG = `docs/handoff/execskill-registration-v1-20261021.md` (cited by line); PLAN =
  `docs/handoff/execskill-implementation-plan-v1-20261021.md` (cited by line). Paths without a prefix are under
  `skillopt/execskill/`.
- Read-only: no code was edited, no model was called, no test pool was read, and the reviewer started no container.
  Sandbox weaknesses are described as classes with fixes only; this file deliberately contains no reproduction steps.

## Verdict

- BLOCKER: none found.
- MAJOR: 6 (findings 1-6).
- MINOR: 11 (findings 7-17).

Targeted tests on dl (`PYTHONDONTWRITEBYTECODE=1 .../env/bin/python -B -m pytest -q -p no:cacheprovider
tests/test_execskill_{sandbox,slots,budgets,solver,integration_b2,outcomes_ext,cells,client,router}.py`):
**181 passed in 13.48 s**. None of these tests covers findings 1-6: halt scope across chains, manifest/endpoint B
consistency, the unit drain, worker-parent isolation, infrastructure-versus-procedure attribution under load, and
the missing runtime wiring are all untested.

## Short answers to the lens questions

| Question | Answer |
|---|---|
| Can model code escape the container? | No route found. The container flags (sandbox/client.py:97-114) are: no network, read-only root, uid 65534, all capabilities dropped, no-new-privileges, pids/memory/CPU caps, private IPC, noexec /tmp, and an environment reduced to the registered keys. The B2 real-container escape probe found no secrets. |
| Corrupt the frame protocol? | Not through the normal output path: fds 0/1/2 are on /dev/null, results go through a private pipe, frames have a size cap, and seq, echo and value hash are checked. Inside the container, however, the worker parent is not isolated from its same-uid children, so code that gets past the hygiene layer can interfere (finding 4). |
| Persist state? | Not across cells or episodes: each has its own container, which is removed and confirmed. Within a cell or episode, only past the hygiene layer (findings 4, 8, 17). REG states the guarantee without that condition. |
| Read files? | Yes, inside the container (finding 8). The B2 probe found nothing sensitive there. |
| Hang a cell? | No unbounded host wait found. Every frame read and write, ping, load and cleanup has a deadline. A call is bounded by its wall limit + 10 s grace and by RLIMIT_CPU, and a faulting procedure is dropped for the rest of the cell. A procedure that stays just under its limits can still stretch an ALFWorld episode (steps x hooks x 5 s). That costs throughput only. |
| Faults mapped to P1/P2/P3, never to infrastructure? | Procedure faults do reach P1/P2/P3. The mapping also leaks in both directions. Host-side errors inside the solver's catch-alls become infrastructure unknowns (finding 10; no trigger found). Infrastructure events become P1/P2/P3/P4 (finding 5, MAJOR). |
| B reserved while M is sent? | Yes (see Confirmed). But the B a run reserves with is not pinned to the verified manifest (finding 2). |
| Can a leak or an over-B reply halt, and is it documented? | Yes, it halts. The halt is documented as "global" and the risk is accepted (REG 353, 417, 1007-1008; C11; FA-F14; EA-E7). Not documented: with one ledger, the halt stops **both** chains (finding 1). The leak detector also inspects only two fields (finding 14). |
| Lock order, slot waits, native slot, cleanup | Lock order is consistent on the paths read. Episode, live and native waits are untimed and never P4. The native slot is never held across a model call, but `assert_order` enforces this only if the model pools come from `slots.pools` (finding 6a). Cleanup is confirmed per container, but the unit drain is unwired and fragile (finding 3), and the per-call pool can raise a spurious P4 (finding 12). |
| Empty package equivalent to the frozen solver? | On the registered projections, yes (T-SOLVER-1 passes). Operationally, no: arm C gains containers and stop paths the frozen solver does not have (finding 9). |

## Findings

### 1. MAJOR - One ledger serves both chains, so an over-B or leaked reply in either chain halts both; this cross-chain reach is not stated

- **Where:**
  - budgets.py:4 and :85-104: one ledger per run root (`<root>/shared/ledger`); `caps()` declares both chains and a single `overall` in it.
  - chain.py:247: `setting.budget.declare(budgets.caps())`.
  - PLAN 308.
  - frozen coevo5/budget.py:276-281 and :294-297: no attempt begins while the ledger is halted, and every reservation of an attempt whose halt generation predates any halt is refused.
  - frozen coevo5/calls.py:5-9, :184, :213.
- **Why:**
  - REG documents that a completion above B halts the ledger "globally" and accepts that risk (REG 353, 417, 1007-1008; C11; FA-F14; EA-E7). It also says that on ALFWorld branch E (B = 2,048) a typical reasoning leak triggers the halt.
  - The same document says each chain has its own ledger scopes and caps and pauses on its own (REG 39, 843-844), and that the chains decide, read the test set and seal independently (REG 915-916).
  - It never says that a halt caused by chain D's solver also stops chain G (its running units, its GLM role calls, and a test read in progress), or the reverse.
  - With one ledger, it does. The halt counter is global, so every open attempt of both chains is refused at its next reservation. Recovery then needs an owner decision in every interrupted unit of both chains.
  - A frozen-ledger quarantine (an unreadable ledger, a failed settlement) reaches equally far.
  - No test pins the halt scope: T-LEDGER-1..3 (PLAN 378) cover only the breach itself.
- **Fix:** Either option works:
  - give each chain its own ledger root (`<root>/<chain>/ledger`, each with its own `overall`); or
  - state in REG §4.1, §9.3 and §14, and in the owner-facing text, that a halt from either chain stops both, and give the recovery steps for the chain that did not cause it.

  In both cases, add a test that a breach under `D:` scopes refuses a `G:` attempt (one ledger) or does not refuse it (separate roots).

### 2. MAJOR - The halting threshold B has two unreconciled sources, and the verified one is only checked as B >= M

- **Where:**
  - manifest.py:52-53: `SOLVER_FIELDS` records `branch` and `B` but not `longest`.
  - manifest.py:202-209: `solver_block` computes B from branch and longest.
  - manifest.py:219-225: `check_clients` compares every solver field with the registration except B. B is only checked to be >= M.
  - units.py:84-95: `solver_endpoint` recomputes B from `Setting.branch` / `Setting.longest` and ignores the manifest's B.
  - budgets.py:130: the endpoint checks only B >= M.
  - smoke.py:190 compares an entry's B with a caller-supplied map. No code compares the manifest's B with `protocol.ledger_bound`.
- **Why:**
  - B is both the reservation size and the breach threshold.
  - A manifest with B = M (or any B >= M) passes verification on branch E. On branch N, B cannot be re-derived at all because `longest` is not recorded.
  - The running endpoint takes B from Setting fields that an adapter not yet written (ticket A13-1) will fill. Nothing ensures that the B in the verified manifest is the B the run reserves with.
  - If the two diverge, one of two things happens. Either the manifest misstates the halting threshold, or, if the adapter later reads B from the manifest, a B below the registered value makes ordinary over-M replies halt both chains (finding 1).
- **Fix:**
  - Record `longest` and the S1-b result's sha256 in the solver block.
  - In `check_clients`, require `B[bench] == protocol.ledger_bound(model, bench, branch=..., longest=...)` for every bench.
  - Have `solver_endpoint` take B from the verified manifest and assert that it equals the recomputation.
  - Add refusal tests: B = M on branch E, and a branch-N block without `longest`.

### 3. MAJOR - Container cleanup is unreliable: the unit drain has no call site, would misfire with two chains, misses route B's own pre-check containers, and treats a single slow removal as a stop

- **Where:**
  - sandbox/client.py:19-21: the drain is meant to run "once, after every worker of a unit has exited".
  - sandbox/client.py:53-54 and :366: names are `execskill-sbx-` + uuid, with no chain, unit or attempt tag.
  - sandbox/client.py:161-168: `cleanup` runs one `rm --force` and one exact-name `ps`, each bounded by 10 s, with no retry.
  - sandbox/client.py:171-176: `drain_check`. Its only callers are tests (test_execskill_sandbox.py:403-413, test_execskill_integration_b2.py:216-429) and mutation 18.
  - precheck.py:72: pre-check containers are named `continual-eval-` + uuid.
  - precheck.py:93-101: one 10 s rm, then CleanupUnconfirmed.
  - prelaunch.py:110-115: the S2 `leftovers` row lists only the `execskill-sbx-` prefix.
  - REG 219-221; ticket A5-2 (open).
- **Why:**
  - (a) REG §2.6 registers a prefix-wide "none left" check after each unit drains. No production code calls it.
  - (b) Once wired, a prefix-wide check made while the other chain (or another unit) has live containers raises CleanupUnconfirmed spuriously, because names carry no chain or unit tag. This is A5-2, an open owner/registrar decision.
  - (c) Route B's pre-check containers use the frozen `continual-eval-` prefix. The S2 `leftovers` row does not list that prefix, and frozen pipelines on the same machine also use it. Leftover pre-check containers are therefore neither detected nor attributable.
  - (d) A single 10 s bound with no retry turns a transient host stall into a unit stop. v3 already stopped on `container_cleanup_unconfirmed` after a ~36 s host stall (2026-10-05).
  - Route B multiplies container lifecycles, and each one is exposed to (d):
    - one per cell with procedures;
    - one per ALFWorld episode on every arm, including C (solver.py:688-689, cells.py:124-130);
    - one pre-check per SpreadsheetBench cell, including C (solver.py:625);
    - one per item and side in `router.plan` (router.py:160);
    - one per replay group (replay.py:418), detector pass (detectors.py:372) and engineer C5 check (engineer.py:436).
- **Fix:**
  - Tag every route-B container, both sandbox and pre-check, with chain, unit and attempt (as a name component or a `--label`).
  - Drain by tag once a unit's workers have exited, wire that drain into the unit runner, and test it.
  - Make the S2 `leftovers` row list pre-check containers by their tag.
  - Before raising CleanupUnconfirmed, retry `rm --force` and the exact-name check within a bounded window (e.g. 60-120 s), and record the latency.
  - Measure rm latency under the registered concurrency in S0.

### 4. MAJOR - Call children are not isolated from the worker parent, so the frame-stream and no-hidden-state guarantees hold only while the hygiene layer holds

- **Where:**
  - sandbox/worker.py:422-443: one fork per call; on timeout or over-cap, only the direct child is killed.
  - sandbox/worker.py:632-643: in `main`, the frame channel is a private descriptor of the worker parent. The parent does not harden itself against same-uid processes and keeps Python's default interrupt handling.
  - sandbox/client.py:97-114: the worker and its children share one uid, and the worker is the container's first process.
  - sandbox/client.py:419-420: a refusal reply becomes ConfigurationError.
  - policy.py:4: the policy is "NOT the security boundary".
  - REG 222-224 ("hidden state cannot persist across requests"); MA-M4 (REG 1144).
- **Why:**
  - The container bounds the damage to the container itself, and this review found no route out (see the table above).
  - Inside the container, the per-call child has the same identity as the worker parent and is not separated from it. Code that gets past the static hygiene layer, which by its own docstring is not the boundary, can interfere with the worker parent and its frame stream, or leave processes behind.
  - Consequences:
    - (i) A seq/echo mismatch is charged as P1 `worker` to whichever procedure is in flight, possibly an innocent one, and that procedure is dropped.
    - (ii) A forged refusal surfaces as ConfigurationError, which stops the unit instead of recording a procedure fault.
    - (iii) State can be carried across calls outside the declared `state` channel.
  - REG states these guarantees without this condition.
- **Fix:**
  - In the worker parent, before serving, mark the process non-dumpable and ignore interrupt signals.
  - Start each child in its own session/process group, kill and reap the whole group after every call, and check that only the worker parent remains. If anything else remains, discard the container and charge only the procedure that ran.
  - Map a refusal on a `call` op to `_Lost` (P1), and keep ConfigurationError for refusals of ping and load.
  - Add registrar-written S0 escape-probe rows for interference with the worker parent and for leftover processes.
  - State the guarantee's conditions in REG §2.6.

### 5. MAJOR - Infrastructure events and load are charged as procedure faults (P1/P2/P3) or pause units (P4), and they count toward the 2% gates

- **Where:**
  - sandbox/client.py:14-18 and :311-322: any `_Lost` (end of file, corrupt frame, a reply later than timeout + 10 s) becomes fault `worker`, and the procedure is dropped.
  - sandbox/client.py:58 (10 s grace) and :86 (0.5 CPU per cell container).
  - sandbox/client.py:379-385: a start that misses the 20 s ready ping raises SandboxUnavailable, with no retry.
  - worker.py:446-452: wall-timeout and signal faults.
  - protocol.py:429-430: predicate 2 s, hook 5 s, detector 5 s, ready 20 s.
  - router.py:73-96: any predicate failure becomes P2.
  - outcomes_ext.py:11-12 and :57-60: P3 becomes `unknown_fault`, which is scored wrong for the candidate.
  - REG 173, 465, 560-562 and 1324: P1/P2/P3 count toward the 2% J3 cap and the 2% self-test gate, and are "not infrastructure faults".
- **Why:**
  - Several infrastructure events look identical to a crashing procedure, and the client charges the procedure for them: a docker daemon hiccup, the kernel OOM killer acting on the container, a dead docker CLI process, or a host stall longer than the grace period.
  - Load-dependent timeouts are plausible. Wall limits are 2-5 s in 0.5-CPU containers, on a 7-core machine shared by two chains, up to three native SpreadsheetBench containers and six ALFWorld environments.
  - A timeout in one execution but not in its re-execution changes the request, which becomes P3 against the candidate.
  - These events fall only on arms that run procedures, so infrastructure noise becomes an arm difference. With a 2% threshold, a handful of them can reject a step (J3) or block a self-test.
  - The 2.62 s ready time in the B2 note was measured on an idle machine, not under the registered concurrency.
- **Fix:**
  - On `_Lost`, query the container with a bounded `docker inspect` (exit code, OOM-killed flag, daemon reachable). Classify docker-side deaths and host stalls as infrastructure unknowns that neither drop the procedure nor count toward J3.
  - In S0, measure hook and predicate CPU and wall time under the registered concurrency, and derive the limits from CPU time with a wall-time multiple.
  - Allow one bounded start retry before P4.
  - Report P1/P2/P3 by kind and arm in S2, so load effects are visible.

### 6. MAJOR (unverifiable) - The runtime wiring that several safety properties depend on does not exist yet

- **Where:**
  - chain.py:15 and :232-234: `learn` is `step.run_step`, but `step.py` and `examiner.py` are absent (B5 note line 16; tickets A12-2, B4 open item 1).
  - scripts/run_execskill.py:148-166: run and terminate are refused (A13-1).
  - units.py:49-75 and :107-119.
  - budgets.py:131-137: `setting.slots[client.model]`.
  - sandbox/client.py:347-348 and :371-372: `per_call=None` / `live=None` silently disable the per-call and live caps.
  - manifest.py:276-278: `limits_of` is called only by a test.
  - chain.py:78-92 and :187: the memory-heavy lock is taken only around test-read children.
  - rounds.py:85: one worker count for every bench.
- **Why:** The following registered properties depend on code that is not written, so they cannot be verified:
  - (a) The model pools must be `OrderedSlots` from `slots.pools` sharing one `Holdings`. This is what makes `assert_order` refuse a model call under the native slot, so the "native never across a model call" guarantee is only as strong as this wiring.
  - (b) Every worker factory (`router.plan`, donors, replay, detectors, engineer C5, generators) must pass the live and per-call pools. Otherwise those containers bypass the machine-wide caps.
  - (c) The manifest's registered limits must reach `Worker`.
  - (d) Learning units must take the memory-heavy lock, so SpreadsheetBench never runs beside SpreadsheetBench or ALFWorld (REG 229).
  - (e) The unit drain (finding 3).
  - (f) B taken from the manifest (finding 2).
  - (g) C3: ALFWorld units run with 6 workers (PLAN 312).
- **Fix:** Write the adapter and the step with these as asserted invariants:
  - `Setting` refuses a slots dict not built by `slots.pools`.
  - `Worker` refuses `live=None` / `per_call=None` unless an explicit test flag is set.
  - Every unit takes `heavy(setting, bench)`.
  - Add an integration test that inspects one built `Setting` and one worker factory of each kind.

### 7. MINOR - `exc_type` passes unsanitised into training records and sealed test-read records

- **Where:**
  - worker.py:304-305: only `message` is truncated.
  - sandbox/client.py:239-240 and :423-441: `exc_type` is not checked.
  - solver.py:254-258.
  - evaluation.py:205: `sealed_cell` keeps `faults[].exc_type`.
  - policy.py:81-84 and :100: class statements are banned, but the builtin `type` is not, so classes can still be created dynamically.
- **Why:** Procedure code chooses the exception type name, and it can be any text up to the 1 MiB frame cap, including item text. `sealed_cell` drops messages to keep sealed records free of item content, but it keeps `exc_type`.
- **Fix:** Accept only an identifier, in the worker and again in `_result`, using the frozen `EXCEPTION_NAME` (`[A-Za-z_][A-Za-z0-9_]{0,63}`, coevo5/calls.py:36 and :258). Record `other` for anything else.

### 8. MINOR - The policy overstates its file-access ban, and /tmp persists for a whole cell or episode

- **Where:**
  - policy.py:13-17: the docstring.
  - policy.py:93-98: `FORBIDDEN_ATTRIBUTES`.
  - sandbox/client.py:112: one tmpfs /tmp per container.
  - worker.py:370-373: RLIMIT_FSIZE 0.
- **Why:**
  - The attribute denylist does not cover every file-opening method reachable on objects of the allowed libraries, so procedure code can read files inside the container. The B2 probe found nothing sensitive there, so the impact is the false claim.
  - /tmp lives as long as the container. RLIMIT_FSIZE 0 stops file data but not file-system metadata, so "no hidden state across requests" again depends on the hygiene layer.
- **Fix:**
  - Correct the docstring: the real file-access controls are the read-only root, the absence of secrets and uid 65534.
  - Have the worker parent check that /tmp is empty after every call, and treat anything left as a fault of the procedure that ran.
  - Add an S0 row for this check.

### 9. MINOR - Empty-package equivalence holds on the projections only; arm C gains containers and stop paths that the frozen solver lacks

- **Where:**
  - solver.py:618-626: a pre-check container for every SpreadsheetBench cell, arm C included (REG §2.5, A9-1).
  - precheck.py:100-101: CleanupUnconfirmed is raised unconditionally. The frozen `_native` instead reports `cleanup_confirmed: false` and stops only under `_stop_on_cleanup_failure` (solver.py:645-648).
  - cells.py:124-130 and solver.py:688-689: every ALFWorld arm, C included, starts and pings a container, which exposes it to P4 and to cleanup stops.
  - solver.py:701-703: a mismatched live reset-view hash raises ConfigurationError.
  - solver.py:402-406: chain D's margin truncation rule.
- **Why:** T-SOLVER-1 (tests/test_execskill_solver.py:100) compares projections using working fakes. It does not exercise these failure paths, which the frozen solver does not have, so arm C is not operationally identical to the frozen baseline.
- **Fix:** Add T-SOLVER-1 variants for arm C with failing docker fakes (start failure, unconfirmed cleanup), and state in REG which outcome classes arm C can now take.

### 10. MINOR - Host-side errors inside the solver's catch-alls become infrastructure unknowns

- **Where:**
  - solver.py:577-580 and :651-654: `OSError, ValueError, KeyError, BadZipFile` become `public_input_or_runtime_error:<Type>`.
  - solver.py:758-759: any non-stop exception in an ALFWorld episode becomes `alfworld_environment_error:<Type>`.
  - `require` raises ValueError (continual_eval/core); one example is solver.py:116.
- **Why:** A host bug triggered by procedure output would be counted as an infrastructure unknown instead of P1 or a configuration stop. Examples are a `require` during note rendering or in `sham_discouraged`. No trigger was found: notes.screen is type-robust, and donors store an integer discouragement count (donors.py:191, placebo.py:181). Hence MINOR.
- **Fix:** Wrap hook-output processing (`shaped`, `render`, `assemble`, `before_step`, `after_step`) in its own handler that charges the procedure (P1 `host_processing`), and let wiring errors surface as ConfigurationError.

### 11. MINOR - A host-built request over the frame cap is charged to the procedure

- **Where:**
  - sandbox/client.py:305-307: a request over the cap becomes an `over_cap` fault, which is P1 in hooks and P2 in predicates.
  - sandbox/client.py:86-88: the cap is 1 MiB, and RLIMIT_AS is 2 GiB, above the 768 MiB container limit.
  - Ticket A5-1: neither value is registered yet.
  - manifest.py:51: `view_bytes_p99` is measured but not tied to the cap.
- **Why:** The arguments are views built by the host. An item whose view exceeds the cap faults every procedure on it, on every arm that runs them, regardless of procedure quality, and those faults count toward J3.
- **Fix:** Register the cap from S0 `view_bytes_p99` with a margin. Record a host-built request over the cap as an item-level infrastructure condition (procedure skipped, counted separately) instead of a procedure fault.

### 12. MINOR - The per-call pool can produce a spurious P4

- **Where:**
  - slots.py:7 and :19: the pool is described as one whose holds "last seconds".
  - slots.py:99-103, :111-118 and :151-158: random polling, with no FIFO order.
  - protocol.py:429 (generator calls 60 s) with sandbox/client.py:58 (+10 s grace).
  - One 4-slot pool serves both chains.
- **Why:** Generator holds of up to 70 s contradict "holds last seconds". With random polling, a waiter can lose every race for 2 x 600 s and raise SandboxUnavailable, pausing a unit because of a queueing effect.
- **Fix:** Use FIFO tickets for this pool, or a separate pool for generator and detector calls. Register the pool size from S0 wait percentiles measured under the registered concurrency.

### 13. MINOR - A live slot leaks if starting the container raises anything other than OSError

- **Where:**
  - sandbox/client.py:370-378: the slot is entered at :371-372, only OSError is caught around `spawn`, and the stack is attached to `_container` only afterwards.
  - sandbox/client.py:335-345: `close` releases the slot only through `_container`.
- **Why:** Any other exception from `Popen` leaves the slot and its lock file held until the process exits. That shrinks the machine-wide live pool of 6 for every route-B process.
- **Fix:** Guard everything from `enter_context` to the end of `_ensure`, and close the stack on any exception when no container was attached.

### 14. MINOR - The reasoning-leak detector inspects only two fields

- **Where:**
  - client.py:150-158: only `completion_tokens_details.reasoning_tokens` and `message.reasoning_content` are checked.
  - smoke.py:131: `_leak` looks only at the subtype.
- **Why:** A leak in another shape is scored as a clean reply, for example another reasoning field or inline thinking tags in the content. S2's zero-leak criterion is then met vacuously. S1-e is a positive control only for the shape it elicits.
- **Fix:** Also flag a non-empty `message.reasoning` and leading thinking tags in the content. In S1, record the usage and message keys the gateway actually returns.

### 15. MINOR - Two concurrent chains are outside the memory budget, C3 is not encoded, and live slots are held across model calls

- **Where:**
  - REG 227-230 and 1601-1604: T8 budgets one unit at a time.
  - chain.py:18-20: QA units take no memory lock.
  - sandbox/client.py:86-88.
  - rounds.py:85 and units.py:72: 16 workers for every bench.
  - PLAN 312 and REG 1598: C3 says ALFWorld units run with 6 workers.
  - units.py:110-113 and sandbox/client.py:360-373: containers start lazily and hold their slot until close (B2 open item 6).
- **Why:**
  - With two chains, a QA unit beside a SpreadsheetBench unit reaches 6 x 768 MiB live + 3 x 4 GiB native = 16.5 GiB of container limits on a 15 GiB machine. Host OOM kills would then surface as P1 faults (finding 5).
  - C3 is harmless for P4 because episode waits are untimed (slots.py:93-97). However, T8's premise of 3,600 s episode-wait timeouts no longer matches the code.
  - Holding the machine-wide live pool across model calls (chain G's read timeout is 2,400 s) lets one chain starve the other's episodes. This costs throughput only and never causes P4.
- **Fix:**
  - Add the two-chain combinations to T8. Alternatively, have QA units share the memory lock while SpreadsheetBench runs, or drop native slots to 2 when both chains are active.
  - Either encode C3 or delete it together with its T8 line.
  - Consider giving each chain its own share of the live pool.

### 16. MINOR - The host frame loop uses `select.select`

- **Where:** sandbox/client.py:199 and :231.
- **Why:** `select` raises ValueError for descriptors >= 1024. `call()` catches only `_Lost`, so the error reaches the solver's catch-all and becomes `public_input_or_runtime_error:ValueError` (finding 10). This needs high descriptor numbers in a long-running 16-thread process, but it is cheap to remove.
- **Fix:** Use `selectors.DefaultSelector` or `select.poll`.

### 17. MINOR - A failed fork crashes the worker and is charged to the procedure in flight, and descendants outlive the call

- **Where:**
  - worker.py:426: `os.fork()` is unguarded.
  - worker.py:441-442: only the direct child is killed.
- **Why:**
  - When the container's process limit is exhausted, the fork error ends the worker. The host sees end of file, and the in-flight procedure gets P1 and is dropped, although it may not be the cause.
  - Descendants (possible only past the hygiene layer) keep consuming pids and CPU, causing timeouts that are charged to later procedures.
  - C6's two-seed determinism check and the detector's second pass catch part of this.
- **Fix:** Return a resource fault on fork failure without ending the worker. With finding 4's process-group fix, kill descendants after every call.

## Confirmed (no finding)

- **B is reserved and settled, M is sent.**
  - units.py:92-95 and budgets.py:130-137 build the frozen Endpoint with `max_tokens` = B, so the reservation is `ledger.reservation(size, B)` (frozen calls.py).
  - The frozen `send` calls `client.call(system, user)`, and `ElucidClient` sends its own `max_tokens` = M (client.py:134-140; manifest.py:286).
  - Replies with M < completion <= B are recorded as `over_nominal` and scored, never halted (client.py:156).
  - A reasoning reply is mapped to `thinking_mismatch` and goes through the frozen resend path (client.py:157-158).
- **The native slot is never held across a model call.**
  - It is held only around the pre-check (solver.py:439-440), each native case (solver.py:641-643) and SpreadsheetBench scoring (cells.py:275). None of these contains a model call.
  - The model level precedes native in `LOCK_ORDER` (slots.py:39), so `assert_order` (slots.py:51-56) would refuse a model call made under native. This depends on finding 6(a).
- **Slot waits.** Episode, live and native waits are untimed, log a line every 300 s, and never raise P4 (slots.py:93-97). Only the per-call pool is timed (slots.py:99-103).
- **Lock order on the paths read.**
  - The order is episode (cells.py:243), then live (sandbox/client.py:371-372), then per-call (:312, :347-348), then model, then native.
  - Plan, donor and replay workers are opened one at a time (router.py:160, replay.py:418), so live slots are never nested.
- **Stops are preserved.**
  - The solver's catch-alls re-raise `STOPS` first (solver.py:577-578, :651-652, :751-757).
  - ConfigurationError is a stop (frozen coevo5/cells.py:45-46).
  - Stops raised inside model calls are recovered from the call records (outcomes_ext `_all_stops`).
- **P3 is never an infrastructure unknown** (outcomes_ext.py:11-12, :57-60).
- **Concurrent cells do not cause spurious BudgetStops.** The frozen `Budget.reserve` waits while reservations are open in an exceeded scope instead of stopping (coevo5/budget.py:283-315).
- **Host frame handling is deadline-bound and capped.**
  - Writes and reads use deadlines (sandbox/client.py:189-236).
  - An over-cap length header is refused before its payload is collected (:215-217).
  - seq, echo and value hash are checked (:417-418, :424-441).
- **The host-side calculator is bounded.** It caps every operand and result (4,096 bits, exponent <= 12, 100 nodes, depth 20) and checks a 5 s cell watchdog at every node (compute.py:9-21, :121, :133-138, :195-196).
- **Container flags match the registration** (sandbox/client.py:97-114). B2's real-container rows (rlimits, oom_score_adj, /dev/null fds, memory fault) were not re-run in this review.
