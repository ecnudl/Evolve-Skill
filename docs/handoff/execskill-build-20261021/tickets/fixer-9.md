# Ticket fixer-9 → main agent / owner: sandbox lifecycle and fault attribution (safety findings 3, 4, 5)

From the fixer (2026-10-22). Safety review findings 3, 4, 5; tickets A5-2 (open) and A13-1. The fixer did not change
`sandbox/client.py` lifecycle code, `sandbox/worker.py` or `precheck.py` for these findings: there was not enough time,
and each needs an owner decision or an S0 measurement first. Changing `worker.py` also changes the manifest's
`worker_sha256`, which is fine before launch.

1. **Container cleanup (safety 3).**
   - Tag every route-B container, sandbox and pre-check, with chain, unit and attempt (`--label`). Pre-check
     containers still use the frozen `continual-eval-` prefix, which frozen pipelines share.
   - Drain by tag once a unit's workers have exited, and wire that drain into the unit runner. This depends on the
     A5-2 decision.
   - Make the S2 `leftovers` row list pre-check containers by their tag.
   - Retry `rm --force` and the exact-name check within a bounded window (60-120 s) before `CleanupUnconfirmed`,
     and record the latency. v3 stopped on a ~36 s host stall on 2026-10-05.
2. **Worker isolation (safety 4).**
   - In the worker parent: `prctl(PR_SET_DUMPABLE, 0)` and ignore SIGINT before serving.
   - Start each call child in its own session, and kill and reap its process group after every call. If any process
     other than the worker parent remains, discard the container and charge only the procedure that ran.
   - Map a refusal of a `call` op to `_Lost` (P1); keep `ConfigurationError` for refusals of ping and load.
   - Add S0 escape-probe rows, and state the conditions of the guarantee in REG §2.6.
3. **Infrastructure versus procedure faults (safety 5).**
   - On `_Lost`, run a bounded `docker inspect` (exit code, OOMKilled, daemon reachable). Classify docker-side deaths
     and host stalls as infrastructure unknowns, which do not drop the procedure and do not count toward J3 or the
     self-test gate.
   - Allow one bounded start retry before P4.
   - Measure hook and predicate CPU and wall time under the registered concurrency in S0.
   - Report P1/P2/P3 by kind and arm in S2.
