# typed-v2: decisions D9 to D12 (owner decision of 2026-11-12; replaces section 3 of DECISIONS.md)

Written by the coordinator on 2026-11-12 after the owner's message of about 14:2x, verbatim:
"对于之前做的重跑和一些修改的决定，请你首先暂停然后按照那三个决定修复，修复之后在保证效果的同时按照最短时间最少消耗花销的方式开始重跑，你明白我的意思吗".
Reading: (1) stop typed-v1 now; (2) build the three approved changes (D1 to D8 stand unchanged); (3) run typed-v2 in
the cheapest and fastest way that keeps the result valid. This is the owner decision that F5 and section 3 of
DECISIONS.md were waiting for. It covers the typed-v2 run only. `T/` = `skillopt/execskill/typed/`.

## Facts added

- **F7.** typed-v1 was stopped on the owner's order on 2026-11-12 by SIGINT to each chain's main process (15:13:33).
  D exited 15:14:05 in unit `s5/program-1-gate` (83 units done, 54,957,897 tokens charged); G exited 15:15:21 in unit
  `s4/noise` (57 units done, 33,924,247 tokens charged). Exit code 130, no pause record, no container left, nothing
  deleted. Root `/data/execskill-20261110-typed-v1` is frozen as it stands; it is not resumed unless the owner asks.
  Finished read events there: C0 and C on five panels for both chains (11/11), S1..S3 for G, S1..S4 for D. All of
  its sealed read contents are still unopened and stay unopened until the typed-v2 code and run plan are frozen.
- **F8 (from spec/schedule-lock.md S4, S7; to be re-verified by the read-plan section).** A read unit's name depends
  only on (event, bench); a cell tag is sha256(bench, item id, arm); the recorded request hash is
  sha256(system NUL user); system and user come from the mount record, a function of (bench, item, arm, typemap,
  library, vector, view); read cells carry no step. The per-step library and typemap files are write-once.

## Decisions

**D9. Run mode of the typed-v2 real run.** `schedule = learn_first` (D8 a) and a new sealed manifest field
`read_plan = economy`. `read_plan = full` (every event reads five panels fresh, the typed-v1 behaviour) stays the
default of the code and the only value allowed with `schedule = interleaved`; `prepare` refuses `economy` without
`learn_first`. Learning is completely fresh from step 1 under the typed-v2 rules: no practice-side cell, record or
library entry of typed-v1 is reused (considered and rejected: about 3M tokens saved against a cross-version import
inside the learning path).

**D10. The economy read plan: every distinct set of requests is read fresh exactly once.** Pre-registered rule:
  (a) The unit of reading stays the whole panel of one bench for one event, as in typed-v1. No item-level mixing of
      readings inside a panel.
  (b) After the last freeze (s5) and before any read call, a zero-call planning pass computes, inside the
      consent-gated read path (the only place where test items may be opened), for every bench and every event
      E in (C0, C, S1, S2, S3, S4, S5) the per-item MOUNT IDENTITY under E's arm and E's frozen library and typemap:
      a hash over everything that determines the requests that would be sent for that item (base blocks of the arm,
      the item view, the item's type under the event's typemap, the ordered list of eligible library entries with
      their content hashes, the selection request if the mount would send one, mounted program packages, sandbox /
      environment configuration that the frozen state can change). For arms that mount nothing from the library
      (C0, C) the full request hash sha256(system NUL user) is computed too. Two events are in the same CLASS for a
      bench iff the mount identities of ALL items of the panel are equal.
  (c) Each class is read exactly once, with fresh calls, by the read unit of the LATEST event in the class (order
      C0, C, S1..S5). Consequences: the final library (S5) is always read fresh on all five panels; a panel that a
      step changed gets a fresh reading of the state before the change and one of the state after it, both taken in
      the same read phase (same days, same provider state), so no claimed effect rests on a cross-date comparison.
  (d) Every other (event, bench) of a class gets an ALIAS record that names the representative unit and stores the
      proof (both identity lists' hashes, item count). An alias is never a result of its own; the readout shows the
      representative's reading for it and marks it "same requests as <event>". A difference between two events of
      one class is zero by construction and is shown as such (a dash), never as a measured 0.0.
  (e) Order of the fresh units in the read phase: S5 on the five panels first, then the remaining representatives
      in descending event order. Order never enters a request or an identity (D8).
  (f) Fallback is always "read fresh": a missing, unreadable or unequal identity, a failed self-check of the plan
      file, or any doubt makes that (event, bench) its own class. Nothing is ever skipped without a stored proof.
  (g) The plan (`read-plan.json` per chain: per bench the class table, representative, identity-list hashes; hashes
      and counts only, no test content, no scores) is written once, self-hashed, bound into the run state; resume
      re-verifies it and pauses on a difference. The planning pass may be repeated zero-call and must reproduce the
      stored file byte for byte (this is the zero-call replay the owner's 10/24 rule asks for).
  (h) Everything the planning pass opens is handled as a read unit handles it: owner consent first, panel registry
      and SpreadsheetBench test qualification created by the same path as in typed-v1, no test content written
      outside the sealed unit directories, nothing but hashes and counts in open files or logs.

**D11. The reference row C and the typed-v1 replicate of C0: carried over only with a proof, outside the run loop.**
A typed-owned command (new module in `T/`, CLI subcommand of `scripts/run_typed.py`; zero calls) compares, for
events C0 and C, each bench and each chain, the per-item full request hashes stored by the typed-v2 planning pass
with the request hashes typed-v1 recorded for its finished unit of the same chain, event and bench, and checks:
same item set and order-independent equality for all items, the typed-v1 unit complete (all cells present, its own
record hash valid), same solver settings in both manifests (model, provider settings, thinking setting, token
limits), same machinery list hash, same panel registry hash. If everything holds it copies that typed-v1 unit
directory unchanged into the typed-v2 root under `<chain>/carried/typed-v1/<unit>/` (sha256 of every file recorded)
and writes a write-once receipt. Use of a receipt:
  - C class (reference card): a valid receipt present when the read phase reaches the C unit makes C an alias of the
    carried unit, marked "carried from typed-v1, read 2026-11-11"; without a valid receipt C is read fresh.
  - C0 class: ALWAYS read fresh in typed-v2 through its class representative (D10 c). A carried typed-v1 C0 unit is
    only a second, earlier replicate of the same requests (noise and drift reference); it is never the baseline of
    a comparison.
The command prints counts and verdicts only. The typed-v1 root is never written. typed-v1's S1..S4 reads are not
carried anywhere (their states are typed-v1 libraries).

**D12. What is not cut (binding for every section).** Fresh learning for all five steps; the gate rule of D5; the
static screen and sandbox; consent and sealing of test reads; a fresh five-panel reading of the final library; a
fresh same-phase baseline for every panel whose requests changed. Token caps as D6. No statistic or decision reads
a carried or aliased cell as an independent sample.

## Added 2026-11-12 15:4x: lock mode of the real run (facts F9, F10; decisions D13, D14)

- **F9 (measured on dl 2026-11-12 15:29, read-only).** Machine: 7 CPUs, cgroup v1 memory limit 15,032,385,536 bytes,
  no swap, boot 2026-10-14 20:53. Since boot: `memory.failcnt` 0, `oom_kill` 0, no out-of-memory line in the kernel
  log; `memory.max_usage_in_bytes` 14,166,765,568 (includes page cache). In that period main-v6 .. main-v9 and
  cross-v5 ran with the shared environment lock (`v218_lock.environment`): main-v9 alone has 506 (G) and 576 (D)
  lock receipts in `lock-waits.jsonl` (exclusive 367 / 494, shared 139 / 82; longest wait 8,420 s / 15,388 s).
  So the shared mode has run for days on this machine without one memory kill and without the limit ever being hit.
- **F10 (typed-v1 unit timing, from file times only; helper `/data/typed-v1-ops/reuse.py <root> timing`).** Sheet
  cells under the per-cell plain lock: D alone on the machine 27 to 41 s per cell (`s4/outcomes` 91 cells 1.03 h,
  `s4/card-r1` 50 cells 0.38 h, `s4/program-1-gate` 50 cells 0.45 h, test panel C 204 cells 1.85 h); with the other
  chain also on sheet cells a test panel took 3.6 to 6.2 h; G `s4/noise` got 24 cells in 62 min while D ran ALFWorld
  learning units (shared holders starve the exclusive sheet cell). ALFWorld: D `s5/noise` 80 cells 0.66 h. GLM
  ZebraLogic: 200 cells in 0.97 h (`s3/noise`), a 200-item test panel 1.1 to 1.4 h. Sheet and ALFWorld work of both
  chains is the long pole of elapsed time.

**D13. Lock mode of the typed-v2 real run and smoke: `unit_shared`** (schedule-lock.md L2 b: the existing machinery
function `v218_lock.environment`, as main-v6 .. main-v10 used it; two sheet cells of one unit run at once; receipts in
`lock-waits.jsonl`). `per_cell_plain` stays the code default (schedule-lock.md L7); the real-run and smoke manifests
set the sealed lock field to `unit_shared`. This is the zero-cost evidence Q3 of schedule-lock.md asked for (F9, F10).
With it, as Q4 says, the ALFWorld preparation resets of read units are wrapped with `v218_lock.call` in the same
change. The lock mode enters no request, no cell tag and no mount identity; it is recorded in the manifest and in
every carry receipt (typed-v1 read its panels under `per_cell_plain`; a carried cell is marked with its date AND its
lock mode). Guard, ops side only (no run code): a sampler logs cgroup memory use and `failcnt` during smoke and run;
a non-zero `failcnt` or any memory kill is reported and the affected unit is treated as a faulty attempt.
Considered and not taken now: locking only the native operation with model calls outside (`v218_lock.call` /
`workers` / `engine` inside `T/mount.py` `solve`): larger gain, but new call sites and a new memory analysis.

**D14. Both chains run on dl; the second machine is not used for this run.** Estimated gain 2 to 12 h of about 30,
against a setup with environment-parity proof, relay of the typed-v1 carry source, and the standing destroy risk of
that machine. It stays available if the owner wants a faster follow-up.

## Added 2026-11-12 15:5x: coordinator decisions on DESIGN.md section 8, facts F11 to F13, decision D15

- **F11 (machinery lists, zero call, dl).** `sha256sum --quiet -c machinery-main-v10.sha256` inside
  `/data/execskill-code-20261109-main-v10` passes; the snapshot holds 564 `.py` files outside `typed`, no
  `skillopt/execskill/typed`, no symbolic link. The list's own sha256 recomputed there equals the pin
  `3c37fdd90de0e6b51013af7fd4f166f3fa9a1fead5836b335111a4775202599f` (F2 is now verified, no longer inherited).
  The data list `machinery-main-v10-data.sha256` (this directory) was made there from the snapshot: 64 rows, sorted
  with `LC_ALL=C`, sha256 `75ad90d48b644a1dddb43fc5e83edb855418229bd9930eed4e3c6f073b337a48` = `DATA_LIST_SHA256`.
  All 64 files of the local tree equal it (`shasum -a 256 -c`, 0 differences). This closes O2.
- **F12 (token projection, accounting only; helper `/data/typed-v2-ops/capproj.py`, rates from the typed-v1 ledger).**
  Charged tokens per practice cell in typed-v1 (blank arm / with a card): SearchQA 1,340 / 1,800 to 2,150; OfficeQA
  5,200 to 6,300 / 5,400 to 7,300; ZebraLogic 4,700 to 4,900 / 4,900 to 6,200; SpreadsheetBench 1,300 / 1,400 to
  1,850; ALFWorld per episode D 24,800 / 43,500 (about 30 calls per episode, the card rides on every call), G
  13,100 on the test panel. One five-panel read event: G 4.9 to 6.1 M, D 5.8 to 6.8 M. Projection for typed-v2
  (million tokens; "typical" = no-harm shared, half of the second card rounds, 1.3 program gates per step; "full" =
  every unit of the step runs):

  | chain | learning typical | learning full | reads economy | reads all fresh | economy total | worst case x 1.1 | cap |
  |---|---|---|---|---|---|---|---|
  | G | 31.7 | 46.3 | 13.4 to 27.5 | 43.6 | 45 to 74 | 98.9 | 150 |
  | D | 40.3 | 59.2 | 16.4 to 33.7 | 51.0 | 57 to 93 | 121.2 | 170 |

  Per step (typical / full): G 3.3/4.8, 4.6/6.7, 9.0/13.3, 1.8/2.5, 12.9/19.0; D 3.3/4.8, 3.8/5.5, 7.9/11.7,
  1.6/2.3, 23.7/35.0. The ALFWorld step is 40 to 60 per cent of the learning cost. Both chains together: economy
  plan about 102 to 167 M (most likely 120 to 130 M), every cell read fresh about 167 to 200 M. The owner was told
  65 to 85 M on 11/12 15:3x from a rough count made before typed-v1 had reached ALFWorld and without the tripled
  gate arms; the corrected figure is reported to the owner before launch. This closes O3: the caps of D6 stay
  (worst case 66 per cent of G's cap, 71 per cent of D's).
- **F13 (O1 sizing).** Pairs excluded as unknown in typed-v1 gate decisions: G 0; D 1 pair of 50 in each of the two
  SpreadsheetBench program gates of step 4. The change of O1 moves at most one item in a slice.

Decisions on the open points of DESIGN.md section 8 (coordinator, binding for the implementation):

- **O1.** Confirmed: a cell whose final outcome is a model-side unknown (`unknown`, `unknown_artifact`) is scored 0,
  never re-run, and counted in `unknown_final`; infrastructure and configuration unknowns are re-run by the existing
  rule and pause the chain if they stay unknown. The same holds for both arms of every comparison.
- **O4.** The draw keys keep their typed-v1 values (`SEED`, `SLICE_TAG`, `EXAMPLE_TAG`): the same practice items as
  typed-v1, and the carry of the reference row C stays possible. This is the one stated exception to D6; the
  manifest records them as `draw_keys`.
- **O5.** D5's sharing stays. After an accepted card the program baseline is the accepted card's three gate runs;
  the decision record says so (`baseline_selected: true`) and reports must name it when a program is accepted on
  such a baseline.
- **O6.** An item counts as fired when the program fired in at least one of its R cells; the record keeps the fired
  count per item (0..R).
- **O7.** The typed-side `no_hook_function` check is accepted (it runs before the frozen `policy.check`, whose call
  is unchanged).
- **O8.** The implementer words the twelve remaining `PROBLEM_SENTENCES` in the form of the three given ones (counts
  and key names only, no reply text), pinned; the Codex review covers them.
- **O9.** Operations rule, no code: the note of every typed-v2 consent names the run root and states the read plan.
- **O10.** The read plan (D9 to D12) is integrated in a second pass after `spec/read-plan.md` and its critics; it
  shares `T/reads.py` with the reset wrap of D13 and is implemented after step 6 of IMPLEMENTATION-ORDER.md.
- **Program gate on the items where the program fired.** The rule stays the typed-v1 rule with the repeat
  statistics of D5: the gain on the fired items is compared with the tau of the whole slice, `better_f > worse_f`,
  and `no_regress` over all items. A stricter threshold for small fired subsets would be a change of the decision
  rule against the owner's gate principle of 11/02 ("gain and no harm, not too defensive") and is not made. Added,
  informational only and never deciding: every program decision record stores `fired_items`, `fired_cells`,
  `se_points_fired = (100 / (R * n_f)) * sqrt(2 * Q_f / (R - 1))` (Q_f over the fired items) and
  `se_points_scaled = se_points * sqrt(n / n_f)`. Reports state for each accepted program how many items it fired
  on and how its gain compares with these two values.

**D15. Width of learning units.** New typed-owned constant `LEARN_WIDTHS = {searchqa: 6, officeqa: 6, zebralogic: 6,
spreadsheetbench: 2, alfworld: 2}`, used by the learning units (`C` `cells`, today `widths=WIDTHS`); `WIDTHS`
(3, 3, 3, 2, 2) keeps serving the read units, where five panels already run side by side. Both are sealed in the
manifest (`widths`, `learn_widths`); the smoke uses the same values. A width enters no request, no cell tag, no
identity and no decision; all arms of one unit run under the same width. Evidence that it is safe: typed-v1's read
phase sent up to 13 requests at once per chain to the same providers for days (five panels, inner widths 3, 3, 3,
2, 2) and ran mounted material in the sandbox at that load; a learning unit sends 6. Effect: GLM answers one
ZebraLogic item in about 52 s, so 200 cells take 0.97 h at width 3 (F10); the typed-v2 ZebraLogic step has up to
2,300 cells, about 10 h at width 3 and about 5 h at width 6. If a provider answers with rate-limit errors the cells
become infrastructure unknowns and are re-run by the existing rule. The widths are sealed values: they are not
changed inside a root; a pause caused by rate limits is resumed with the same values and reported.

## Added 2026-11-12 16:1x: coordinator decisions for the implementation (O11, O12, module placement, build split)

- **O11 (binary scores only).** The gate statistics are built for binary cell scores (x = 1 for a correct cell, else
  0). The last bullet of DESIGN 3.4 "Statistics" (non-binary scores on `Fraction`) and the words "also non-binary at
  1e-9" in DESIGN section 5 are NOT built: no typed bench has a non-binary score, and unused arithmetic in the
  deciding module is a risk without a benefit. `arm_runs` refuses a `correct` value that is neither `True`, `False`
  nor `None`. Records hold JSON integers only; `scores` is always `'binary'`.
- **O12 (per-item records).** `per_item` of a decision record is the list form of DESIGN 4.1, `[[item, S_B, S_K],
  ...]` in the item order of the slice (for binary scores the sum of squares equals the sum, so it is not stored);
  `noise.json` stores `per_item = [[item, S], ...]`. Program decisions add `fired_cells = [[item, count], ...]` for
  the items with a count above 0. Where `spec/gate.md` 3.2 shows a dictionary with squares, this list form holds.
- **Module placement.** The pure repeat statistics live in a new typed-owned module `T/gatestats.py` (labels,
  `arm_runs`, `repeat_statistics`, `calibration`, the three decisions, `recompute`); it imports nothing from the
  frozen machinery and touches no file. In step 5 `T/gates.py` drops its three typed-v1 decision functions and
  re-exports these names, so `gates.recompute` and the other names of DESIGN 3.4 resolve as written.
  `paired_statistics`, `split_pairs` and `noise_threshold` stay in `T/gates.py` for the readout of read events.
- **Build split.** IMPLEMENTATION-ORDER.md orders the steps strictly one after the other. The build keeps that order
  for every file that two steps share, and runs beside it only work on files nobody else edits at that moment: new
  modules with their new test files (`T/machinery.py`, `T/replies.py`, `T/cards.py`, `T/gatestats.py`,
  `T/engineer_prompt.py`) and the split of `_routed_mount` in `T/mount.py`. Each piece writes a report
  `impl/<step id>.md` in this directory. Step ids: 1a literals, `own_root`, manifest fields, test pins; 1m machinery
  guard; 1b `Services` pass, start checks, sealed code identity, learning widths; 2a card module; 2b card
  integration; 3 reply reader; 4a engineer prompt module; 4b writers; 4c chain and smoke; 5s gate statistics; 5m
  mount split; then step 5 wiring, steps 6 and 7 and the read plan.

## Deliverable

`docs/handoff/typed-v2/spec/read-plan.md` (same layout as the other sections: blockers, behaviour, change list,
records and identity, tests, interfaces, risks, NOT DONE), checked by two independent critics, then corrected. It
must also say how the smoke run exercises alias, fresh and carried paths (the typed-v1 smoke root may serve as carry
source if its smoke panels are identical), what the readout tables look like, and how much code it is. It builds on
`spec/schedule-lock.md` Part A (learn_first, frozen receipts) and must not contradict it.

## Added 2026-11-12 17:29: coordinator decisions on the read plan (RP1 to RP11; D11 revised)

Written by the coordinator of session 9b763bee after seven read-only verifiers checked the 48 critic findings of
`spec/read-plan-critic-A.md` / `-B.md` against commit 8375ecb, answered B1-B5 / Q1-Q18 / N1-N10 of `spec/read-plan.md`,
and hunted unanchored for missed request inputs (verdicts: `SkillOpt-scratch/typed-v2-build/rp-verify/ALL-results.json`
on the coordinator's machine; 45 of 48 findings accepted in full or in part). These decisions bind the corrected
`spec/read-plan.md`. They do not touch Steps 1 to 7 of IMPLEMENTATION-ORDER.md. The read plan is still built after Step 6 (O10).

- **RP1. D11 revised: no carry into the run; C is read fresh.** The reference row C is read fresh through its D10 class,
  like every other event. typed-v1's C0 and C readings of 2026-11-11 serve ONLY as an earlier, cross-date replicate
  (noise and drift reference, read under `per_cell_plain`): a separate zero-call, read-only, consent-gated command,
  run after the typed-v2 read phase, matches typed-v1 cells to typed-v2 fresh cells by cell tag and
  `request_sha256[0]` and prints agreement / flip counts, judge-version equality and unmatched counts, never test
  content. It never writes into the typed-v2 run state, never becomes a baseline or a table row, and is not needed by
  the run: it is built after launch. Dropped from the read plan: `T/carry.py`, R58 (receipt use), P9, P10, R61, the
  CB23 / CB26 machinery, the 'carried' table kind and settle marker, carry tests T13-T15 as written. Reason: four of
  four verifiers recommended it independently. Carrying C saves about 9 to 11 M tokens for both chains (7 to 9 per
  cent of the economy total) and 2 to 6 h, but makes the main contrast "learned library versus hand-written card"
  cross-date on 8 of 10 bench-chain cells, so it could support no claim there (D10 c, R68); solver temperature,
  thinking flag, provider route and later ALFWorld turns can be shown equal only by code equality, which is a doubt,
  and doubt means read fresh. 21 of the 48 findings and 3 of the 4 blockers (A4, CB1, CB9) concerned the carry.
  The deviation from D11 is in the safe direction (more fresh reads); the owner is told in plain words.
- **RP2. Solver settings record (CB4 a, B3, Q3).** At chain start typed-v2 writes a write-once, credential-free
  `<chain>/solver-settings.json` (per bench: model asked, provider route NAME, max tokens B, nominal M, thinking /
  reasoning setting, accepted response model ids, read timeout; no URL, no key, no credential path) and binds its
  sha256 in the chain state. Provenance only; it enters no request, identity or decision.
- **RP3. First-request hashes (A12, Q5, Q6).** Exact first-request hashes (zero-call capture through the real
  `mount.mount`) are MANDATORY for every item without offered programs on SearchQA, OfficeQA, ZebraLogic and
  SpreadsheetBench, for every event; R29 requires equal first-request list hashes wherever both are non-null. No
  ALFWorld capture (option 1 a). Infrastructure unknowns inside a complete representative: the alias stands and the
  representative's unknown / infrastructure / configuration counts are stored in the alias record and shown beside
  every member (option 2 a).
- **RP4. Max-based metrics (A13, CB13).** `forgetting` and `forgetting_after_home`: if an earlier event shares the
  final event's class, print the measured maximum over the other classes when it is above 0, else `-` with the count
  of by-construction terms; without such events, the signed measured maximum (option b').
- **RP5. Same phase (CB19).** Option B with a bound of 24 h: a contrast between two fresh units is same-phase iff
  the returned model-id sets of the two units are equal and no recovery between them splits. A recovery does not
  split iff its pause lasted at most 24 h AND its recovery record carries `same_phase: true`, written before resume
  and blind to results, stating that no code, configuration, provider route or credential changed; a missing field
  splits. 24 h instead of the suggested 6 h: the read phase itself spans most of a day (K-C) and an overnight pause on
  an unattended machine must not void it. A split contrast is a reference only (no se, interval or counts).
- **RP6. No standard stop after the plan (CB31, CB21, X3, Q10).** The real run does not stop after the plan. Right
  after the plan is bound and before the first alias settles, the chain replays the planning pass zero-call in a
  fresh interpreter subprocess from the stored sealed inputs (A5) and requires byte equality; a difference pauses
  `read_plan_changed`. `--stop-after-plan` exists for `run` and `smoke` (default off); the smoke uses it once (stop
  and resume between plan and reads) and kills and resumes once inside a fresh read unit. Reason: an automatic replay
  needs nobody awake at an unknown hour, and with RP1 there is no carry to run during a stop.
- **RP7. Replicates (Q7, vQ-X1).** No in-run replicate. The readout prints `in-run replicates: 0` beside every
  contrast and shows the practice-side gate noise beside the read tables. A same-phase ZebraLogic replicate (about
  1.0 to 1.2 M tokens per chain) is NOT built; it is mentioned to the owner as an option only.
- **RP8. Type id (B5, Q1, X-B5).** The identity hashes what the type selects (card text, selection request, offered
  program records), never the type id; the id is stored beside it un-hashed. This is the reading of D10 (b).
- **RP9. One routing path (A1, H1).** No third mount implementation: the read identity is built on the planned
  `mount.mount_identity` / `_route` split of Step 5 plus `public_sha256`, `view_sha256`, the selection-request hash
  (capture selector through the real `mount.mount`) and the ordered record hashes of the offered programs. Any
  exception of the shared function makes that (event, bench) a fallback class with a fixed reason code.
- **RP10. Post-read mismatch (Q8).** Fallback without pause, and it voids EVERY alias of that bench, settled or not;
  those pairs are read fresh (bounded by the `full` plan); recorded in state and reported as a defect signal.
- **RP11. Pass failure (X1, A9, CB22, N4).** The pass turns only its own detected inconsistencies into
  `read_plan_failed`; every Pause or stop raised by code it calls propagates unchanged. The first recovery of
  `read_plan_failed` re-runs the pass; a second failure with the same reason code voids the plan and all 35 pairs of
  the chain are read fresh in the economy order.
- All other verifier verdicts (accept, partial, refute, with their corrections) are adopted as written, except
  corrections that exist only for the dropped carry path (RP1); corrections about sealing (A11), completeness (B1)
  and judge-version equality (A3) apply to the post-read replicate command instead.

## Added 2026-11-12 17:45: owner decision D16, shared-type learning and gating

Owner, 2026-11-12 about 17:4x, asked: "我觉得这次优化是否可以做一些泛化性的提升，就是针对在一个bench上学习，在其他bench上关联的bench提升，不相关的也不下降这种性能的优化".
The coordinator proposed option A ("这次加上'同题型多任务一起写、一起判'这一处，启动推迟 2 到 4 小时") against B (no change,
generalization in a later version). Owner, verbatim: "选A".

- **F14 ([V] at 8375ecb).** A type has one active card; an accepted card retires the previous one for every source of
  the type (`C.apply_card` -> `library.retire_card`, `typemap.set_card`). The writer's examples and the gate use the
  current bench's learn and gate slices only (`C.cards`, `C.card_decision`, `C.programs`, `C.program_decision`). So a
  later bench's accepted card or program changes the requests of an earlier bench of the same type with no check on
  that bench. Benches of other types get byte-identical requests (no change, hence no drop and no gain, by construction).

**D16. Shared types: write for every member, gate on every member.** At step k with current bench b and home type T
(after typing), the OTHER MEMBERS M are the earlier benches b' with a source in T. When M is not empty:
  (a) Writers. The card writer (both rounds) and the program engineer also see examples of every b' in M: the current
      mount F run once on b''s LEARN slice (unit `s<k>/member-<b'>-outcomes`; after an accepted card, the engineer's
      member examples come from `s<k>/member-<b'>-outcomes-card`, as the current bench's do), chosen and rendered by the
      same rule as the current bench's examples, at most as many, in a block labelled with its source. The prompt names
      the member sources and states rule (b). The current bench's part of the request is unchanged; no gate item of any
      bench reaches a writer; D2 length rules unchanged. A revision round's result summary adds the member check as
      counts and points only.
  (b) Gate. A candidate (card round or program) is accepted iff the D5 home rule holds on b's gate slice (unchanged)
      AND for every b' in M `no_regress(D_b')` holds on b''s gate slice: R = 3 runs per item and arm; member baseline =
      the current mount F on b' items (after an accepted card: that card's member runs, as O5); tau from that
      comparison's baseline repeats (D5); O1 applies. Reason on failure: `member_harm` (naming the bench). The member
      comparison runs only for a candidate that passed the home rule. Units `s<k>/member-<b'>-base` (F#1..3),
      `s<k>/card-r<j>-member-<b'>` (cand_card#1..3), `s<k>/program-<i>-member-<b'>` (cand_program#1..3); D5 arm sharing
      (identities, plan.json) and the per-(unit, tag) rerun rule apply to them.
  (c) Records and reports. Every decision record of a shared type stores per member: items, D, better, worse, tied,
      gain_points, se_points, tau_points, no_regress, units, labels, baseline_selected; `gates.recompute` reproduces the
      member verdicts. Readout and reports show for each accepted skill its home gain and every member gain ("related
      gain": informational, it decides nothing beyond no_regress).
  (d) Scope. A type with one bench changes nothing: no extra unit, cell or request; every request equals the D5
      behaviour byte for byte (golden test). The typing no-harm merge check is unchanged. Reads (D9, D10, D12, RP1 to
      RP11) are unchanged: a member panel whose requests change is read fresh before and after by the economy plan.
  (e) Cost [I]. Only when a later bench joins an earlier bench's type; in this bench order only OfficeQA can join
      SearchQA's type (step 2). Per chain about 1.5 to 4 M tokens (member outcomes about 0.3 M each, member baseline
      about 0.6 M, about 0.6 M per candidate that passes the home rule); 0 if OfficeQA opens its own type. D6 caps
      unchanged.
  (f) Build. New step id 5x in the second batch, right after the Step 5 wiring (5w): `C`, `W`, `T/engineer_prompt.py`,
      `T/gatestats.py` (member verdicts, recompute), `T/readout.py`, tests. The batch-2 reviewers cover it.

## Added 2026-11-12 17:51: decision D17, the learning starts from the historical card C (coordinator, under the owner's goal)

Owner, 2026-11-12 about 17:5x, standing goal for the night (verbatim): "我可能大约半小时后会离开，然后明天的十点钟左右回来，这期间请你不要停止工作，
我们的核心目的是得到我们的方法的完整的5x5主实验的数据，这期间如果有问题的话你有权修复并且部分重测，我希望获得一个泛化性优秀的一个测评表，也就是五个bench在
每一步（每个bench）进化完之后在五个bench上全量评测，然后在相似的bench上能够提升效果，不相似的bench上效果不会倒退，并且数值上至少不能比skillopt和gepa这种低很多".

- **F15 (opened historical readouts only; no typed-v1 or typed-v2 test read was opened).** On these five test panels
  (`SkillOpt/docs/handoff/textskill5x5-v1-readout-20261108/README.md`) the historical card C beats blank B by, G:
  SearchQA +11.3, OfficeQA +16.9, ZebraLogic +3.5, sheet +4.9, ALFWorld +1.5; D: +16.8, +13.4, -3.5, -2.9, +20.1.
  SkillOpt and GEPA, learned from an empty skill, end near C (chain-end five-bench mean minus C: SkillOpt G -1.1,
  GEPA G -1.3, GEPA D +1.1; SkillOpt D -16.3 from a global output-format conflict). typed-v1 starts from C0 (the
  format lines of C only; a mount without a learned card is C0, `T/mount.py` `system_card`) and its accepted SearchQA
  cards gained +4.0 / +5.0 points on practice over C0. `v222_cards.historical_text(b)` is the whole card C and
  `format_text(b)` the format lines of it (they partition C's lines); for ZebraLogic both are the same text.
- **D17. Base card = C.** New sealed manifest field `base_card` in ('format', 'historical'); code default 'format'
  (the behaviour without D17, kept for the golden tests); the typed-v2 smoke and real run set 'historical'. With
  'historical', for every bench b, `system_card(b, T)` is `T + CARD_JOIN + historical_text(b)` for a learned text T
  and `historical_text(b)` (= arm C) without one. The LEARNING base arm gets its own label `B` (mount =
  `system_card(b, '')`): it takes the place of C0 in every learning unit (noise `B#1..3`, the no-harm baseline
  `B@noise`, the shared F of a new type with no skill); with 'format' the identity of B equals that of C0, so every
  request is byte-identical to the design without D17 (golden test). Read arms are unchanged: C0 (format lines only:
  the no-skill row), C (historical card: the start of learning), S1..S5. Writers (card writer, engineer, and D16's
  member block) are shown the base card of each bench they write for, labelled as the instruction the solver already
  receives, with the request to add to it and not to repeat or contradict it; length rules (D2) apply to the learned
  text only. Typing, gates (D5, D16), schedule (D8, D9), reads (D10, D12, RP1-RP11) are otherwise unchanged; a bench
  whose type learns nothing then reads exactly C (an alias of C's class under D10).
- **Reason.** The owner's goal asks that the table not fall far below SkillOpt and GEPA, which end near C; starting
  from C0, typed must first re-learn what C already gives (11 to 20 points on three bench-chain pairs) and typed-v1's
  cards recovered about 5. Starting from C makes every learned skill an increment over the hand card, which is also
  the project's open research question (learning versus a reasonable instruction). Reporting: typed-v2 rows and the
  v2.24 SkillOpt / GEPA rows are shown against the same C row, stating that typed-v2 starts from C while those
  baselines started from an empty skill, and that the v2.24 rows were read on 2026-11-07/08 (cross-run, cross-date).
- **Cost [I].** C adds about 900 to 2,900 characters to every system message of non-ZebraLogic cells. ALFWorld
  carries it on every call of an episode: its learning cost grows most (D's per-episode cost with a card was 43,500
  against 24,800 blank, F12). Rough total: plus 10 to 20 M tokens per chain; the D6 caps still hold (F12 worst cases
  98.9 / 121.2 M against 150 / 170 M).
- **Build.** Step id 5b in the second batch, BEFORE the Step 5 wiring (5w): `T/mount.py` (`system_card` by base,
  `base_card`), `T/prepare.py` (field, check), `T/__init__.py` (BASE_CARDS, default), `C` (the label B where C0 is used
  on the learning side), `W` and `T/engineer_prompt.py` (the base card block), `T/smoke.py`, tests. 5w then wires D5
  with B, and 5x wires D16 with the base card block.

## Added 2026-11-12 18:38: coordinator answers to read-plan questions Q20 to Q24 (RP12)

The corrected `spec/read-plan.md` (1,326 lines; fix1, two checkers, fix2; no blocker) raised Q19 to Q24. Q19 is retired
by the spec itself (adopted as an interface requirement of the machinery check: the `scripts.*` modules the bound run
imports are covered by Step 7). Answers, binding:
- **Q20** accepted: the smoke-only manifest field `read_plan_probe` forces one fallback class with the real pass code;
  `prepare` refuses it on a real root and with `read_plan = full`.
- **Q21** accepted as the spec words it after fix2 (a replay child that crashes or times out pauses
  `read_plan_changed`, detail `replay_error`; bounded by RP11 / Q24 below).
- **Q22** accepted: a resume whose recomputed solver-settings record differs pauses `solver_settings_changed` before
  any call.
- **Q23 yes (binding for Step 5b, part of D17).** With `base_card = 'historical'`, EVERY learned-side or S-event mount
  that today returns the format block for an item (the unknown-type branch of the routed mount, `T/mount.py`
  `_routed_mount` / `_route` at 8375ecb :200-204, and a typed item whose type has no card) returns
  `system_card(bench, '')`, i.e. the historical card C. Test: unknown and typed-without-card items mount byte-equal
  system text under each base value, equal to arm C's text under 'historical' and to arm C0's under 'format'. Reason:
  D17's promise that a bench whose type learns nothing reads exactly C, and the owner's "dissimilar benches do not
  regress" (an unlearned bench must not drop from C to C0 in S1..S(k-1)).
- **Q24 option A.** A non-stop exception raised by the pass's own code (outside the panel path) counts as
  `read_plan_failed` with code `pass_exception` (class name only); by RP11 the second occurrence voids the plan and all
  35 pairs of the chain are read fresh in the economy order. Panel-path exceptions keep propagating unchanged.

## Added 2026-11-12 19:52: coordinator answers to the read-plan core's spec points (RP13)

The pure core `T/readplan.py` (branch typed-v2-readplan-core, commit 3f7e933; report `impl/rp-core.md`) raised five
points. Binding answers:
- R29 "both fall back" keeps its literal, safe reading: when one event of a group of equal identities has different
  first requests, the whole group is read fresh (it signals an incomplete identity; any doubt means read fresh).
- R44 a: `verify_alias` compares the representative's counts from its mirror (accepted as built).
- T23's reason check of `state.json` applies to the read-plan parts of the state only.
- R81: the recovery outcome names of the module are adopted.
- The constants R1 places in `T/__init__.py` stay defined in `T/readplan.py` and are re-exported by `T/__init__.py`.
- Integration requirement (from the core review, F1): the planning pass must mount every item with exactly the frozen
  library and type map it records (`identities_record(frozen=...)`, `item_components(arm=...)`); a test proves that
  the objects passed to the mount calls are the loaded frozen ones.

## Added 2026-11-12 20:50: coordinator answers to the design-merge open points (RP14)

The merged design (`SkillOpt-scratch/typed-v2-build/design-merge/`, to be copied into this directory after batch 3)
listed points the addendum did not decide. Binding answers:
- **Reset wrap and `open_panel`:** Step 6 (build id 6s) does the `open_panel` extraction of R24 AND the D13 ALFWorld
  reset wrap in one change, so `T/reads.py` is edited once; the read-plan integration uses `open_panel` as built.
- **O7 order corrected to the build:** the typed-side `no_hook_function` check runs AFTER the unchanged frozen
  `policy.check` (source, policy, hooks, structure), as built in step 4b and pinned by its tests. Both are zero-cost
  static checks; the order only decides which failure the fix evidence names first. O7's words "it runs before" are
  replaced by this sentence; the rest of O7 stands.
- **Step 7 last:** the machinery guard completion (build id 7g) runs after the read plan, so its AST scan of `T/`
  covers `T/readplan.py`; 7g also writes the read plan's bound-driver cases.
- **D16 member sentence:** step 5x decides whether it enters the pinned engineer system texts (new `PROMPT_VERSION`) or
  the user payload only; step 7 pins the result either way.
- **Memory (merge check of F9):** by the measured cgroup limit (15,032,385,536 bytes = 14,336 MiB) the worst-case
  ceiling sum of both chains under `unit_shared` (14,848 MiB) is 512 MiB above the limit. D13 stays (it rests on the
  measured history of F9: days of shared-mode runs, `failcnt` 0, no kill), and the ops memory sampler becomes
  MANDATORY for smoke and run: a non-zero `failcnt` or a memory kill is reported and its unit treated as a faulty
  attempt (D13), and two such events in one chain switch that chain to a new root with `per_cell_plain` only after a
  report to the owner.

## Added 2026-11-12 21:32: D16 member scope widened to routed benches (RP15)

Batch-2 review rb-stats-1 (deferred by the fixer as a spec gap): D16's members are the earlier benches with a SOURCE in
the home type T, but routing is per item: a gate item of an earlier bench b' whose source is NOT in T (for example
OfficeQA split into its own type at step 2, or SearchQA beside an OfficeQA type) can still be routed into T when it
lies nearer to a T source within that source's threshold, and a later change of T's skills then changes b''s requests
with no member check. That is the "similar benches do not regress" guarantee of the owner's goal of 2026-11-12 17:5x.
Decision (option a of `impl/fix-b.md`): `members_of(T, step)` returns the earlier benches with a source in T PLUS the
earlier benches with at least one gate item that the step's type map routes into T (zero model calls; the routing of
the stored practice vectors). The decision record lists, per member, whether it is a source member or a routed member
and the number of its gate items routed into T. The member check itself is unchanged (D16 b, the member's whole gate
slice). Benches not yet learned are never members (no future practice data is used). Built by the batch-3 fixer (fix-c)
with tests: a split bench with routed items becomes a member; a bench with none does not; the record shows the counts.
## Added 2026-11-12 21:38: Codex review round 2 of batch 2 (RP16)

Codex (gpt-6-astra, ultra, read-only, 21:32-21:36) reviewed `git diff cdf85b6 eced37a` and reported two majors.
- **Finding 1 accepted and fixed** (branch typed-v2-codex2-fixes): `chain.recompute_decision(record) == record` now
  holds for EVERY stored decision, including a gate-accepted program whose description failed (the gate is recomputed
  from the record with its `gate_verdict`, the fresh verdict goes back into `gate_verdict`, and the stored override is
  carried forward only when the recomputed gate accepted and the stored final decision is a `description_failed`
  rejection; any other override is never reproduced). Tests assert `== record` everywhere.
- **Finding 2 refuted by decision.** The engineer prompt's [import] row now states that a from-import of a banned
  member is rejected (`PROMPT_VERSION = 'typed-engineer-prompt-2'`, batch-2 fixer, coordinator finding coord-1). This
  wording change is BINDING: the old row told the program writer that `from M import name` is allowed, which the
  frozen screen rejects for banned members (verified by step 4a), i.e. it caused exactly the screen losses D3 exists to
  remove. The engineer system texts are typed-v2's own (new in step 4a), not a typed-v1 request; the golden test of
  base 'format' keeps the documented normalisation `undo_coord1` for this one difference and nothing else.

## Added 2026-11-13 11:5x: D14 revised during the real run, chain G moved to the second machine

- **D14 revised (coordinator, on the owner's question of 2026-11-13 11:2x "不是有两台机器吗，没有充分利用？").** From
  11:49 chain G of the real run `/data/execskill-20261113-typed-v2` runs on PJ-CL4MIND; chain D stays on dl. Reason: the
  cross-chain memory lock cost more than D14 assumed (G's exclusive SpreadsheetBench cells waited behind D's ALFWorld
  shared holders; no G send from 11:14 to 11:21). Parity before the move, all by hashes: the 23 pinned data files (the
  five test panels included), the ALFWorld data, the OfficeQA upstream, the practice pools, the solver Python env and
  the sandbox image id were already equal; the two code snapshots, the embedding env, the main-v10 sheet
  qualification and smoke manifests were copied and verified; machinery lists, 715 typed tests (4 skipped) and the
  bound check (564 files, data list 75ad90d4) passed on PJ. G was stopped on dl (SIGINT, then SIGKILL of the process
  group at 11:47:33 inside s4/card-r1, no pending send), its directory, the manifest and shared/ copied (8,990 files,
  equal digest), and resumed with an owner-delegated recovery record (same_phase true). The code, manifest, models and
  data are unchanged; only the machine changed. Consequences: the root-wide shared steps (test panel registry
  `shared/test/<bench>.json`, the SpreadsheetBench test-side qualification) run once per machine; they are zero-call and
  determined by the panel content, and are compared by hash when PJ's G directory is merged back into dl's root before
  the readout (dl's stale G directory is archived first, never resumed). PJ's G directory is copied to
  dl:/data/typed-v2-ops/pj-sync/G every hour (the machine may be destroyed).
