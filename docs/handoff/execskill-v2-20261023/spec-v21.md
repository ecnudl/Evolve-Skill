# Route B v2.1 — change specification as implemented (2026-10-24)

## Owner decisions (chat, verbatim)
- 2026-10-24 02:22: "好的，那就按照你的说法来，先修，修好之后继续跑" — approve the proposed fixes ①–④ and relaunch both
  chains from scratch in a new root. Item ⑤ (explain the LiveMath meta option in the task card) was not chosen; it
  would change the card and make the existing baselines incomparable, so it is not done.
- 2026-10-24 02:22 (right after): "我要去睡觉了没法同意，我给予你权利，你去同意吧" — the owner delegates the approvals
  that would otherwise wait for them, in particular the read consent of the new root. Recorded in the registrar; the
  consent's note discloses the delegation. The smoke-waiver rule ("only the owner writes it") is not touched: v2.1
  reuses the v2 smoke of record and its existing owner waiver.

## Why (main-v2, 2026-10-23 21:54 – 2026-10-24 00:01, run 67453b36…, aborted)
- Chain D wedged at ~22:10: every elucid call ended in PoolTimeout with no socket open. httpcore 1.0.9 keeps a proxy
  tunnel whose TLS handshake timed out in its pool as an ACTIVE connection that is never closed or removed
  (`TunnelHTTPConnection.handle_request`: CONNECT, then `start_tls` raises ConnectTimeout); with httpx's default 100
  connections the 100th such timeout exhausted the client's pool forever. 98 ConnectTimeouts preceded the first
  PoolTimeout; a fresh process probe went 3/3 OK. Chain D was stopped at 23:09 (237/300 run cells).
- Chain G stopped (exit 3) in `G/s3-livemath/engineer-r3`: `TypeError: unhashable type: 'dict'` in
  `replay.validate_test` — the engineer wrote a replay test's mutation as `{"strip_digits": true}`.
- LiveMath round 2 adopted `p-livemath-3-1` (10 fixed / 3 broken of 65, p = 0.046): a meta-option shortcut. Its
  predicate fires only when the option "One of the remaining options is correct, but a stronger result can be proven."
  is present (detected with "remaining" and "stron"+"ger"), and its note tells the solver to "weigh this
  self-referential entry". It got past C4 after the fix calls echoed the screen's matched phrase ("one of the
  remaining") and the adjudicator's reason, and the next fix reply paraphrased around them. That option is the
  correct answer in 129/129 LiveMath training items. Acceptance's J7 (options-only probe) would likely have rejected
  the package at acceptance, but training adopted it.

## Changes
1. Connection pools (every configuration; infrastructure): `client.POOL_LIMITS = httpx.Limits(max_connections=None,
   max_keepalive_connections=20)`; `client.http_client(read_timeout, options)` builds every solver and role client's
   httpx client (the frozen constructor's settings + POOL_LIMITS); `client.unpooled(frozen, ...)` rebuilds the httpx
   client of a frozen `weak_solver_probe.Client` (chain G's solver in `solver_client`, the GLM-5.3 roles in
   `manifest._clients`). `scripts/weak_solver_probe.py` (frozen) is unchanged. The research sources' Wikipedia client
   (`research.Wikipedia`) takes POOL_LIMITS too (Codex review 2026-10-24 #1). Concurrency stays bounded by the slot
   pools (`protocol.SLOTS`).
2. Type guards on model-written values (every configuration): `replay.validate_test` checks that the trajectory, the
   hook, the property kind and the mutation are strings before using them as keys (returns its registered reasons);
   `engineer.leak_check` reads a replay test's trajectory only when the test is an object and the trajectory a
   string; `engineer._fix` looks up the target key only for a string kind. The SpreadsheetBench family refuses a
   written edit target outside A1:XFD1048576 (`edit_target_invalid`) and a formula holding a character a worksheet
   cannot store (`format`) before any file is written (Codex review #2: both raised openpyxl errors that
   `generators.generate` did not catch).
3. Configuration `main-v2-1` = `main-v2` + two engineer rules, read from protocol tables by `step._engineer_train`
   into `engineer.Context` (train mode only; `Context.__post_init__` refuses them elsewhere):
   - `FIX_ECHO[main-v2-1] = False` → `engineer._redacted`: a fix call shows a failed C4 without flagged texts,
     matched terms, static-ban details or the adjudicator's reason (static bans: rule + line; output bans: cell,
     hook, step, kind — a letter ban "option_letter" — and, for a counterfactual difference, its aspects and
     `COUNTERFACTUAL_RULE`; leakage hits: place, bench, reason codes, adjudication outcome); a failed C9 with each
     fault's cell, hook, step and kind only. The sealed engineer record keeps the full detail. Other checks unchanged.
     With echo off, the trajectories the proposal and analyst calls show carry no screen match either: the message of
     a `note_lexicon`/`note_meta_option` fault and the detail of a note field dropped for `lexicon`/`meta_option`
     become null, kinds, fields and reasons kept (`engineer._unechoed`; Codex review #3).
   - `META_COUNTERFACTUAL[main-v2-1] = True` → in C4 (after the output/letter bans, before the leakage adjudication)
     `replay.meta_counterfactual`: the procedure is replayed (zero model calls, fresh worker, PYTHONHASHSEED 0) on every
     in-scope LiveMath trajectory whose view contains the meta option, with the option's text replaced by
     `META_FILLER` ("This option's wording is withheld and replaced by this neutral sentence."); any difference
     from the real-view outcome in predicate, shown notes (per hook/step), bindings, repair request, ALFWorld steps
     or fault kinds — counterfactual texts with the filler mapped back to the option — fails C4 as output bans
     `{cell, kind: "meta_counterfactual", aspects}`.
   - Prompts (and their hashes), slices, caps, schedules, factors, read cells, stage reads, learning mode: main-v2's.
     New root `/data/execskill-20261024-main-v2-1`, manifest `/data/execskill-20261024-main-v2-1-manifest.json`,
     evidence `main_v2_1_real_run`, consumption namespaces `G-v2-1` / `D-v2-1` (the same fixed-order cut; main-v2
     dispatched no acceptance item). `routes.check_pins` requires chain D's route-B pin as for main/main-v2.

## Known limits (registered, to disclose)
- The counterfactual is vacuous before LiveMath (steps 1-2 have no LiveMath trajectory); acceptance's J7 remains the
  backstop for a procedure first adopted there. It cannot catch a procedure that steers every LiveMath item the same
  way regardless of the option (also J7's job).
- Only a whole verbatim quote of the option maps back, and no LiveMath note field can hold one unscreened (table cells
  hold 40 characters; facts/candidates/warnings are screened for the meta phrases), so any note that carries part of
  the option's text on a meta-present item is flagged — conservative by design.
- A procedure whose output depends on call order within a worker could differ spuriously; C6 already requires equal
  value hashes across two orders and seeds.

## Codex review and zero-call validation (2026-10-24 03:0x-03:30)
- Codex, one round (gpt-6-astra, ultra, read-only mirror): NOT ACCEPTABLE, 4 MAJOR, no BLOCKER; all fixed
  (`codex-review-v21.md`): the Wikipedia pool (#1), the sheet family's bounds (#2), the shown trajectories' screen
  matches (#3), the launch script's patch-hash check before any snapshot artifact (#4).
- Real records, zero model calls, real docker sandbox (the main-v2 manifest's image and limits): main-v2 chain G's
  LiveMath run slice, 119 stored trajectories, 65 holding the meta option. `p-livemath-3-1` (the adopted shortcut):
  C6 passes, it applies on exactly the 65 meta-present items (0 of the other 54), and `meta_counterfactual` flags
  65/65 (applies + notes), so v2.1's C4 fails it. The three SearchQA procedures never apply on LiveMath: 0 flagged.
  The synthetic controls on the same real trajectories: a generic hint 0/119 flagged, the option count 0/119, a note
  quoting each option's first characters 53 flagged, all meta-present (the registered conservative limit). The four
  replay tests of main-v2's crashing r3 reply: t1, t2 (mutation an object) -> "mutation", t3 ->
  "predicate_needs_mutation", t4 valid; no exception. Reports `/root/ops2-20261022/logs/v21/validate-cf.json`,
  `validate-cf2.json`; scripts beside the v2.1 patches in `/root/ops2-20261022/work/v21/`.
- Tests: the registered selection before the review 1,514 passed, 1 failed (mutation 30: its site moved with v2.1's
  GLM construction; the site now names the construction inside `unpooled`); after the review fixes, targeted 187
  passed, then the registered selection again (the launch record has the count).

## Launch (zero-call preconditions, then the run)
Smoke of record: the v2 smoke on snapshot e (chain-G smoke, S-E6 projected main-v2; SX passed; S2.format waived by the
owner's v2 waiver, 2026-10-23 21:20). main-v2-1 is priced exactly as main-v2 (`main21_delta.priced_as_main_v2`), so
the test-read estimate is the record S-E6 projected (configuration main-v2), whose value and terms equal
main-v2-1's. Snapshot g = f + the reviewed v2.1 patch; `main21_delta.py` checks e -> g exactly (snapshot lists, git
parents and both reviewed patch hashes, code map, clients, runtime, echo sets, q23-g vs q23-e). Order: registered
test selection → commit g → `main21-snapshot.sh g` → `main21-q23.sh` → `main21-consent.sh` (delegated) →
`main21-go.sh` → `main21-pins.sh` → `main21-manifest.sh` → `main-tls.py` → chain G → G's first-call confirmation →
chain D on route A → D's confirmation.
