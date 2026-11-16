# Review rc-plan (read-only reviewer)

Lens: read-plan identity, sealing and failure paths (batch = git diff de7346c,
context = git diff 8375ecb). Trusted only the code.

## Plan
- [x] Read the binding docs (addendum RP1-RP15, D16, D17; read-plan spec 1.B, 1.C, 1.D, 3, 4.3)
- [x] Read T/readplan.py (integration part 1408-1892 and the core it calls), chain.py read-plan methods,
      reads.open_panel / preparation_reset, mount.mount / mount_identity / solve, smoke.py, prepare.py, run_typed.py
- [x] Identity: false equality (request, program, scoring inputs; D16; D17 base; Q23 unknown items)
- [x] Identity: false difference (event-specific values)
- [x] Capture sends nothing
- [x] Sealing (open plan, alias records, state, status, pause details, replay child stdout/stderr)
- [x] Automatic replay child (command, env, seed, exit/verdict mapping, smoke root, fake child)
- [x] Fallback and void paths (RP10, RP11, Q24 A, R44)
- [x] The smoke probe (Q20, R7)
- [x] Tests run

## Done
Checked against the code; details in "Findings" and "Checked OK".

## Findings
1. (minor, affects paid calls) chain.py:1014 `replay_plan`: the "second error voids" rule tests
   `detail in rp['failures']`, i.e. ANY earlier occurrence in the whole run, not the previous recovery
   outcome (R44 d). The replay can run again after an equal one (verify_read_plan restores a plan file and
   sets `rp['replay'] = None`, chain.py:1091). Scenario: first replay `replay_error:timeout` -> pause ->
   recovery -> replay `equal`; reads start, some aliases settle; later the plan file fails its check ->
   recovery restores it -> the check replay times out again -> `seen` is true -> void_plan('replay_error')
   at once, with no pause: every settled alias becomes void_alias and is read fresh (up to 26 extra fresh
   units per chain). Safe direction (fresh reads), but paid calls the spec does not require.
   Fix: decide "second" from the previous recovery outcome of the same detail (e.g. the last entry of
   rp['recoveries'] / the detail of the last applied recovery), or clear the replay failure history when a
   replay is recorded `equal`.

## Checked OK (no defect found)
- Identity: system text hashed after composition (D17 base, D16 member cards via the frozen library,
  Q23 unknown items mount system_card(bench,'',base) in both mount and mount_identity); offered program
  bodies (skill sha256 = body hash) and the selection request (names, descriptions, public text) hashed;
  public and view hashed; capture covers runtime/configuration effects on the first request of
  non-ALFWorld items without programs; the pass and the read units pass the same base_card (manifest),
  view function, vectors source, nominal M, scorer root and mode.
- No false difference found: public/view are per item, identical across events; the first request does
  not carry the unit, tag or package label.
- Capture: capture_selector and CaptureCall never reach a client or the ledger; mount.solve with no
  enabled program starts no worker and skips _sheet_score; the frozen _response makes one call.
- Sealing: open plan checked by check_open_record with every item id; alias records counts/hashes only;
  pause details are fixed codes or class names (_pause_detail, _guarded); replay child prints fixed keys
  only and the parent keeps only a closed-vocabulary code; stderr captured and dropped.
- Replay child: smoke_root is idempotent (no double suffix); replay services use the same mount, identity,
  view, worker options, runtime and nominal M as the real services; native/heavy None does not change the
  first request; ALFWorld views loaded from the inputs file.
- Fallback/void: pass_failed second same code voids and marks read-plan; void_plan / void_bench archive
  aliases and the sweeps read every unsettled pair fresh; complete_reads requires every pair fresh-complete
  or a verified alias with a fresh-complete representative before step markers.
- Probe: prepare/read_plan_of refuse it on a real root and with full; identities_record turns the ok pair
  into smoke_probe, its own class, read fresh in the first sweep.

## Tests
mkdir -p /tmp/typed2-neutral/rc-plan && cd <repo-root> &&
TMPDIR=/tmp/typed2-neutral/rc-plan <python> -m pytest -q -p no:cacheprovider
tests/test_typed_readplan.py tests/test_typed_readplan_core.py
Last line: 83 passed in 19.34s

## Choices
Read-only; no tree file edited except this notes file. Scratch only under /tmp/typed2-neutral/rc-plan/.

## Disagreements
None with the spec; finding 1 is a deviation from R44 d's wording ("the previous recovery outcome").

## Left for later steps
Not reviewed in depth: readout economy tables beyond the alias resolver and contrasts; machinery guard (7g).
