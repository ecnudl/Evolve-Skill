# typed-v3, chain side: decisions before code (2026-11-14)

Owner's word (2026-11-14, about 21:0x to 21:5x, chat): items are NOT made before evolution ("那岂不就是有种自己有新出了
一个验证集的感觉"); they are made after the train results, an LLM analyses what to make, ratios are preset; multi-round
program repair with execution feedback comes back; skills may start from the archive, but a bench's package is added
only when its step is reached, and after every step all five test panels are measured again; the no-card row is not
read; no confirmation re-read of typed-v2; program repair and item making are built together; both chains run on dl
(the owner's own experiment takes PJ-CL4MIND). "其余都按照你的建议来." Estimated cost told and accepted: about 215M
tokens for both chains.

Why: typed-v2's gains came from cards; its programs were written once and are weak (the ZebraLogic programs gave a
solution on 40 and 45 of 100 practice gate puzzles, right 119/120 and 135/135 when they did); its gates of 40 to 100
real items cannot see a gain of 5 points (six card gains of +3 to +6 refused). Evidence: ledger 2026-11-14 21:27,
BANK-PILOT B25 to B33.

This file fixes WHAT is built. Each piece gets its own spec section here before its code and one review after it.

## T1 Version, roots, what stays

- `VERSION = CONFIGURATION = 'typed-v3'`; evidence labels `typed_v3_real_run` / `typed_v3_smoke`; tree
  `execskill-typed3`, branch `research/typed-skills-v3`; machinery `main-v10` unchanged; run root
  `/data/execskill-<date>-typed-v3` on dl, both chains there; caps G 150M, D 170M (estimate about 100M / 116M).
- Unchanged from typed-v2: benches and order, practice slices (learn 100/34/73/41/20, gate 100/40/100/50/40), models,
  base card `historical` (D17), shared types and member checks on the member's REAL gate slice (D16), R = 3 fresh
  runs per item and arm, tau = max(3 points, 2 SE of the baseline's repeats), card rounds 2, static program screen
  and sandbox, memory lock `unit_shared`, consent and sealing of test reads, the path-word guard.
- Changed: T2 to T11.

## T2 Reads

Schedule `interleaved`, read plan `full`: after step k the frozen state S<k> is read FRESH on all five test panels
(the owner's binding definition of the 5x5). Rows: C (the hand card, before step 1) and S1..S5. The anchor C0 is not
read (owner). No alias, no economy plan. Readout: differences S<k> - C and S<k> - S<k-1>, own-run, same items.

## T3 Step flow (bench b at step k), units under `s<k>/`

1. `diagnose`: the learning base B (the hand card alone) R times on the LEARN slice. Per item 0..R right runs and
   its replies. (typed-v2 ran F once here; the analyst needs to tell a stable failure from noise.)
2. `items-plan`: the analyst (role model) writes the item plan (T4).
3. `items`: the bench's maker or selector produces the items of the plan (T5); each item is in the benchmark's own
   form with a record (class, weakness, side, certificate or source, hash). `items.json` lists them with hashes.
4. `items-check`: B ONCE on the judging-side attack and calibration items. The plan holds when the attack items'
   pass rate is at least 5 points below the calibration items'. If not: `items-plan-2` (the analyst sees the two
   rates per weakness, counts only), replacement attack items, `items-check-2`. Whatever the second check says, the
   step goes on and the record keeps both rates. These runs are used for nothing else.
5. `items.json` is sealed (write-once, hash in every later record of the step). From here the step's GATE items of
   bench b are J = R + A + G + K: the real gate slice R, then the judging-side attack A, guard G and calibration K
   items. Members of a shared type keep their real gate slice.
6. `noise` (B x R on J), `typing`, `outcomes` (F once on the learn slice and on the SHOWN made items; F x R on J
   unless it is B's arm), `cards`, `programs`, `finalize`: typed-v2's units on J, with the rules of T7 and the
   program learning of T8 and T9.

## T4 The analyst's plan

Input: the bench's task description; per learn item its public text (bounded), the R outcomes of B and one wrong
reply (bounded); the experience log (for every earlier step and this chain: what was tried, accepted or refused,
with counts, no item text of other benches); the maker's capability sheet of T5 (what can be asked for). Output, a
JSON object: `weaknesses` [{id, description, evidence: [learn item ids], signature: how a wrong reply looks, spec:
maker-specific}], `guards` [{description, spec}], `note`. Fixed code keeps a weakness only when at least 3 of its
evidence items exist and B failed each of them in at least 2 of R runs. Fewer than 3 kept weaknesses: the attack
share falls to 20 % of the made judging items and the rest goes to calibration (no weakness is invented). The gate
slice never reaches the analyst; the judging-side made items never reach a writer.

## T5 Makers and selectors (tools exist before evolution, items do not)

Judging-side made items per step (attack / guard / calibration) and shown items (attack / guard):

| bench | A / G / K | shown | where items come from |
|---|---|---|---|
| SearchQA | 60 / 45 / 45 | 27 / 13 | SELECTED from the 400 unused real practice items by a selector call per batch |
| OfficeQA | 32 / 24 / 24 | 16 / 8 | made on the practice documents, answers by fixed code (use depends on B34) |
| ZebraLogic | 80 / 60 / 60 | 40 / 20 | `bank/zebra` generator with a spec: sizes, clue-kind emphasis, search needed |
| SpreadsheetBench | 24 / 18 / 18 | 13 / 7 | made on practice workbooks, answers by two agreeing programs |
| ALFWorld | 16 / 12 / 12 | 8 / 4 | SELECTED from the 3,454 unused practice games by task type |

- Ratio 4 : 3 : 3 on the judging side (owner approved). Attack: the plan's weaknesses in turn. Guard: what B solved
  in all R runs (same kinds, sizes or task types). Calibration: drawn like the real gate slice (ZebraLogic: the
  gate's own size shares), no targeting.
- An answer is certified by execution only: the ZebraLogic certificate, OfficeQA's fixed-code derivation, two
  agreeing sheet programs; a selected item is a real item with its reference. No solver's success admits an item
  (B30).
- Sides by family: a made item's family is its document, workbook or seed; shown and judging sides share no family;
  OfficeQA and sheet follow the practice split (learn-side documents and workbooks feed the shown side, gate-side
  ones the judging side).
- OfficeQA follows the audit of B34: 甲 as in the table; 乙: guard items only (0 / 40 / 40 of twins and plain
  questions, E = R); 丙: no made items (J = R, as typed-v2).
- Tokens of making are charged to the chain's ledger through its role client.

## T6 What a writer sees

Card writer and engineer: the learn-slice examples as in typed-v2, and the SHOWN made items with F's attempt on each
(attack items first). Program repair (T8) also uses the shown made items as execution cases. No judging-side item,
no gate-slice item and no test item reaches a writer.

## T7 Decisions (owner's principle of 2026-11-02: gain where it acts, no harm on the whole batch)

Let E = R + A (where improvement is sought) and J the whole gate list. All statistics as typed-v2
(`gatestats.repeat_statistics`, R = 3, tau from the baseline's own repeats on the same items).

- Card: accepted iff the gain on E reaches tau_E (tau of the baseline's repeats ON E), more items of E got better
  than worse, and `no_regress` holds on J (gain on J >= -tau_J).
- Program: as typed-v2 on J: it fired on at least one item of J, the gain on the fired items reaches the
  whole-list tau, more fired items better than worse, `no_regress` on J.
- Typing no-harm and member checks: unchanged rules; the home bench's list is J, a member's is its real slice.
- Screen before the paid three runs: every candidate ONCE on A + G; it goes on to the full gate iff its pass count
  there is not below the baseline's mean pass count there (programs: and it fired on at least one of them). The
  screen's runs are never reused in the full gate (a candidate that passed by luck would carry that luck).
- Reported with every decision, deciding nothing: the gain on R alone, on A, G and K, and the made-minus-real
  parity of B on K (the per-step instrument check).

## T8 Program learning: repair rounds with execution feedback

1. Engineer proposals and static screen as typed-v2 (up to 3 proposals, one fix call for a screen failure).
2. PROBE, no model call: each screened proposal is run by the solver shell on a probe call (the request is built
   and recorded, no request is sent) on every learn item and shown made item: did it fire, did it put a note into
   the request (characters), which faults (timeouts, exceptions, caps). ALFWorld: the first step only.
3. Free repair rounds, up to 3 per proposal: the engineer receives its source and the coverage report (counts by
   item group, and up to 5 items per failure class with their public text); the revision is screened and probed;
   the version with the most noted items stays (ties: fewer faults, then the earlier one). A round that does not
   improve ends the repair.
4. One paid feedback round: the best version once on the learn slice and the shown made items; fixed / broken
   against F's attempts; when it broke at least as many as it fixed, one more repair with the broken items shown.
5. Screen and gate of T7. At most 2 engineer candidates reach the gate per step (as typed-v2).

## T9 Archive packages

Sealed in the manifest at prepare with the sha256 of every record (`skill-archive/manifest.json`): chain G
ZebraLogic `main-v6-G-s3-p-zebralogic-3-5`, chain D ZebraLogic `main-v6-D-s3-p-zebralogic-3-3`, both chains
ALFWorld `alfworld-v11-accepted` (three procedures). Rule: only packages an earlier chain accepted at its own
practice gate; never a hand-picked one, never `oracle-reference`. At the bench's step the package is candidate 0 of
`programs`: typed screen (a refusal is recorded, nothing is fixed), probe, screen run, full gate under T7. Accepted:
it joins the library with origin `archive`, and the engineer's proposals of T8 start from it as their parent and
are judged against the incumbent that holds it. The readout separates the archive's gate result from what the step
learned after it; the write-up states that the archive's test readings were known when this rule was set.

## T10 Costs (estimate, told to the owner)

Learning about 60M per chain (typed-v2: 33M to 35M), reads 6 rows x 5 panels about 38M (G) and 53M (D); item
making about 1.5M per chain. Total about 215M.

## T11 Build order (one spec section, tests, one review each)

P1 program learning (T8, T9) in `chain.programs`; P2 the item stage (T3 steps 1 to 5, T4, T5) with its Services
hooks and the bank makers as tools; P3 the gate on J (T6, T7, screen) and the read rows (T2); then a practice-only
smoke of both chains on dl, then the real run. Frozen runs and their roots are not touched; typed-v2's golden
tests keep passing through the version switch.

## Build decisions of 2026-11-15 night (made by the assistant while the owner slept; to be reported)

- B1 Build split (T11 refined): P1 program learning; P2a the item tools as NEW files only (`typed/items/`: quotas,
  counts, records, the analyst's request and plan check, the experience log, the ZebraLogic maker, the SearchQA and
  ALFWorld selectors) built in a separate worktree in parallel with P1; P3a the arithmetic of T7 in `gatestats.py`
  (pure) in another worktree; then P2b (the item stage wired into the chain) and P3b (the rules on J, the screen
  unit, the reads, the preset) on the merged tree. One Codex review per piece (P2a and P3a count as pieces).
- B2 Shown side when fewer than 3 weaknesses are kept: T4 speaks of judging items only; the shown side follows the
  same rule (shown attack = floor(20 % of the shown total), the rest shown guard), so writers do not see more attack
  examples than there are kept weaknesses to justify them.
- B3 OfficeQA: no made items (B36 reading 丙). SpreadsheetBench: no made items in this version, because no solver
  has run on made sheet items and the OfficeQA experience (made items 28 to 41 points easier, B25) shows that an
  unchecked maker must not judge; building the sheet maker and an instrument check for it is left to a later
  version. Sheet and OfficeQA steps run with J = R; their items blocks record the reasons; the readout states it.
- B5 Item files are named by slot (`items/<slot>.json`), not by item id: pool ids can contain the word "test",
  ':' or '/'. The replacement round `items-2` replaces attack items only, at most as many per side as round 1 made,
  split in turn over plan 2's kept weaknesses (fewer than 3 kept: min(round 1's count, the 20 % rule's count); none
  kept: nothing is replaced and the record says so); round 1's guard and calibration items stay.
- B6 Answers to the reviews of P2b and P3r that are decisions, not code (2026-11-15 03:5x). (a) The SearchQA selector
  reads the public text of every candidate, including those that become judging items, because it must match them to
  the plan's weaknesses (P2 brief D); its reply holds labels only, its records are never shown to a writer, and no
  writer sees a judging item: the gate stays independent of the writers. (b) Writers see the reference answer of a
  FAILED learn or shown item, as typed-v2's writers saw failed learn items' references: learn and shown items are
  training material; the reference of a judging or gate item never reaches a writer, the analyst or the selector.
  (c) prepare seals the new options explicitly even at their defaults (P1: program_learning, archive; P2b: item_stage,
  item_quotas); a typed-v3 manifest differs from typed-v2's anyway by its version label, and an old manifest without the
  fields still reads as the defaults. (d) A solver reply saved before its cell was written is replayed, not re-sent,
  on resume, for every solver cell (gate, noise, outcomes, diagnose, items-check, learn, screen and read cells), under a
  sealed option that the typed-v3 preset turns on; typed-v2 resume behaviour stays the default. One mechanism, in the
  cell machinery, beside P1's replay of role-call receipts.
- B4 The screen of T7 is a coarse filter by design (P3a's simulation: a candidate without effect passes about half
  the time; a real +5-point card is screened out about 14 % of the time on 140 screen items, 26 % on 40). A screen
  refusal is never reported as evidence of no effect.

## Decision of 2026-11-15 afternoon (made by the assistant while the owner was away; to be reported)

- B7 A provider's content-filter refusal of a solver request is a model-side outcome. The real run
  `/data/execskill-20261115-typed-v3` (launched 10:10) paused chain G at 13:49 in `s1/items-check`: 1 of 105 runs
  (B on SearchQA practice item `ea88242882794a9ea5705de2e68a3782`, a clue whose topic triggered the provider's
  content filter) was answered by GLM-5.3 with HTTP 400 and error code 1301, its content filter
  ("input or generated content may be unsafe or sensitive"), 0 tokens; the owner-delegated recovery re-ran that one
  cell at 15:18 and it was refused again (deterministic). The code counted it as an infrastructure unknown, so every
  arm of the step would pause on that item. Rule from now on: (error_type `http_400`, `receipt_rest.error_code`
  `1301`) is model-side, as `finish_sensitive` / `finish_content_filter` already are (addendum O1: final, scored 0,
  never re-run, never a pause), in every solver cell (gate, noise, outcomes, diagnose, items-check, screen, learn and
  read cells) through `units.infrastructure_unknown_of`. The code is read from `receipt_rest`, which the resume replay
  'on' keeps, so typed-v2's records and the default 'off' are unchanged. Role calls are unchanged (none was refused;
  writers never see an unknown outcome as an example, so a refused shown item never reaches them). An item refused
  for every arm scores 0 in every arm: it adds no difference and dilutes a gain by 1 / n. The SearchQA test panel
  had no refusal in chain G's C read (400 of 400 cells, 0 unknown).
  Consequence: chain G's run under the old code cannot go on (a frozen run is never patched): it stays paused in its
  root as an interrupted run (its C reads sealed, never opened); chain G is started again from the beginning in a new
  root `/data/execskill-20261115b-typed-v3` on a new snapshot (`-20261115b-`: one letter after the date names a
  further root of the same day, `prepare.ROOT_NAME`). Chain D keeps running unchanged in the first root on the first
  snapshot (deepseek-v4-flash never answers with GLM's codes, so the rule is inert there); the two chains then differ
  by this rule only, and the readout says so.

  B7b (same afternoon; Codex's review of f1950b9 found B7 incomplete): two gaps closed. (1) A refusal is final under
  the resume replay too: in a solver cell (learning and read cells) a saved refusal answers its occurrence wherever it
  stands in the calls file -- also as the file's last record (a refusal saved right before a kill, which was sent
  again: a new reply could have replaced the final zero, a transport failure on the resend would have made it an
  infrastructure unknown) and in a cell re-run after another failure (`units.ReplayRule`'s `final_refusals`, set only
  by `units.ReplayingRecorder`; a delivered receipt of the same occurrence still answers first). The role-call replay
  and the default rule are unchanged: a role call's refused receipt at the end of its file is sent again. (2) A
  refused item's text enters no role sample that shows public text without reading an outcome, since a role request
  carrying it may be refused itself (a refused role call counts as an infrastructure failure: the analyst and the
  describer would pause after their retry, the engineer's proposal would get no reply): the
  analyst's learn row keeps the item's id and outcomes with `public_text` null and no wrong reply (decided from its
  diagnose cells); the engineer's hook view is the first learn item not refused; the describer's examples skip it; a
  repair request's coverage block counts it in its class without listing it. Every count and denominator keeps it.
  The refused items of a step are read from the step's cell records (`chain._Run.refused_ids`: a cell with a refused
  send or selection send, `units.cell_refused`), not gathered from the rows a process visited, because a resumed step
  does not re-enter every unit (a sealed `items.json` skips diagnose and the checks; typing and stored decisions load
  their arms from disk): so a role request rebuilt on resume is the one the interrupted pass built and its saved
  receipt is replayed. Unchanged on purpose: the writers' examples and the feedback round's learn report, which show
  only items whose own cells were answered (an item refused under one arm and answered under another can still
  appear there). Without a refusal every request and record is as before (typed-v2's golden requests and cells and
  every typed-v3 test unchanged; three fake chains under the typed-v3 options, run on f1950b9 and on this tree, gave
  the same records, calls files, requests and ledger counts), so B7b is inert for chain D and under 'off'. Tests: 15
  new in `tests/test_typed3_provider_filter.py`, the read path through the real `reads` included.

  B7c (Codex's second look at f254af7: earlier findings 1 and 3 fixed, 2 not fixed in one corner): when the provider
  refused EVERY learn item of the step, the hook view fell back to the refused `learn[0]`. Now the fallback is the first
  item of the bench's practice source that is neither refused nor a real gate item of the step nor (under 'planned') a
  judging-side item; `learn[0]` only if none exists. One new test (all learn items refused: the hook view is the first
  panel item of the fake source, never a refused or gate item); it fails with the old fallback.

## Open at this time

- ~~B34 (the audit) decides OfficeQA's row of T5.~~ Decided 2026-11-15 02:0x by its registered rule: reading 丙
  (BANK-PILOT B36: 78 of 100 admitted items correct in both passes, the auditor rule held). OfficeQA gets NO made
  items in typed-v3: its steps run with J = R, as typed-v2; its maker entry returns no items and records the reason.
- SpreadsheetBench made items (T5 row) have no instrument check (no solver has run on the pilot's 113 items). If
  their maker is not built and checked before the launch, sheet steps also run with J = R; the readout must say so.
- Facts to verify when each piece is coded (not design choices): how a read embeds panel items for routing (made
  items need the same), the typed form of an archived procedure record, the sheet scorer's file layout for a made
  task inside a chain cell.
