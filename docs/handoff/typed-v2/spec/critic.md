# typed-v2 spec cross-check (critic)

Status: FINAL (2026-11-12). Written after two interruptions; the 35-minute limit was exceeded, so the last part is a
NOT DONE list. Scope: `spec/card.md`, `engineer.md`, `reply.md`, `gate.md`, `identity.md`, `schedule-lock.md` against
`DECISIONS.md` (D1..D8, F1..F6) and the code of this tree. `T/` = `skillopt/execskill/typed/`, `X/` =
`skillopt/execskill/`, `W` = `T/writers.py`, `C` = `T/chain.py`. [V] = I opened the cited lines, [I] = inferred.

Blockers under the F1 rule: none found. No decision is impossible inside `T/`, `scripts/`, `tests/`, `docs/`.
D5 is incomplete against the code in one place (2.1) and needs a coordinator decision before the gate is written.
The six sections cannot be implemented as they stand: 8 major items below must be merged first.

## 1. Edits to snapshot-loaded files (F1 / D1)

- 1.1 No section plans an edit of `X/*` or `skillopt/coevo5/*`. Checked sites: `mark_infrastructure_reruns` is a
  `T/` function (`T/units.py:301-321` [V]); the lock choice only changes the setting passed to the existing
  `X/chain.heavy` (`X/chain.py:126-144` [V], called at `C:1131-1132` [V]); the container scope only changes the
  string given to `sandbox.unit_tag` / `drain_unit`, whose only call sites are `C:1155, 1164` [V, grep over `T/`].
- 1.2 No import-time or run-time monkeypatch of a machinery module is planned [V, grep of all six sections]. The
  only occurrence is a pytest case (`engineer.md:287`). Rule to add: it must use the `monkeypatch` fixture and must
  never run in the bound child process.
- 1.3 `card.md:130-131` copies the content screen `X/v225_cards.py:169-201` [V] into `T/cards.py` and calls private
  machinery names (`v225_cards._reference_values`, `PATH_LIKE`, `leakage._numbers/_numeric/_significant/_value/
  _grams`, `engineer.absent_findings`, used at `X/v225_cards.py:176-198` [V]). Allowed by F1 (read and call), but
  this is a second copy of a leak screen. `COPIED_SOURCE_SHA256` is "not computed" (`card.md:252`). Every private
  name must be in `machinery.REQUIRED` (`identity.md:211`); card.md does not list them for that purpose.
- 1.4 GAP. The guard covers 564 `.py` files only. 64 other files under `skillopt/` are loaded from the snapshot and
  are unchecked (`identity.md:14-15`, Q2): 21 in `skillopt/prompts`, 7 in `X/sandbox`, 19 in `skillopt/envs/*/
  prompts`, others [V, counted]. Local tests read this tree's copies; the real run reads the snapshot's. D2's
  "byte-identical first request" and every prompt pin are therefore proven only for this tree.
- 1.5 GAP. `bind_machinery` appends this tree's `X/` to `skillopt.execskill.__path__`
  (`scripts/run_typed.py:48-50` [V]). A NEW module dropped into this tree's `X/` is importable in the bound run; an
  EDITED one is silently ignored. `identity.md:44-45` checks unlisted `.py` files in the SNAPSHOT; whether the same
  check runs on the TREE at every real start is not stated [I].

## 2. Decisions D1..D8: deviations

D5 formulas re-derived, no error: with `q[i] = R*sum_r x^2 - S^2 = R*sum_r (x-m)^2`, `sum_i s2[i] = Q/(R*(R-1))`,
so `SE = (100/(R*n))*sqrt(2*Q/(R-1))` = the D5 text. `reaches(D, m)` and `no_regress(D)` are exactly
`gain >= max(a, c*SE)` and `gain >= -max(a, c*SE)` in integer form; the fired-subset form (`m` items, whole-slice
`Q` and `n`) keeps typed-v1's rule (`T/gates.py:143-164` [V]). Cell identity: the tag is
`sha256(bench, item_id, label)` (`T/units.py:253-254` [V]), so `<arm>#<r>` gives each repeat its own cell, call
file and rerun entry. No stored-result path between repeats: the selection call is per cell (`C:456-475` [V]),
the recorder always calls the client (`T/units.py`, about :219 [V]), request reuse is not on the typed solve path
(`X/profiles.py:1013-1014` [V], used only by `X/v218_read.py`, `X/acceptance.py`).

- 2.1 D5, MAJOR. `gate.md:136-146` treats EVERY `correct is None` cell as missing and re-runs it after a pause.
  That includes the model-side token `unknown_artifact` (`skillopt/coevo5/outcomes.py:138` [V]: an unscorable
  candidate workbook; mapped to `None` at `T/mount.py`, about :407 [V]). D5 defines a missing cell as an
  infrastructure failure. Three effects: (a) an arm whose answers are unscorable is drawn again until scorable,
  which is a selection in favour of that arm; (b) the same request is sent more than R times; (c) a program that
  always writes an unscorable workbook pauses the chain at every attempt ("the same pause again"), each needing an
  owner-level recovery. Today only infrastructure / configuration cells are re-run (`T/units.py:316` [V]).
- 2.2 D5, decision needed. After an accepted card, the card's own accepted gate runs become the baseline of the
  program gate (`gate.md` 1.6, risk 2). They are selected-high runs; typed-v1 re-ran F (`C:850-851` [V]). D5's
  sharing rule requires this; only a fresh `F#1..3` (forbidden "beyond R") removes it. The bias makes program
  acceptance and program no-harm stricter, never looser.
- 2.3 D5, not in the decision. "Fired" becomes "fired in at least one of the R cells" (`gate.md` item 17).
- 2.4 D5, record gap. tau is computed per comparison from that baseline's repeats (`gate.md` item 20), but
  `decisions.json['tau_points']` and skill origins keep the C0 value. Readers of the record will see a decision
  that does not follow from the stored tau unless each decision row stores its own tau and Q.
- 2.5 D5, design change not stated as such. The no-harm baseline moves from the same unit, run back to back per
  item (`C:712-724` [V], `T/units.py:257-262` [V]), to the earlier noise unit. Time drift of the provider between
  the two units now enters the no-harm comparison.
- 2.6 D5 cost statement is not the maximum. `gate.md:156-159`: 15n excludes no-harm checks (3n each) and case (d)
  (3n). The table "2,640 against 4,950 cells" (8 x 330, 15 x 330, arithmetic correct) is therefore a floor of the
  maximum; with one no-harm check and case (d) per step it is 21n = 6,930.
- 2.7 D3, MAJOR. `gate.md:307` keeps "the gate takes `proposals[:max_program_candidates]`" (`C:871-872` [V]).
  `engineer.md:71, 333` returns up to three proposal rows of which those with a slot go to the gate. Under gate.md
  a dropped first proposal uses a gate slot and a promoted third proposal is never gated: D3 is not implemented.
- 2.8 D6, caps not shown. Two estimates on different bases, never reconciled: `gate.md:173` (design: under about
  108M for G; no D figure) and `identity.md` item 12 (practice after about 3.5 steps: 85M G / 107M D [I]). Neither
  contains: the ALFWorld learning step, which typed-v1 has not reached and whose gate cells are multi-call
  episodes (40 x 3 x up to 5 arms = 600 episodes); the longer cards in every later solver request (D2; reads are
  26.2M of G's 33.7M); the 10k to 11k character engineer prompt with up to 5 writer calls (D3, D4); 2.6 above.
- 2.9 D6, wording. Draw keys keep `typed-v1` literals (`W:36` [V], `T/prepare.py:39` [V]; `identity.md:37`). This
  is needed for D2's byte-identical first request and for item-paired comparison with typed-v1, but D6 says "new
  names". Needs an explicit exception in DECISIONS.md.
- 2.10 D6, pins. card.md and engineer.md ask where `cards.pins()` and the prompt pins are stored and checked.
  `identity.md:164, 214` answers: source constants with tests, covered at run start by the tree hash (item 9).
  Acceptable, but nobody calls `engineer_prompt.verify()` or checks `COPIED_SOURCE_SHA256` at a real start; state
  one rule. Side effect of item 9: the start check uses `provenance.typed_tree`, which hashes `skillopt/`,
  `scripts/` and `tests/` (`T/prepare.py:226-236` [V]); any ops helper or test touched after `prepare` blocks every
  resume. `typed_code` (`T/**` + `scripts/run_typed.py`) plus the machinery list is the narrower, sufficient check.
- 2.11 D7 finding verified [V]: `unit_tag` = chain letter + 12 hex of sha256(unit) (`X/sandbox/client.py:138-143`),
  `drain_unit` removes by that prefix (`:316-325`); same-letter typed-v1 and typed-v2 processes with the same unit
  name would drain each other. Q1 (scope string) removes it and is T-only. Not yet a decision.
- 2.12 D8 verified [V]: default lock call unchanged; `unit_shared` uses the same lock file
  (`X/v218_lock.py:101`), so it excludes typed-v1's plain flock; it needs `root`, `memory_lock_chain`,
  `memory_lock_unit` (`:97-100`) and `schedule-lock.md:167` supplies them. D1, D2, D4: no deviation found.

## 3. Contradictions between sections

- 3.1 Gate input: 2.7. Also `programs()` (`C:841-873`) is rewritten by gate.md (shared baseline, repeats) and by
  engineer.md (iterate every row, zero-call decision rows, base keys `proposal`, `status`). No merged version.
- 3.2 `W:436-439` `_row`, `W:442-466` `_fix_once`, `W:469-515` `propose_programs` [V] are each rewritten by reply.md
  (`reply.md:129-130`) and by engineer.md with different contents; reply.md leaves `W:499-502` to engineer.md but
  both change the row shape and the signature of `_fix_once`. `T/smoke.py:36-41, 180` likewise; gate.md also edits
  `T/smoke.py:28, 263-283, 300-306`. `W:30` is edited by card, reply and engineer.
- 3.3 Fix request: engineer.md sends `{'request','bench','change','failed_source','failed'}`; `reply.md:245`
  recommends that the fix request stop sending the source inside `change`. Two definitions of one message.
- 3.4 Bound test: card.md copies this tree's `skillopt/` without `typed/`; `gate.md:289` binds "a stub snapshot"
  and imports `typed.mount` and `typed.chain`, which cannot import from the two-file stub of
  `tests/test_typed_cli.py:80-84` [V] (only `T/gates.py` is stub-safe, `T/gates.py:11` [V]); `identity.md:176-186`
  says a stub can no longer bind and defines one driver on a 564 + 64 file stand-in. Three designs, one needed.
- 3.5 `gate.md:245` "Unchanged: every request text" contradicts `gate.md:238-241`: the round-2 card writer request
  carries `revision_result(decision)`, whose numbers change meaning and value (`W:222-238` [V]).
- 3.6 `Services` / `real_services` are changed by three areas (`heavy(bench, unit)`; `identity_fn`; `cap`,
  `machinery_code`, container scope). Every fake services object in tests and `T/smoke.py:305` [V] must change in
  one pass; no section owns that pass. `cards()` / `card_decision` (`C:731-788`) are edited by card and gate;
  `finalize` and the chain state by gate, schedule-lock and identity.
- 3.7 Limits: engineer adds a module constant `MAX_PROGRAM_PROPOSALS`; gate adds `limits['gate_repeats']` and a
  manifest field. `test_typed_chain.py:105` hard-codes `max_candidates=2` (map, [I]). One convention is needed.
- 3.8 Implementation order is stated only by `gate.md:316`.

## 4. Sealing and integrity

- 4.1 No path found by which test material reaches a learner: repeats and shared arms use gate-slice rows only,
  the writer still gets counts only (`W:235-237` [V]), read units keep single runs and their own labels.
- 4.2 Consent is not bound to version or root: exactly six fields, none of them a root (`T/reads.py:91-109` [V];
  `identity.md:97-101`, Q5). A consent copied from a typed-v1 root opens typed-v2 test reads. identity.md only adds
  a shell check of `note` in `run-typed.sh`; `consent()` itself is T-owned and can check it.
- 4.3 Refusal of typed-v1 roots: `_open_state` checks the version in the chain state only (`C:939-948` [V]).
  Everything else relies on the planned `prepare.own_root`; it must be called by every CLI entry including
  `readout` and `status`, and by `read_panel`, or typed-v2 code can write `read-status/` into a typed-v1 root.
- 4.4 Shared-arm rows keep their original arm label and mount record (C0 rows used as the F incumbent). Every row
  consumer must accept that: readout `by_arm` (`T/readout.py:226-230` [V]), `outcomes_for_writer`, the outcome
  counts in `finalize` [I]. gate.md lists the readout only.
- 4.5 Decisions on resume: decision files are write-once (`C:316-323` [V]) but `no_harm` returns the freshly
  computed dict, not the stored one (`C:712-724` [V]). With per-comparison tau this must return the stored record.
  `plan.json` is the only guard that a resumed gate unit has the same jobs and the same sharing.
- 4.6 Re-drawn cells after 2.1 change a decision input after a pause; the record must keep the archived cell and
  the count per arm, or the decision cannot be audited.

## 5. Resume, atomicity, ledger, budgets

- 5.1 `proposals.json` is written after all writer calls (`C:860-867`, `C:316-323` [V]). An interruption inside the
  programs unit re-sends up to 5 calls (3 today) and redraws the proposals; the in-memory `RetryBudget` restarts.
  Both specs accept this (`reply.md:264-266`, `engineer.md:352-353`). Acceptable for integrity (nothing downstream
  saw the first draw), but the calls file must keep every send, and no test covers it.
- 5.2 Rerun set holds bare tags (`T/units.py:116-117, 341-345` [V]). The same bench, item and label recur in
  `card-r1` / `card-r2`, `program-1-gate` / `program-2-gate` and every `noharm-<T>`. After a double fault a valid
  stored cell of a later unfinished unit is drawn again (`gate.md` 3.5, "No change planned"). Unbiased, but it is a
  draw beyond R. The pending entry already carries `unit` (`T/units.py:143-164` [V]).
- 5.3 Caps: see 2.8. The ledger refuses a changed cap (`T/units.py:114-115` [V]), so a wrong cap means a new root.
  The reservation is `CLIENT_ATTEMPTS * (bytes + overhead + max_tokens)` per in-flight send [V]; small here.
- 5.4 Wall time is not budgeted. All labels of an item run back to back in one worker (`T/units.py:257-262` [V]),
  so a gate unit takes about three times as long. SpreadsheetBench: 150 cells per gate arm, up to 750 per chain in
  its step, one at a time on the whole machine under the default lock (`schedule-lock.md` L5: `t_cell` unknown),
  while typed-v1 may still hold the same lock.
- 5.5 One format retry per unit is kept in memory only; a unit resumed after its retry was sent can send a second
  one. Harmless under 5.1 (the unit restarts from its first call), but D4's "one per unit" then holds per attempt.

## 6. Requests that change versus typed-v1 (complete list)

Intentional:
1. Card writer attempt 2: typed retry text instead of `v225_cards.CARD_RETRY` (D2; `W:284-285` [V]).
2. Card writer round 2: `previous_card` up to 4,500 content characters (D2) and `result` numbers on item means with
   this decision's tau (D5). NOT declared by gate.md (3.5 above).
3. Engineer system text, propose and fix, all five benches (D3; replaces `W:310-315` [V]).
4. Fix user message: adds the failed source and screen evidence (D3; today `W:446` [V]). See 3.3.
5. New format-retry request with its own system text and at most 200,000 bytes of the previous reply (D4).
6. Writer calls per programs unit: at most 5 instead of 3 (D3, D4).
7. Every later solver system message and the describer request carry cards up to 4,500 characters (D2).
8. Gate cells: identical request text sent R times; no-harm baseline taken from the noise unit (D5).
Unchanged [V]: first-attempt card request (`W:254-266`, limits told 3,000 / 12 from `X/v225_cards.py:13-14`, example
reserve `W:243-244`), solver and selection request construction, step label, draw keys. [I]: `VERSION`,
`LIBRARY_VERSION` never enter a request (identity.md's grep, not repeated).
Possibly unintentional: if the decision record drops `excluded_unknown`, the round-2 `result` changes from `0` to
`null` (`W:229` uses `.get` [V]); keep the key.

## 7. Test plan gaps

- 7.1 One bound harness (3.4). The stand-in is built from this tree, so it proves import origin and symbol
  presence, not equality with the real snapshot; the second run on dl (`identity.md:179`) is the only real proof
  and must be a named pre-launch step. Python 3.13 on the Mac against 3.11 on dl.
- 7.2 Machinery guard: no case for a differing non-`.py` file (1.4); no case for an extra module under this tree's
  `X/` at a real start (1.5); no case that a private name used by `T/cards.py` is missing in the snapshot.
- 7.3 Gate: no case for a deterministic unknown cell (2.1); no case that a recovered cell is counted per arm; no
  case for the double fault of 5.2; no property test that the integer forms equal the D5 formulas on random data
  with non-binary scores at the 1e-9 tolerance [I]; no case that each decision row stores its own tau (2.4).
- 7.4 Engineer / reply: no resume case inside the promotion loop or after a format retry (5.1); no case that a
  dropped row never reaches a gate unit and a promoted third row does (2.7).
- 7.5 Identity: no case that each CLI entry and `read_panel` refuse a typed-v1 root and a consent without the
  root name (4.2, 4.3); no cap projection case including the ALFWorld step (2.8).
- 7.6 Requests: no golden test of the round-2 card request bytes under D5 (6.2).

## 8. Citation spot-checks

No wrong citation found. Checked and correct [V]:
- card.md: `W:30`, `W:36`, `W:260`, `W:269-272`, `W:275-295`, `X/v225_cards.py:161, 167, 169-201, 178`, `C:784`.
- reply.md: `W:436-439`, `W:442-466` (and `:448, :452-461, :462-464`), `W:469-515` (and `:483-487, :488, :491-494,
  :495-498, :499-502, :503-504`), `C:316-323`, `X/engineer_reader.py:21, 23, 26, 49, 141, 234, 299`. `C:860-865`
  is `C:860-867` (two lines short, same statement).
- engineer.md: `W:29-30`, `W:40`, `W:299-307`, `W:310-315`, `W:387`, `W:396-415`, `W:403-404`, `W:499-502`,
  `W:505-514`, `C:871-872`, `C:888-891`, `C:316-323`.
- gate.md: `C:465, 469, 499-504, 508-510, 664, 668-671, 712-724, 726-729, 850-851, 871-872, 904-908`,
  `T/gates.py:90, 101-173`, `T/units.py:253-254, 301-321, 334-337`, `W:222-239`. `T/units.py:116-124` is `:116-117`.
- identity.md: `T/units.py:114-115`, `C:939-948, 973, 1155, 1164`, `X/sandbox/client.py:138-143, 316-325`,
  `T/prepare.py:34, 39, 226-236`, `T/library.py:91`, `tests/test_typed_cli.py:80-105`.
- schedule-lock.md: `X/profiles.py:1005-1018`, `X/chain.py:129-133`, `X/v218_lock.py:37-41, 97-100, 123-125`,
  `C:469`, `C:1131-1132`, `T/reads.py:269`.

## NOT DONE

- Not opened: `T/reads.py:272, 342`; `T/__init__.py:43, 60`; `skillopt/coevo5/leakage.py`; `T/smoke.py:36-41, 180,
  263-283`; `tests/test_typed_chain.py:105`, `tests/test_typed_writers.py:297-304` (taken from the map).
- Not re-read after the interruptions: card.md 1.3 (consumer table), engineer.md rule table, schedule-lock.md
  L1..L7 in full. Claims about them above are marked [I] or cite the line I re-opened.
- Not checked: the non-binary tolerance path of gate.md; `safe_path` on the run root for the `unit_shared` log
  files (`X/v218_lock.py` writes `chain.log` and `lock-waits.jsonl` under `<root>/<chain>/`); whether
  `prelaunch.sha256_list` skips `__pycache__`.
- Not possible here (no ssh, no ledger): the cap projection of 2.8 and the count of `unknown` gate cells in
  typed-v1, which decides how often 2.1 would fire.
