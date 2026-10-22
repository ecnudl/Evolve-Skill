# M round — builder W: Codex finding #6 (sandbox hidden filesystem state; reflection helpers)

Status: DONE. Zero model calls, no network, no git writes. Target met inside the window.

## The finding (confirmed before fixing)
`policy.py` allowed `operator.attrgetter`, so a CONSTRUCTED name (`"_"*2 + "globals" + "_"*2`) evaded the literal
dunder check: `attrgetter("__globals__")(safe_sympify)["os"]` reached the worker helper's `os` module. Verified on dl
with the pinned interpreter (zero model calls):
- the exploit source passed `policy.check` with **no** violations;
- `os in safe_sympify.__globals__` and `os in public_workbook.__globals__` are both True;
- `operator.methodcaller("__class__")` with a constructed string also passed.
`os.mkdir` is not stopped by `RLIMIT_FSIZE=0` (directory, no content), and the sandbox `/tmp` tmpfs is shared across a
container's forked call children, so a marker planted in one call was visible to the next — §2.6 says hidden state must
not survive a request.

## Fix (two layers; OS boundary is primary)
Files owned by W only. No cross-owner edits.

1. **OS boundary — `skillopt/execskill/sandbox/worker.py`** (primary):
   - Every call runs in a fresh private writable directory (`_new_call_dir` → `tempfile.mkdtemp`), set as the child's
     cwd and `TMPDIR`/`TMP`/`TEMP` in `_child`, and removed when the call ends (`_reset_writable` in `run_call`'s
     `finally`).
   - In the container (worker is PID 1, so `/tmp` is this container's own tmpfs) `_reset_writable` also sweeps every
     other entry a call created in the writable base, back to the entries present when the worker started serving
     (`_BASELINE`, captured on the first call after preload). This removes an absolute-path marker a hygiene-bypassing
     route plants in `/tmp`.
   - On a host (offline tests, not PID 1) only the private directory is removed — the shared `/tmp` is never swept.
   - Added stdlib imports `shutil`, `tempfile`; module docstring updated. `run_call`'s parent body is wrapped in
     `try/finally`; the child branch still ends in `os._exit`, which bypasses that `finally`, so only the parent sweeps.
   - The container argv (`sandbox/client.py docker_command`) and `precheck.py` were read: the argv is unchanged (no
     manifest impact); precheck is a one-shot-per-container path (one program, then `rm --force`), so cross-request
     persistence does not apply there — no change needed.

2. **Reflection ban (extra protection) — `skillopt/execskill/policy.py`**:
   - Added `attrgetter` and `methodcaller` to `FORBIDDEN_ATTRIBUTES`. This refuses `operator.attrgetter`,
     aliased `op.attrgetter`, and (via `_forbidden_member`) `from operator import attrgetter` / `methodcaller`.
     `operator.add` and other non-reflection members still pass.
   - Regenerated the derived (untracked) `skillopt/execskill/sandbox/policy.json` (pre-launch build artifact; nothing
     of route B has run, so this is a refresh, not a relabel of a frozen run). New `policy_sha256` =
     `a17386849d20a617adb4e8729ac79076b2d4e0c68bc83792bbe665afa98a7dd1`. Version string unchanged
     (`fivebench-execskill-v1-policy`) to avoid manifest/pin churn in M1's area; the manifest reads the code-computed
     hash, so it tracks automatically.

## Tests
- Added policy tests (`tests/test_execskill_policy.py`): `test_reflection_helpers_that_build_attribute_access_from_a_string_are_banned`
  (4 params incl. the constructed-dunder exploit and the aliased form), `test_reflection_helpers_cannot_be_from_imported`,
  `test_operator_non_reflection_members_still_pass`.
- Added sandbox tests (`tests/test_execskill_sandbox.py`): `test_a_call_runs_in_a_private_writable_directory_removed_afterwards`
  and `test_each_call_child_runs_in_its_own_private_directory` (drive `worker.run_call` on raw code, TMPDIR redirected
  to tmp_path, host mode).
- Targeted runs on dl (pinned interp): `test_execskill_sandbox.py` + `test_execskill_policy.py` = **161 passed**.
  `test_execskill_s0.py` + `test_execskill_smoke.py` + `test_execskill_evaluation_sheet.py` +
  `test_execskill_shortcut_sb.py` = 66 passed, **1 failed** (see open items — not mine).

## Mutation entries 81-83 (`tests/test_execskill_mutations.py`, W's reserved range)
- 81 `_reset_writable(call_dir)` → `pass` ; test: the private-dir-removed sandbox test.
- 82 `os.chdir(call_dir)` → `pass` ; test: the per-call-own-directory sandbox test.
- 83 remove `"attrgetter"` from `FORBIDDEN_ATTRIBUTES` ; test: the reflection-ban policy test.
Each site occurs exactly once; each named test was confirmed to FAIL under its mutation in an isolated tree copy
(and pass unmutated). Full mutation suite NOT run (I1 runs the whole suite on a fresh copy).

## Real-container evidence (zero model calls, throwaway root `/tmp/w-*`, deleted afterwards)
Pinned image `sha256:0a0a5dcb…`, registered cell argv (CELL_LIMITS 768m/0.5/64):
- (a) cross-call: call 1 `os.mkdir('/tmp/escape-marker')` succeeded under FSIZE=0 (`call1_created_marker: true`), yet
  `call2_marker_visible: false` and call 2's `/tmp` held only its own fresh private dir — the marker did not survive the
  request (the PID-1 sweep ran in the entrypoint parent).
- (b) existing escape rows: all 11 (`escape_rows` + `fixer9_rows`) PASS with the amended worker; `dumpable: 0`.
- Cleanup: no leftover `execskill-sbx-` containers; throwaway root removed.

## Cross-owner edits
None. All edits are W-owned (policy.py, sandbox/worker.py, sandbox/policy.json, their tests, mutation entries 81-83).

## Open items / notes
- NOT MINE: `tests/test_execskill_shortcut_sb.py::test_c1_2_the_shortcut_gate_reaches_its_verdict_on_cells_run_without_the_workbook`
  failed (examiner shortcut-gate verdict `gated["kept"]`). `examiner.py` (18:30), `step.py` and that test file (18:34)
  were being edited by the concurrent builders who own examiner/step/shortcut (E/M2a/M2b) during my run; the test uses
  `FakeSandbox` and never touches policy/worker/attrgetter, so it is independent of this fix. Flagged for the owner.
- The container's PID-1 `/tmp` sweep is not unit-testable on a host (getpid≠1); it is covered by the real-container
  check above. If a permanent S0 row is wanted for it, that touches `smoke.escape_rows`/`s0.fixer9_rows` (M1), so it was
  left as the manual real-container verification the ticket asked for rather than a cross-owner edit.
