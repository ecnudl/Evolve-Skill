# typed-v2 design merge: changes by source id

Merge of 2026-11-12 (evening) of `DECISIONS-ADDENDUM-20261112.md` (up to its section of 19:52) and the corrected
`spec/read-plan.md` into `DESIGN.md` (15:40) and `IMPLEMENTATION-ORDER.md` (15:39), then one fix pass on the
checker's 15 issues (id merge-fix, about 20:45; last section of this file). Outputs in this directory: `DESIGN.md`
(659 -> 1,503 lines) and `IMPLEMENTATION-ORDER.md` (143 -> 315 lines). The sources under
`execskill-typed2/docs/handoff/typed-v2` were only read.

Method. The originals were spliced by line: every original line is kept verbatim except these replaced ranges.
DESIGN: 1-14 (header), 37 (table row 9), 47-49 ("Not changed"), 59-63 (F2, F3), 350-356 (gate step sequence),
371-382 (gate decision bullets), 384-398 (shared arms), 415-417 (gate cost), 513-525 (table 4.1), 600-604 (order
before a paid call, caps), 613-628 (section 7), 630-648 (O1..O10 of section 8). IMPLEMENTATION-ORDER: 1-11 (header).
All other new text is inserted; each folded passage carries its source id in brackets, and each replaced statement
keeps one line "Changed by <id>: <what>". The parts and the splice script are in `parts/` (`parts/assemble.py`).
The fix pass edited the two merged files directly, not the parts: `parts/` and `parts/assemble.py` reproduce the state
before the fix pass, so re-running `assemble.py` would undo it. The fix pass also replaced these original DESIGN
lines: 229-231 (the hooks check, now with O7's order and "Changed by O7"), 344-345 (gate labels, "Changed by D17"
beside), 445 (the mark of `LIST_SHA256`), 491-493 (memory ceilings, "Changed by F9"), 567 (the property-test words;
the "Changed by O11" line was already there). No original line of IMPLEMENTATION-ORDER was touched.

Notation: D = merged `DESIGN.md`, IO = merged `IMPLEMENTATION-ORDER.md`; numbers are sections of D; "hdr" = the
header.

## Facts

- F7 (typed-v1 stop, 15:13, units and tokens, finished read events, sealed contents unopened): D 2 (F3 rewritten as
  "F3 ...; F7 its stop"), 7.
- F8 (read unit name, cell tag, request hash, no step in read cells; re-verified by R8, R14): D 2 (new bullet).
- F9 (dl memory facts, shared-lock history): D 2 (new bullet); 3.6 cited it already; 3.6 lock bullet: the memory
  ceilings now against the measured 14,336 MiB, not schedule-lock's 15,360 (fix pass).
- F10 (typed-v1 unit timing): D 2 (new bullet), 3.6 (D15 effect).
- F11 (machinery lists verified on dl; data list made, `DATA_LIST_SHA256`): D 2 (F2 rewritten, new bullet), 3.5 (data
  files resolved; `LIST_SHA256` marked [F11], fix pass), 4.3, 6 (order), 8 (O2); IO Step 7 note.
- F12 (token projection, per-step figures, owner figure corrected before launch): D 2 (new bullet with the table),
  3.4 (cost), 6 (order, caps), 8 (O3); IO Step 7 note.
- F13 (unknown pairs in typed-v1 gates): D 2, 3.4 (O1 bullet), 8.
- F14 (shared types in typed-v1 change earlier benches unchecked): D 1 (row 12), 2, 3.7 B (R91).
- F15 (historical card C against blank; SkillOpt / GEPA end near C; `historical_text` / `format_text`): D 2 (with a
  note that "B" there is the blank arm, not D17's B).

## Decisions

- D9 (run mode `learn_first` + `read_plan = economy`; `full` default and only value with `interleaved`; fresh
  learning, no typed-v1 practice reuse): D hdr, 1 (rows 9, 10; "Not changed"; the owner text of 14:2x with the
  coordinator's reading marked as such, fix pass), 3.5 (sealed fields), 3.6 (run values;
  read part replaced under economy), 3.7 (decisions, A), 4.1, 4.2 (12), 4.4, 6 (order), 7, 8 (O10); IO intro, batch 3
  (6s, rp-int), Step 6 note, "Do not touch".
- D10 (economy read plan, rules a to h): D 1 (row 10), 3.6 (R20, R35), 3.7 (whole area; (d) with the proof contents
  and "the readout shows the representative's reading ... same requests as <event>", (g) with "pauses on a
  difference", R65 / R66 with the representative's reading and the legend, fix pass), 4.1 (plan, sealed files, alias
  records, state), 4.2 (12), 7; IO batch 3 (rp-int, rp-ro), Step R.
- D11 as revised by RP1 (no carry; C read fresh; typed-v1 C0 / C only as a post-read replicate): D 1 (row 10), 3.7
  (decisions with "Changed by RP1", E), 7.
- D12 (what is never cut): D hdr, 1 ("Never cut" paragraph), 3.4 (D16 d), 3.7 (decisions), 7; IO batch 3.
- D13 (`unit_shared` for run and smoke; reset wrap; sampler; the alternative considered and not taken): D 1 (row 9),
  3.5 (sealed), 3.6 (read-plan reuse of the wrap; carry-receipt clause voided by RP1; the basis of `unit_shared`
  against the ceilings and the alternative not taken, fix pass), 3.7 (R7, R23), 4.1, 4.2 (13), 6 (order, smoke), 7
  (the alternative, fix pass); IO 6s, Step 7 note.
- D14 (both chains on dl): D 1 (row 15), 6 (wall time note), 7.
- D15 (learning widths `LEARN_WIDTHS`, sealed `widths` / `learn_widths`): D 1 (row 13), 3.5 (sealed), 3.6 (new
  bullet), 3.7 (R7, R14), 4.1, 4.2 (13), 5 (`tests/test_typed2_services.py`), 6 (wall time), 7; IO batch 1 (1a, 1b),
  Step 1 note.
- D16 (shared types: writers see member examples; member `no_regress`; `member_harm`; records; scope; cost): D hdr, 1
  (row 12; the owner text of 17:4x with option A as the coordinator proposed it, fix pass), 3.1 (card writer member
  examples), 3.2 (engineer member examples; placement open), 3.4 (step sequence
  (3m), card and program bullets, "Shared types" block, shared-arm search, cost), 3.7 (R91, K-D), 4.1 (decision
  records, member units, writer requests), 4.2 (11), 4.4 (`member_harm`), 5 (`tests/test_typed2_shared.py`), 6
  (reporting), 7, 8 (still open 2); IO batch 2 (5x), Step 4 and Step 5 notes.
- D17 (base card C: sealed `base_card`; learning base arm B; writers shown C; read arms unchanged; cost; reporting):
  D hdr, 1 (row 11, "Not changed"; the owner goal of 17:5x in full, fix pass), 2 (F15 note), 3.1 (first-attempt
  request "Changed by D17"; base-card block; later consumers), 3.2 (proposal payload block), 3.4 (B replaces C0 in the
  step sequence, no-harm, shared arms, cost; "Changed by D17" lines; the labels and B's three uses, fix pass), 3.5 (sealed field, chain state), 3.7 (R7, R91), 4.1 to 4.4, 5 (`tests/test_typed2_base.py`; gate cases
  on B), 6 (`prepare --base-card historical`, reporting against the same C row), 7, 8 (O6 note, still open 6, 7); IO
  batch 2 (5b), Step 1, 2, 4, 5 notes, "Do not touch".

## Coordinator answers and rules

- O1 (model-side unknown scored 0, never re-run, counted; infrastructure re-run, pause): D 3.4 (Cells, "Resolved"
  bullet), 8.
- O2 (data list): D 3.5 (resolved by F11), 8.
- O3 (caps): D 6 (caps resolved), 8.
- O4 (draw keys keep typed-v1 values): D 3.5 ("Resolved"), 4.1, 8.
- O5 (sharing stays; `baseline_selected`; reports name it): D 3.4 (baselines bullet), 4.1, 6 (reporting), 8.
- O6 (fired in at least one of R cells; fired count per item): D 3.4 (program bullet), 4.1, 8.
- O7 (`no_hook_function` accepted; it runs before the frozen `policy.check`, whose call is unchanged): D hdr (BLOCKER
  sentence), 3.2 (O7's order stated as binding; the 4b order as a deviation; "Changed by O7"), 8 (title; O7 partly
  resolved, quoted in full; still open 3); IO Step 4 note. The first merge had kept "after" as the rule (fix pass).
- O8 (twelve `PROBLEM_SENTENCES` worded by the implementer, pinned): D 3.3, 4.3, 8; IO Step 3 note.
- O9 (consent note names the root and states the read plan): D 1, 4.4, 6 (order), 8.
- O10 (read plan integrated in a second pass, after step 6; shares `T/reads.py` with the D13 wrap): D 3.6, 3.7, 8 (and
  still open 1, 9); IO intro, batch 3 order, Step 6 note, "Do not touch". O10 fixes neither the one-change rule of
  `T/reads.py` (that is R24's) nor the place of step 7 (fix pass).
- O11 (binary scores only): D 3.4 (bullet replacing the non-binary one), 4.1, 5 (bullet "binary scores only [O11]",
  fix pass; "Changed by O11"), 8; IO Step 5 note.
- O12 (per-item list forms): D 3.4 ("Records" paragraph), 4.1, 8.
- PG, program gate on the fired items (rule unchanged; informational `se_points_fired`, `se_points_scaled`): D 3.4
  (new bullet), 4.1, 6 (reporting), 8.
- MP, module placement (`T/gatestats.py` pure; `T/gates.py` re-exports): D 3.4 ("Module placement" paragraph;
  "Changed by [MP]" at the change sites), 5; IO batch 1 (5s), Step 5 note.
- BS, build split (strict order for shared files; new modules beside; reports; step ids): IO intro, "Build as actually
  done"; D hdr (mark only). [BS] marks only BS's three rules in IO "Rules of every piece"; the other implementer rules
  are marked [workflow] (fix pass). The ids 6s, rp-int, rp-ro, 7g, "batch 3" and "Step R" are not BS ids: they are
  this merge's proposal, marked [I] in IO and D 3.7.
- RP header of 17:29 ("They do not touch Steps 1 to 7 of IMPLEMENTATION-ORDER.md. The read plan is still built after
  Step 6 (O10)."): D 3.6, 3.7 intro, 8 (O10, still open 1); IO batch 3, Step 6 note, Step R, "Do not touch" (fix
  pass).

## Read-plan decisions

- RP1 (no carry into the run; replicate command after launch): D 1, 2 (F3), 3.5 (`own_root`, `replicate --source`),
  3.6 (carry receipt clause), 3.7 (decisions, E: consent-gated, consent valid in both roots R83, counts and verdicts
  only R86 / R87, the R47b error record, fix pass), 4.1 (no `carried` directory), 6 (owner told; after launch), 7, 8;
  IO batch 3 (after launch), "Do not touch".
- RP2 (credential-free `solver-settings.json`, hash bound): D 1 (row 14), 3.5 (state), 3.7 A (R75), 4.1.
- RP3 (mandatory first-request hashes on four benches, none on ALFWorld; alias stands with u/i/c counts): D 3.7 B
  (R19), 3.7 D (R41), 3.7 F (R66), 4.1 (alias record).
- RP4 (max metrics rule): D 3.7 F (R70).
- RP5 (same phase: model ids and the 24 h recovery rule): D 3.7 F (R67, R89), 6 (recovery records).
- RP6 (automatic replay in a fresh process; no stop in the run; smoke stop and kill): D 3.7 C (R76, R77), 6 (smoke).
- RP7 (no in-run replicate; gate noise beside the tables): D 3.7 F (R69), 6 (reporting: `in-run replicates: <n>`, 0
  as planned, n > 0 only after a fallback read two identical classes, fix pass), 7 (owner option).
- RP8 (the type id is not hashed): D 3.7 B (R12, R14).
- RP9 (one routing path through `mount_identity` / `_route`): D 3.7 B (R16).
- RP10 (post-read mismatch voids every alias of the bench, no pause): D 3.7 D (R42).
- RP11 (the pass pauses only on its own inconsistencies; second same failure voids): D 3.4 (D16 d reference), 3.7 C
  (R33).
- RP12 (answers to Q19..Q24): D hdr, 3.4, 3.5, 3.7, 4, 8; IO batch 3 (7g), Step 7 note. In detail:
  Q19 (the `scripts.*` modules join the machinery check, step 7): D 3.5, 4.3, 8; IO 7g, Step 7 note.
  Q20 (smoke-only `read_plan_probe`): D 3.5, 3.7 A (R7), 4.1, 4.4, 6 (order, smoke), 8.
  Q21 (replay crash or timeout pauses; second error voids): D 3.7 C (R76), 8.
  Q22 (`solver_settings_changed` pauses a resume): D 1 (row 14), 3.7 A (R75), 4.4, 8.
  Q23 (the unknown and card-less branches mount `system_card(bench, '')`): D 3.4 ("Changed by Q23"; shared-arm case
  (b)), 3.7 B (R91 b binding), 4.2 (9), 5 (base tests, T6 variant), 8; IO Step 5 note (5b).
  Q24 (option A, `pass_exception`): D 3.7 C (R33), 8.
- RP13 (answers to the read-plan core's points; integration requirement): D 3.7 (A R1; C R27, R29, R31; D R41; H),
  5 (T23 scope; the frozen-objects test), 8; IO "Read-plan core", Step R.

## Build facts and build rules used (not decisions)

Marked [impl <id>] in D and IO, from `impl/1a.md`, `1b.md`, `1m.md`, `3.md`, `4a.md`, `4b.md`, `4c.md`, `5s.md`,
`5m.md`, `5b.md`, `5w.md`, `5x.md` (plan only; in progress), `impl/rp-core.md` (worktree execskill-typed2-rp), the
commits cdf85b6, e2cf9e7, 3f7e933 and the working tree observed at about 19:55. They fill names and record fields
where the build fixed them (D 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.4, 5) and the build tables of IO.
Marked [workflow] in IO (fix pass): the implementer rules of the build workflow's prompts
(`<local-scratch>/typed-v2-build/workflow-A.js`: the precedence line 31 and "HARD RULES", lines 33-40): own files
only, nothing under `skillopt/` outside `T/`, no ssh / network / paid call, no git write, never delete or weaken a
test, Python 3.11 and 3.13, the precedence for implementers.

## Not decided by the addendum (listed in D 8, "Still open after the merge")

1. Who makes the D13 reset wrap: Step 6 as listed (then `T/reads.py` is edited twice, against R24) or the read-plan
   piece by a coordinator decision; the RP decisions leave Steps 1 to 7 untouched (reworded by the fix pass).
2. Where D16's member sentence goes in the engineer prompt (pinned system texts or user payload only; step 5x).
3. O7's order: O7 binds "before `policy.check`"; the build (4b) runs the check after it (reworded by the fix pass).
4. The Codex review fixes of batch 1 (e2cf9e7) not yet in the main tree.
5. Step 4a's proposal on the [import] rule sentence (new `PROMPT_VERSION`).
6. Step 5b's reading of D17 for the card screen and the label wordings (batch-2 review).
7. Small build gaps (docstrings naming C0, no test of sharing case (d), the `failing_clause` text, an unassigned cap
   projection test).
8. The spec's open checks N13, N15, N16.
9. Step 7 before or after the read plan (O10 fixes only "after step 6"); the place of the read plan's `REQUIRED` and
   bound-driver lines follows the choice (added by the fix pass).

## Fix pass (id merge-fix, 2026-11-12 about 20:45): the checker's issues

Each issue was checked against the addendum (and, where named, the spec and the build workflow). All 15 were
confirmed; none was refuted. Where each fix landed (D = merged DESIGN, IO = merged IMPLEMENTATION-ORDER):

- O7. Confirmed: O7 reads "(it runs before the frozen `policy.check`, whose call is unchanged)"; the merge kept
  "after" as the rule and called O7 resolved. Fixed: D 3.2 states the order of O7 as binding, the 4b order (source,
  policy, hooks, structure) as a deviation until the coordinator confirms or corrects O7, and "Changed by O7"; D 8
  "O7 partly resolved" with O7 quoted in full; still open 3; D header BLOCKER sentence and the title of 8; IO Step 4.
- F9. Confirmed: 15,032,385,536 bytes = 14,336 MiB; the shared-mode ceiling sum, 14,848 MiB, is 512 MiB above it,
  not below. Fixed: D 3.6 lock bullet (MiB figures, the measured limit, schedule-lock's 15,360 named as an
  assumption, D13's basis on F9's history and the sampler, "Changed by F9").
- BS, O10 (batch 3). Confirmed: no source outside this merge contains 6s, rp-int, rp-ro, 7g, "batch 3" or
  "Step R" (searched: the addendum, `impl/*.md`, `spec/*.md`, the rp worktree reports, the build workflow scripts).
  Fixed: IO header (which ids are the addendum's, which the merge's), intro, batch-3 section (a proposal of this
  merge [I]; the phrase "read from the ids" removed; the rp-int `REQUIRED` line and the bound-driver lines made
  conditional on the order), Step 1, 6, R and 7 notes, "Do not touch"; D 3.7 intro; D 8 still open 9 (new).
- D17 (B's uses; row 11). Confirmed: D17 lists three uses of B, among them the shared F of a new type with no skill.
  Fixed: D 3.4 sentence after the statistics; D 1 row 11 ("C under 'historical'; C0's text under 'format'").
- D10 (d), (g). Confirmed. Fixed: D 3.7 decisions, (d) with the proof contents and "the readout shows the
  representative's reading ... same requests as <event>", (g) with "no test content, no scores" and "pauses on a
  difference (`read_plan_changed`, R44)"; D 3.7 F R65 / R66 in the spec's words and with the legend of the spec's
  layout example.
- RP7. Confirmed: a fixed 0 would be false after a fallback that read two identical classes (R69). Fixed: D 6.
- D17 (labels). Confirmed. Fixed: D 3.4 labels show `B#1..3` with "Changed by D17: was `C0#1..3`" beside; the later
  "Changed by D17" line no longer points to "the labels above".
- O11. Confirmed. Fixed: D 5 gate bullet ("binary scores only [O11]"); the "Changed by O11" line stays as history.
- RP header, O10. Confirmed: the 17:29 section says the RP decisions "do not touch Steps 1 to 7"; O10 says only that
  the read plan shares `T/reads.py` with the D13 wrap; the one-change rule is R24's. Fixed: D 3.6 (R24 credited), 3.7
  intro, 8 (O10, still open 1 with the two options); IO 6s and rp-int rows, Step 6 note (Step 6 does not take the
  `open_panel` extraction), Step 7 note (the bound-driver lines are a spec placement; Q19 is the one Step 7 change
  the addendum makes), Step R, "Do not touch". Also D 5: the bound driver carries `mount_identity`, the capture and
  T7 in the spec's words (spec section 2 puts T2 in `tests/test_typed_readplan.py`).
- RP1 (E). Confirmed. Fixed: D 3.7 E (zero-call, read-only, consent-gated; consent valid in both roots, R83; the F7
  note on typed-v1 sealed cells; counts and verdicts only, no item id, text, reply or per-item score, R86, R87; the
  R47b error record).
- D17 against R68. Confirmed as a wording conflict. Fixed: D 3.7 F scopes R68 to the typed-v2 readout (spec 1.F);
  D 6 shows D17's comparison as a separate block labelled cross-run and cross-date.
- D13 (alternative). Confirmed. Fixed: D 3.6 ("Considered and not taken now [D13]") and D 7.
- BS (rules). Confirmed: the other rules marked [BS] come from `workflow-A.js` (precedence line 31, HARD RULES lines
  33-40) and the first plan's "Do not touch". Fixed: IO "Rules of every piece" ([BS] on BS's three rules; the rest
  [workflow]; "the coordinator commits" marked [I]); IO header defines [workflow].
- F11 (mark). Confirmed. Fixed: D 3.5 `LIST_SHA256` marked "[F11: verified on dl, zero call]".
- D9, D16, D17 (owner texts). Confirmed. Fixed: D 1 paragraph: (a) the coordinator's reading of 14:2x marked as such;
  (b) option A as the coordinator proposed it and the owner chose it over B, with the owner's request as its motive;
  (c) the 17:5x goal rendered in full in English (no stop while away; the 5x5 data; the authority to fix and partly
  re-test; a full five-bench evaluation after every step; similar up, dissimilar not down, not much below SkillOpt and
  GEPA), with the pointer that D17 leaves the reads unchanged (each 5x5 cell is a fresh reading or a proven alias).
