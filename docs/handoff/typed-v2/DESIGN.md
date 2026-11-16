# typed-v2: design (integrated; addendum merged)

> **Integration status (2026-11-13, coordinator):** this file folds the addendum through RP13 (merge of 2026-11-12 ~20:4x, one fidelity check). Later decisions RP14 (open points of this merge: reset wrap in Step 6, O7 order as built, Step 7 last, memory sampler mandatory), RP15 (D16 members include routed benches) and RP16 (Codex round 2: recompute convention, binding [import] wording) and the as-built reports of batch 3 (impl/6s.md, rp-int.md, rp-ro.md, 7g.md, fix-c.md) are in DECISIONS-ADDENDUM-20261112.md, which keeps precedence over this file.


Status: merge of 2026-11-12, evening. Inputs: `DESIGN.md` of 15:40 (sections 1 to 8, decisions D1..D8),
`DECISIONS.md` (D1..D8, F1..F6), `DECISIONS-ADDENDUM-20261112.md` up to its section of 19:52 (facts F7..F15,
decisions D9..D17, coordinator answers O1..O12, the rule on the program gate over fired items, module placement,
build split, read-plan decisions RP1..RP13), the corrected `spec/read-plan.md` (fix2, 1,326 lines) and, for build
facts only, the implementer reports `impl/*.md` and `impl/rp-core.md` (branch typed-v2-readplan-core). Every decision
of the addendum is folded in where it belongs, so a reader no longer needs the addendum to know what is decided.
Precedence is unchanged: addendum coordinator sections > this file > `spec/*.md`. Where this merge and the addendum
disagree, the addendum holds. Nothing in the code tree was edited by this merge.
Marks. [V] = the cited code was opened and read for the first integration (tree of commit 8375ecb); [I] = taken from
a section or inferred, not re-opened. A source id in brackets marks folded text: [D9]..[D17] decisions, [F7]..[F15]
facts, [O1]..[O12] coordinator answers to section 8, [PG] the addendum's rule "program gate on the items where the
program fired", [MP] its module placement, [BS] its build split, [RP1]..[RP13] read-plan decisions, [Q19]..[Q24]
read-plan questions answered in RP12. R<n>, T<n>, S<n>, K-<x> and N<n> are rule, test, smoke, risk and open-check ids
of `spec/read-plan.md`. [impl <id>] marks a build fact from an implementer report: what was built, not a decision.
Where the addendum replaced text, the new text stands and one line "Changed by <id>: <what>" keeps the old meaning
visible. Abbreviations: `T/` = `skillopt/execskill/typed/`, `X/` = `skillopt/execskill/`, `C` = `T/chain.py`, `W` =
`T/writers.py`, `R` = `X/engineer_reader.py`, dl = the Linux machine, n = gate items of a bench, R (in formulas) =
repeats, B (as an arm) = the learning base arm of D17, M = the other member benches of a shared type (D16). Line
numbers are those of the tree as copied from typed-v1 (commit 8375ecb); they move with every build step, so find a
site by its function name.

No BLOCKER: every decision D1..D17 can be met inside `T/`, `scripts/`, `tests/`, `docs/`. The three points the first
integration sent to the coordinator before code (O1..O3) and the other seven are resolved (section 8), except the
order part of O7, which the build does not follow yet (section 8, still open 3).
Changed by D9..D17: the first integration took up only D13 and D14 and described D9..D12 as hooks; all are designed
in now (1, 3.4, 3.6, 3.7, 6, 7).

## 1. Purpose and changes against typed-v1

typed-v1 learned 2 cards and 0 programs in 7 learning steps. Its practice-side records (no test content) show that
most losses were made by the pipeline, not by the model (F6): 9 of 21 cards were rejected for length (2,349 to 3,499
characters; a card of exactly 3,000 was counted as 3,001 because of the final newline) and 4 card rounds were void;
4 of 12 program candidates died at the static screen whose rules the writer was never told; 2 of 4 correct fix
replies were lost by reply reading (`change` instead of `changes`; a placeholder inline source beside a real fenced
program); the gate threshold came from one pair of runs (G ZebraLogic: 31 of 100 items flipped, tau 11.18), and a
card with +11.0 points, 20 items better and 9 worse was rejected by 0.18. typed-v2 removes these losses and changes
nothing else. Same benches, slices, order, models, read arms, sandbox, static screen and consent rules.

Changed by D9..D17: "changes nothing else" held for the three approved changes; the owner's later decisions add
the changes of rows 9 to 15 below (read plan, learning base C, shared types, widths, solver settings, machine).

The owner's later decisions of 2026-11-12 apply to the typed-v2 run only (verbatim Chinese texts in the addendum;
English renderings here). About 14:2x: stop typed-v1, build the three approved changes, then rerun; "in the cheapest
and fastest way that keeps the result valid" is the coordinator's reading of the rerun clause (addendum, "Reading:
(3)"), not the owner's words [D9..D12]. About 17:4x: option A, chosen over B (no change now, generalization in a later
version): write for and gate on every member bench of a shared type in this version (launch 2 to 4 h later),
motivated by the owner's request that learning on one bench help related benches and not lower unrelated ones [D16].
About 17:5x, the owner's standing goal for the night: work does not stop while the owner is away (back at about 10:00
the next day); the core aim is the complete 5x5 main-experiment data of the method; problems found meanwhile may be
fixed and partly re-tested; the evaluation table should show excellent generalization: after every step (every
bench) has evolved, a full evaluation on all five benches, gains on similar benches, no regression on dissimilar
ones, and numbers at least not much lower than SkillOpt and GEPA. D17 is a coordinator decision under that goal; it
leaves the reads unchanged (D10, D12, RP1 to RP11), so every (event, bench) cell of the 5x5 is either a fresh reading
or an alias with a stored proof (3.7).

| # | Area (decision) | typed-v1 | typed-v2 |
|---|---|---|---|
| 1 | Card length (D2) | reject above 3,000 characters, final newline counted, generic retry text | writer still told 3,000 characters and 12 bullets; rejected only above 4,500 content characters or 12 bullets; newline not counted; retry names the measured length |
| 2 | Engineer prompt (D3) | route-B prompt, screen rules not stated, fix call sees only a reason word | typed-owned prompt with every screen rule and a legal rewrite; fix call gets the failed program and per-line evidence |
| 3 | Program promotion (D3) | 2 proposals, a screen failure wastes a slot | up to 3 proposals in one unit, the first 2 that pass the screen are tested; promotion only on screen failure |
| 4 | Reply reading (D4) | frozen route-B reader, strict envelope | one typed-owned tolerant reader, one format retry per programs unit |
| 5 | Gate (D5) | 1 run per item and arm, tau from one C0 pair, unknown pairs dropped | 3 fresh runs per item and arm inside one unit, item means, SE from the baseline's repeats, accept iff gain >= tau and better > worse, no cell dropped |
| 6 | Version and identity (D6) | `typed-v1` | `typed-v2` literals, new library and type-map versions, new pins, refusal of typed-v1 roots and libraries, caps sealed in the manifest |
| 7 | Machinery guard (D1) | none | pinned list of the 564 frozen files, check at every real start, bound-interpreter test |
| 8 | Beside typed-v1 (D7) | - | container names scoped by version and root, so the two runs cannot drain each other |
| 9 | Schedule, memory lock (D8, D9, D13) | reads interleaved with learning; per-cell lock | sealed manifest fields `schedule` (`interleaved` default, `learn_first`) and `memory_lock` (`per_cell_plain` default, `unit_shared`); the real run and the smoke set `learn_first` [D9] and `unit_shared` [D13] |
| 10 | Read plan (D9, D10, D11 as revised by RP1, D12) | every read event reads five panels fresh | sealed `read_plan` (`full` default; `economy` for the real run and the smoke): after the last freeze a zero-call planning pass groups, per bench, the events whose per-item mount identities are all equal; each class is read once, fresh, by its latest event; the others get alias records with a stored proof; any doubt reads fresh; C is read fresh, no typed-v1 reading is carried (3.7) |
| 11 | Learning base (D17) | learning starts from C0 (the format lines of C only) | sealed `base_card` (`format` default; `historical` for the real run and the smoke): every learned mount composes on the historical card C; the learning base arm `B` (C under 'historical'; C0's text under 'format') replaces C0 on the learning side; writers are shown C; read arms unchanged (3.1, 3.2, 3.4) |
| 12 | Shared types (D16) | a later bench's accepted skill changes the requests of an earlier bench of the same type with no check there (F14) | writers also see examples of every other member bench of the type; a candidate is accepted only if, besides the home rule, `no_regress` holds on every member's gate slice, else `member_harm` (3.4) |
| 13 | Learning widths (D15) | learning units at the read widths (3, 3, 3, 2, 2) | `LEARN_WIDTHS` (6, 6, 6, 2, 2) for learning units, `WIDTHS` for read units; both sealed (3.6) |
| 14 | Solver settings (RP2) | not recorded | credential-free `<chain>/solver-settings.json`, write-once, hash bound in the state; a resume with other settings pauses `solver_settings_changed` [Q22] (3.7 A) |
| 15 | Machine (D14) | - | both chains run on dl; the second machine is not used for this run (6) |

Changed by D9, D13: row 9 said only that both fields exist; the run's values are now fixed.

Approved by the owner but deferred (D1): the two static-screen relaxations, (a) nested pure calls in a module-level
constant such as `frozenset("a b".split())`, (b) `__name__` on an exception type. Reason: the screen is
`X/policy.py`, which the real run loads from the frozen snapshot; relaxing it needs a new policy version there plus
identity branches in package, notes, client and the in-container worker, hence a new machinery snapshot and possibly
a new qualification of the SpreadsheetBench scorer. The F6 losses came from the writer not being told the rules and
from reply reading; both are repaired inside `T/` (changes 2 to 4). The prompt names both forms as illegal and gives
the legal rewrite (section 3.2). They can return with the next machinery snapshot.

Not changed: benches, slice sizes (gate 100/40/100/50/40), bench order, models, card rounds (2), fix calls (one per
failing program), describer, form of the typing rule, read arms `C0, C, S1..S5` (also under D17), sandbox, static
screen, consent rules (exactly the six route-B fields; the consent note now names the root and states the read plan,
an operations rule [O9]), sealing of test reads. Learning is completely fresh from step 1 under the typed-v2 rules:
no practice-side cell, record or library entry of typed-v1 is reused (considered and rejected: about 3 M tokens saved
against a cross-version import inside the learning path) [D9].
Never cut to save tokens or time [D12]: fresh learning for all five steps; the gate rule of D5; the static screen and
sandbox; consent and sealing of test reads; a fresh five-panel reading of the final library; a fresh same-phase
baseline for every panel whose requests changed; the token caps of D6. No statistic or decision reads a carried or
aliased cell as an independent sample.
Changed by D17: the read arms stay, but the learning-side baseline is now B instead of C0 (3.4), and under
`base_card = 'historical'` every learned mount and every S<k> read composes on C.

## 2. Facts and constraints

- **F1 bound run.** The real run starts `scripts/run_typed.py --machinery-snapshot /data/execskill-code-20261109-main-v10`.
  `bind_machinery` puts the snapshot first on `sys.path`, imports `skillopt` from it and APPENDS this tree's
  `skillopt/execskill` to `skillopt.execskill.__path__` (`scripts/run_typed.py:35-54` [V]). So only `T/*`, and any
  module name that exists only in this tree, load from this tree; every other `skillopt` module is the snapshot's.
  An edit to `X/*` or `skillopt/coevo5/*` here is silently ignored by the real run. All changes live in `T/`,
  `scripts/`, `tests/`, `docs/`; the design may read and call the frozen modules but never edits them.
- **F2 identity of the copies.** 564 `skillopt/**/*.py` files outside `T/` are byte-identical to the snapshot; their
  list is `docs/handoff/typed-v2/machinery-main-v10.sha256`. Verified on dl, zero call [F11]: `sha256sum --quiet -c`
  of the list inside `/data/execskill-code-20261109-main-v10` passes; the snapshot holds 564 `.py` files outside
  `typed`, no `skillopt/execskill/typed`, no symbolic link; the list's own sha256 recomputed there equals the pin
  `3c37fdd90de0e6b51013af7fd4f166f3fa9a1fead5836b335111a4775202599f`. Changed by F11: F2 was inherited [I]; it is
  now verified.
- **F3 typed-v1 is frozen; F7 its stop.** Its tree, root `/data/execskill-20261110-typed-v1`, records and
  `docs/handoff/typed-v1/` are not edited. It was stopped on the owner's order by SIGINT to each chain's main process
  at 2026-11-12 15:13:33 [F7]: D exited 15:14:05 in unit `s5/program-1-gate` (83 units done, 54,957,897 tokens
  charged); G exited 15:15:21 in unit `s4/noise` (57 units, 33,924,247 tokens). Exit code 130, no pause record, no
  container left, nothing deleted. It is not resumed unless the owner asks. Finished read events there: C0 and C on
  five panels for both chains (2026-11-11), S1..S3 for G, S1..S4 for D. All its sealed read contents stay unopened
  until the typed-v2 code and run plan are frozen [F7]. None of them is carried into typed-v2 [RP1]; its C0 and C
  readings serve only the post-read replicate command (3.7 E).
- **F4 sealing.** Test items are opened only inside consent-gated read units; open files and logs carry hashes and
  counts only. No statistic of this design reads a test cell. No sealed number exists in this tree.
- **F5 owner rules.** Static screen and sandbox stay strict; self-tests are never fatal; gates judge gain and no harm.
- **F6 evidence.** The practice-side numbers quoted in section 1.
- **Code facts used below.** A cell tag is `sha256(bench NUL item id NUL arm label)` (`T/units.py:253-254` [V]), so a
  new label is a new cell, call file and rerun entry. Only infrastructure and configuration unknowns are re-run
  today (`T/units.py:316` [V]). A model-side unscorable answer is a final verdict with token `unknown` or
  `unknown_artifact` (`skillopt/coevo5/outcomes.py:138` [V]) and reaches the gate as `correct = None`
  (`T/mount.py:407` [V]). The ledger refuses a changed cap on resume (`T/units.py:114-115` [V]). The typed static
  screen is called without a bench, so the bulletin and receptacle rules apply on every bench (`W:402` [I]).
  Container names are `execskill-sbx-<chain letter>-<12 hex of sha256(unit)>-<uuid>`; the unit drain removes by that
  prefix (`X/sandbox/client.py:138-143, 316-325` [V]).
- **F8 read cells [F8; re-verified by `spec/read-plan.md` R8, R14 at 8375ecb].** A read unit's name depends only on
  (event, bench); a cell tag is sha256(bench, item id, arm); the recorded request hash is sha256(system NUL user);
  system and user come from the mount record, a function of (bench, item, arm, type map, library, vector, view); read
  cells carry no step. The per-step library and type-map files are write-once.
- **F9 machine (dl, measured read-only 2026-11-12 15:29).** 7 CPUs, cgroup v1 memory limit 15,032,385,536 bytes, no
  swap, boot 2026-10-14 20:53. Since boot `memory.failcnt` 0, `oom_kill` 0, no out-of-memory line in the kernel log;
  `memory.max_usage_in_bytes` 14,166,765,568 (page cache included). In that period main-v6..main-v9 and cross-v5 ran
  with the shared environment lock (`v218_lock.environment`): main-v9 alone has 506 (G) and 576 (D) receipts in
  `lock-waits.jsonl` (exclusive 367 / 494, shared 139 / 82; longest wait 8,420 s / 15,388 s). The shared mode ran for
  days on this machine without one memory kill and without the limit ever being hit.
- **F10 typed-v1 unit timing (file times only; `/data/typed-v1-ops/reuse.py <root> timing`).** Sheet cells under the
  plain lock, D alone on the machine: 27 to 41 s per cell (`s4/outcomes` 91 cells 1.03 h, `s4/card-r1` 50 cells
  0.38 h, `s4/program-1-gate` 50 cells 0.45 h, test panel C 204 cells 1.85 h); with the other chain also on sheet
  cells a test panel took 3.6 to 6.2 h; G `s4/noise` got 24 cells in 62 min while D ran ALFWorld learning units
  (shared holders starve the exclusive sheet cell). ALFWorld: D `s5/noise` 80 cells 0.66 h. GLM ZebraLogic: 200 cells
  in 0.97 h (`s3/noise`), a 200-item test panel 1.1 to 1.4 h. Sheet and ALFWorld work of both chains is the long pole
  of elapsed time.
- **F11 machinery lists (zero call, dl).** See F2. The data list `machinery-main-v10-data.sha256` was made there from
  the snapshot: 64 rows, sorted with `LC_ALL=C`, sha256
  `75ad90d48b644a1dddb43fc5e83edb855418229bd9930eed4e3c6f073b337a48` = `DATA_LIST_SHA256`. All 64 files of the local
  tree equal it (0 differences).
- **F12 token projection (accounting only; `/data/typed-v2-ops/capproj.py`, rates from the typed-v1 ledger).**
  Charged tokens per practice cell in typed-v1 (blank arm / with a card): SearchQA 1,340 / 1,800 to 2,150; OfficeQA
  5,200 to 6,300 / 5,400 to 7,300; ZebraLogic 4,700 to 4,900 / 4,900 to 6,200; SpreadsheetBench 1,300 / 1,400 to
  1,850; ALFWorld per episode D 24,800 / 43,500 (about 30 calls per episode, the card rides on every call), G 13,100
  on the test panel. One five-panel read event: G 4.9 to 6.1 M, D 5.8 to 6.8 M. Projection in million tokens
  ("typical" = no-harm shared, half of the second card rounds, 1.3 program gates per step; "full" = every unit of
  the step runs):

  | chain | learning typical | learning full | reads economy | reads all fresh | economy total | worst case x 1.1 | cap |
  |---|---|---|---|---|---|---|---|
  | G | 31.7 | 46.3 | 13.4 to 27.5 | 43.6 | 45 to 74 | 98.9 | 150 |
  | D | 40.3 | 59.2 | 16.4 to 33.7 | 51.0 | 57 to 93 | 121.2 | 170 |

  Per step (typical / full): G 3.3/4.8, 4.6/6.7, 9.0/13.3, 1.8/2.5, 12.9/19.0; D 3.3/4.8, 3.8/5.5, 7.9/11.7,
  1.6/2.3, 23.7/35.0. The ALFWorld step is 40 to 60 per cent of the learning cost. Both chains together: economy plan
  about 102 to 167 M (most likely 120 to 130 M), every cell read fresh about 167 to 200 M. The owner was told 65 to
  85 M on 11/12 15:3x from a rough count made before typed-v1 had reached ALFWorld and without the tripled gate arms;
  the corrected figure is reported to the owner before launch. The projection predates D16 and D17; their increments
  are in 3.4 (cost) and 3.7 I (K-D).
- **F13 unknown pairs in typed-v1 gates (O1 sizing).** Pairs excluded as unknown in typed-v1 gate decisions: G 0; D 1
  pair of 50 in each of the two SpreadsheetBench program gates of step 4. The O1 rule moves at most one item in a
  slice.
- **F14 shared types in typed-v1 [V at 8375ecb].** A type has one active card; an accepted card retires the previous
  one for every source of the type (`C.apply_card` -> `library.retire_card`, `typemap.set_card`). The writer's
  examples and the gate use the current bench's learn and gate slices only (`C.cards`, `C.card_decision`,
  `C.programs`, `C.program_decision`). So a later bench's accepted card or program changes the requests of an earlier
  bench of the same type with no check on that bench. Benches of other types get byte-identical requests (no change,
  hence no drop and no gain, by construction).
- **F15 the historical card C (opened historical readouts only; no typed-v1 or typed-v2 test read was opened).** On
  these five test panels (`SkillOpt/docs/handoff/textskill5x5-v1-readout-20261108/README.md`) the historical card C
  beats the blank arm (named B in that readout; not the learning base arm B of D17) by, G: SearchQA +11.3, OfficeQA
  +16.9, ZebraLogic +3.5, sheet +4.9, ALFWorld +1.5; D: +16.8, +13.4, -3.5, -2.9, +20.1. SkillOpt and GEPA, learned
  from an empty skill, end near C (chain-end five-bench mean minus C: SkillOpt G -1.1, GEPA G -1.3, GEPA D +1.1;
  SkillOpt D -16.3 from a global output-format conflict). typed-v1 starts from C0 (the format lines of C only; a
  mount without a learned card is C0, `T/mount.py` `system_card`) and its accepted SearchQA cards gained +4.0 / +5.0
  points on practice over C0. `v222_cards.historical_text(b)` is the whole card C and `format_text(b)` the format
  lines of it (they partition C's lines); for ZebraLogic both are the same text.
- **Precedence.** Addendum coordinator sections > this file > `spec/*.md`.

## 3. Areas

### 3.1 Card length (D2)

New module `T/cards.py` (about 90 lines) owns the card screen and the retry texts; `X/v225_cards.py` is only read.

- Constants: `CARD_TOLD_CHARS, CARD_HARD_CHARS, CARD_MAX_BULLETS = 3000, 4500, 12`;
  `BULLET = re.compile(r'^\s*(?:[-*+•]|\d+[.)])\s+')` (copy of `X/v225_cards.py:167` [I]);
  `LIMITS_RECORD = {'told_chars': 3000, 'hard_chars': 4500, 'max_bullets': 12, 'count': 'content characters without the final newline'}`.
- `content_chars(text)` = `len(text.strip())` for a string, else 0. `bullet_count(text)` = lines matching `BULLET`.
- `content_violation(...)`: verbatim copy of `X/v225_cards.py:169-201` [I] (keys `format_markers`, `item_identity`,
  `references`, `copied_examples`). It calls private names of frozen modules (`v225_cards._reference_values`,
  `v225_cards.PATH_LIKE`, `leakage._numbers`, `_numeric`, `_significant`, `_value`, `_grams`,
  `engineer.absent_findings`): each of them is listed in `machinery.REQUIRED` (3.5), and `COPIED_SOURCE_SHA256` (the
  sha256 of the copied source lines, computed when the module is written) is checked by a test and at real start.
- `card_screen(text, ...) -> {'violation', 'chars', 'bullets'}`. The length rule is tested first: `'length'` iff
  the text is no string or blank, `content_chars > 4500`, or `bullet_count > 12`; else the content key or None.
- The writer's system message is unchanged: it still asks for at most 3,000 characters and 12 bullet points. The
  first-attempt card request is byte-identical to typed-v1. 4,500 is never named to the writer.
  Changed by D17: the first-attempt request is byte-identical to typed-v1 only under `base_card = 'format'` and on
  ZebraLogic; under 'historical' it carries the base-card block (below). 4,500 is still never named to the writer.
- `CARD_ATTEMPTS = 2` stays (`W:34` [V]). The retry message is the first user message, two newlines, then
  `RETRY_FRAME.format(reason=...)`:

```python
RETRY_FRAME = ('Your reply could not be used as the card: {reason}. Reply again with only the card text, '
               'following every rule of the system message.')
REASON_TOO_LONG = 'it has {chars} characters, but a card may have at most {target}; cut at least {cut} characters'
REASON_TOO_MANY_BULLETS = ('it has {bullets} bullet points, but a card may have at most {max_bullets}; '
                           'merge or remove at least {extra}')
REASON_NO_TEXT = ('it was empty or was cut off before its end, so no card text was received; keep the card '
                  'within {target} characters and {max_bullets} bullet points')
REASON_JOIN = '; in addition, '
RETRY_SHORT = {'length': 'it is empty, longer than 3,000 characters or has more than 12 bullet points',
               'format_markers': 'it contains an answer, action or calc tag or a code fence',
               'item_identity': 'it contains a task identifier or a file path',
               'references': 'it contains a reference answer or a value from one',
               'copied_examples': 'it copies text from an example'}
```

  Numbers are written with thousands separators; `target` = 3,000, `cut` = chars - 3,000, `extra` = bullets - 12.
  Reason: no text -> `REASON_NO_TEXT`; too long -> `REASON_TOO_LONG`; too many bullets -> `REASON_TOO_MANY_BULLETS`;
  both -> the two joined with `REASON_JOIN`, length first; a content key -> `RETRY_SHORT[key]`. `RETRY_FRAME` and
  `RETRY_SHORT` equal the bound `CARD_RETRY` / `RETRY_REASONS` (`X/v225_cards.py:50-58` [I]; a test asserts it), so
  a content-violation retry is byte-identical to typed-v1. Room rule: the detailed sentence is used when
  `len(message) + 2 + len(sentence) <= v225_cards.CARD_WRITER_INPUT_CHARS` (120,000), else the short `length`
  sentence; `_fit_examples` (`W:241-251`) is not edited.
- Records: every attempt row gains `bullets`; `chars` means content characters everywhere (attempt row, card
  decision, skill record); the write result gains `card_limits = LIMITS_RECORD`.
- Later consumers accept 4,500 characters [I, table in `spec/card.md` 1.3]: library, describer, the revision
  request's `previous_card`, mount and solver system message. The v2.25 card `Procedure` cap of 3,000
  (`X/package.py:193-200`) is not on the typed path.
- Change sites: `W:30` (import), `W:269-272` `screen_card`, `W:275-295` `write_card` (retry text, attempt row,
  `card_limits`), `C:54` (import), `C:784` (`'chars': cards.content_chars(text)`) [line numbers of defs V].
- Base card [D17]. With `base_card = 'historical'` the card writer's user payload gains one key
  `base_card = {'meaning', 'text'}`: `text` = `mount.base_text(bench, 'historical')`, the historical card C, exactly
  what the solver receives; `meaning` = a label that names it as the instruction the solver already receives on every
  task of this kind, placed in its system prompt right after the card, and asks the writer to add to it, not to repeat
  or contradict it, with the length limits applying to the card alone (wording pinned by sha256 in
  `tests/test_typed2_base.py` [impl 5b]). The writer's system message (the frozen v2.25 text) is unchanged. The block
  is left out where the base text equals the format block (base 'format'; ZebraLogic under both), so those requests
  stay byte-identical. The D2 length rules apply to the learned text only; C is never counted. Fix and format-retry
  requests carry no block. As built, the card screen's public text under 'historical' is the format block plus C, so
  a phrase of C is never flagged as a reference leak or a copied example [impl 5b, choice 7; a reading of D17 that
  only removes findings, flagged for the batch-2 review].
- Shared types [D16 a]. When the home type T of step k has other member benches M (3.4 "Shared types"), the card
  writer (both rounds) also sees examples of every b' in M: the current mount F run once on b''s LEARN slice (unit
  `s<k>/member-<b'>-outcomes`), chosen and rendered by the same rule as the current bench's examples, at most as many,
  in a block labelled with its source (with b''s own base card under 'historical' [impl 5b, left for 5x]). The request
  names the member sources and states the member rule (3.4). The current bench's part of the request is unchanged;
  no gate item of any bench reaches a writer; the D2 length rules are unchanged. A revision round's result summary
  adds the member check as counts and points only. A type with one bench changes nothing (golden test) [D16 d].
- Later consumers [D17]: under 'historical' every learned solver system message is the learned text, `CARD_JOIN`
  and C, so it holds up to 4,500 characters of card plus C (about 900 to 2,900 more characters on non-ZebraLogic
  benches; ALFWorld carries it on every call of an episode).

### 3.2 Engineer prompt, screen evidence, promotion (D3)

New module `T/engineer_prompt.py`: `PROMPT_VERSION = 'typed-engineer-prompt-1'`, `PURPOSES = ('propose', 'fix')`,
`RULES` (22 rows: 17 rule sentences and 5 rewrite rows), `NOTE_HOOKS_BY_BENCH` (searchqa, officeqa: `before_call`,
`bindings`; zebralogic: `before_call`; spreadsheetbench: `before_call`, `sheet_feedback`; alfworld:
`alf_before_step`), `EVIDENCE_ROWS = 8`, `SOURCE_LINE_CHARS = 240`, `PINS` (sha256 of the ten texts: five benches
times two purposes), `system(bench, purpose)`, `rule_key_for(rule, detail, source_line)`,
`screen_evidence(failed, source, bench)`, `verify()`. It replaces `W:310-315` `engineer_system`; `W:40`
`ALFWORLD_PROMPTS` and `W:299-307` `alfworld_prompt_configuration` are deleted.

Every list and limit in the text is rendered at import from the bound modules, so the text cannot disagree with the
screen that runs: `policy.source_limit`, `MAX_CONSTANT_CHARS`, `IMPORTABLE`, `FROM_ONLY`, `FORBIDDEN_NAMES`,
`FORBIDDEN_ATTRIBUTES`, `FORBIDDEN_MODULES` minus `ORDINARY_ATTRIBUTES`, `RECEPTACLES` (`X/policy.py:62-122` [I]);
`MAX_DESCRIPTION_CHARS`, `MAX_HEADER_CHARS`, `MAX_NOTE_CHARS` (`X/protocol.py:225-230` [I]); `package.MAX_STATE_BYTES`
(`X/package.py:44` [I]). `verify()` recomputes the ten sha256 and compares them with `PINS`. The first sentences of
WHAT YOU RETURN are `replies.REPLY_FORMAT[purpose]` (3.3), embedded by reference; a test checks it.

Text of `system('searchqa', 'propose')`, one paragraph per line, not wrapped (`officeqa` differs only in the bench
name; rendered length 10,076 to 11,216 characters over the ten texts [I]):

```text
You write small Python helper programs for a solver model that works on searchqa tasks. A program runs in a sandbox beside the solver. Its hook functions read the public task input and may hand the solver short notes. It never sees a reference answer or a score. A program is kept only on results: first it must run without a fault on a few practice tasks; then, on held-out practice tasks, the solver must do clearly better with it than without it on the tasks where the program applied, and no worse over all tasks.

WHAT YOU RECEIVE (user message, JSON). task_card and format_block: what the solver is already told; both are fixed, do not restate them. skill_index: names and descriptions of the skills that already exist for these tasks; do not duplicate one. trajectories: practice tasks with the solver's outcome; look for mistakes a program could have prevented by computing or checking something from the task input. hook_views: one real sample of the exact inputs your hooks receive (long strings and lists are cut for display only).

WHAT YOU RETURN. Reply with one fenced json block holding {"changes": [...]} and then one fenced python block per change, in the same order. Each python block is one complete program. Put no program text inside the JSON.
Propose at most 3 programs, the most useful first. They are checked in your order: the first 2 that pass the static screen are tested, and a later one is used only when an earlier one fails. Each entry of "changes" has: "kind": "new" (the only kind accepted); "description": what the program does and when it helps, at most 600 characters; "hooks": the hook functions your code defines; "header": a short title shown above its notes, at most 200 characters, or ""; "max_note_chars": the longest note it may produce, 1 to 4000 (left out or 0 means 4000).

HOOKS. The sandbox calls only top-level functions with exactly these names and parameters. Naming a hook in "hooks" does not create it. A program that defines none of before_call, bindings can never write a note and is rejected.
applies(view) -> bool. Optional; without it the program applies to every task. Return False where the program has nothing reliable to say: it is judged on the tasks where applies returned True.
before_call(view, state) -> a notes dict or None. view = {"question", "context"}; state is always None.
bindings(view) -> {"bindings": [{"name", "quote", "value"}, ...]} or None: numbers quoted from the task text for the solver's calculator. name is a calculator name, value is numeric text, quote must contain value word for word.

NOTES. A notes dict may hold any of: "facts" and "warnings": lists of strings, each at most 200 characters; "candidates": list of strings, each at most 120 characters; "table": list of rows, at most 20 rows by 12 columns, every cell a string of at most 40 characters; "bindings": list of {"name", "quote", "value"}, each a string of at most 200 characters. An unknown field, a wrong type or a value over its cap is a fault and the whole note is dropped; so is a rendered note longer than max_note_chars. Smallest valid returns: before_call -> {}; bindings -> {"bindings": []}. When the program cannot verify what it would say on a task, return no note: a wrong note costs more than no note.

CONTENT. Notes state what the program computed from this task's own public input. Never: a false or overclaiming note; advice on the form of the answer beyond what the task itself states; an instruction that overrides the task or its scoring; a guess from what is typical for the benchmark; facts from outside the task or hard-coded answers; routing by benchmark name, task id, file path, answer or score. The program must do what its description says.

STATIC SCREEN. Before anything runs, a checker reads the program text. It is strict and literal: one violation rejects the program, and you get one correction. The rules, each with the name the checker reports:
[size] The file is at most 24,000 bytes of UTF-8. Rewrite: shorten the program; drop tables and branches it does not need.
[syntax] The file is valid Python 3. Rewrite: correct the line the checker names and re-read the lines around it.
[module_level, statements] At the top level write only: an optional docstring as the first statement, import lines, def functions, and constants written NAME = value with one plain name on the left. No if / for / while / try / with, no class, no "A, B = 1, 2", no "A: int = 1", no "A += 1", no call or other expression on a line of its own. Rewrite: move the statement into a function; write one constant per line.
[module_level, constant values] The value of a top-level constant must be one of: (a) a literal: a number, string, bytes, True, False, None, or a tuple, list, set or dict written out with literals inside (nesting is fine); (b) the name of an earlier constant, alone: B = A; (c) literals of one type joined with +: "ab" + "cd", [1, 2] + [3]; (d) exactly ONE of these calls on literals: set(...), frozenset(...), tuple(...), list(...), dict(...), sorted(...) of one literal; "a b c".split() or "a,b".split(","); ", ".join(["a", "b"]); re.compile("pattern") or re.compile("pattern", re.I | re.M) after a plain "import re". The forms cannot be nested or mixed. Nothing else is allowed in a constant: no f-string, comprehension, lambda, *, %, .format, no other call, no expression that uses another constant.
Rewrite, word set: WORDS = frozenset("alpha beta".split()) is rejected (two calls). Write WORDS = frozenset({"alpha", "beta"}), or keep a list: WORDS = "alpha beta".split().
Rewrite, regex: PAT = re.compile(r"(\d+)\s*" + UNIT) is rejected. Write the pattern as one string literal (adjacent literals without + count as one: re.compile(r"(\d+)\s*" r"(kg|lb)")), or compile it inside the function that uses it.
Rewrite, any other value: compute it inside a function and call that function where the value is needed.
[constant_size] The written value of one constant is at most 2,000 characters. Rewrite: several shorter constants, combined inside a function.
[statement] No class, global, nonlocal, async or await anywhere. Rewrite: return dicts or tuples; keep memory in the state argument.
[decorator] No decorators. Rewrite: a plain function.
[import] Only these modules may be imported: bisect, calendar, collections, copy, datetime, decimal, difflib, fractions, functools, heapq, itertools, json, math, numpy, openpyxl.utils, operator, pandas, re, statistics, string, sympy, textwrap, unicodedata. "import M", "import M as name" and "from M import name" are allowed for them, and also "from numpy.random import default_rng"; "from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter, range_boundaries". No "import *", no other submodule and no other module: no typing, dataclasses, os, sys, io, time, random, pathlib. Rewrite: leave type hints out or use the built-in names (list, dict).
[name] These names cannot be used at all (as a call, variable, parameter, function name or import alias): breakpoint, compile, delattr, dir, eval, exec, exit, getattr, globals, hasattr, hash, help, id, input, locals, open, print, quit, setattr, vars. No name may start with two underscores. Rewrite: view.get("key") instead of getattr / hasattr; call a variable ident or kind, not id or hash; return notes instead of print.
[attribute] After a dot these are never allowed: (1) a name starting with an underscore, which covers every dunder (__name__, __class__, __dict__); (2) a name starting with read_ or to_ (to_dict, to_numeric, to_datetime, read_csv); (3) these names: ExcelFile, ExcelWriter, HDFStore, ag_code, ag_frame, attrgetter, cr_code, cr_frame, eval, f_back, f_builtins, f_code, f_globals, f_locals, format_map, fromfile, fromregex, genfromtxt, gi_code, gi_frame, gi_yieldfrom, lambdify, load, load_workbook, loadtxt, memmap, methodcaller, mro, now, parse_expr, parsing, query, save, savetxt, savez, savez_compressed, sympify, tb_frame, tb_next, today, tofile, utcnow; (4) a name equal to a blocked module name: asyncio, atexit, builtins, code, codeop, concurrent, ctypes, faulthandler, fcntl, gc, glob, http, httpx, importlib, inspect, io, logging, marshal, mmap, multiprocessing, os, pathlib, pickle, platform, pty, queue, requests, resource, runpy, sched, secrets, select, shelve, shutil, signal, site, socket, sqlite3, ssl, subprocess, sys, sysconfig, tarfile, tempfile, threading, traceback, tracemalloc, urllib, uuid, warnings, zipfile.
Rewrite, exception or type name: type(e).__name__ is rejected. Catch the class you expect and write its name as text: except ValueError: kind = "ValueError". For an unknown exception use repr(e).split("(", 1)[0].
Rewrite, data access: view.get("code") or row["code"] instead of view.code; list(series) and dict(zip(keys, values)) instead of to_list / to_dict; float(text) instead of to_numeric.
[numpy_random] numpy randomness only as numpy.random.default_rng(seed) with one fixed integer seed. Rewrite: rng = numpy.random.default_rng(7).
[clock] No current time: besides .now / .today / .utcnow, no "now" or "today" text given to Timestamp, Period or datetime64. Rewrite: take dates from the task text.
[sympify] No sympy parsing of text: no S("..."), sympify, parse_expr or lambdify. Rewrite: build expressions from sympy.Symbol and numbers.
[dunder_string] No string literal may contain a word wrapped in double underscores, such as "__main__". Rewrite: drop the text or write it without the underscores.
[meta_option] The file, comments included, must not contain "stronger result", "stronger statement" or any four consecutive words of "one of the remaining options is correct but a stronger result can be proven". Rewrite: delete the sentence; describe what the program computes instead.
[bulletin_literal] On every bench, no string literal (docstrings included) may contain: a page reference with a number ("page 12", "pp. 3"); a month name or abbreviation followed by a year 1800-2099 ("March 1985"; the word "may" counts); "treasury bulletin" followed by a digit. Rewrite: read such values from the task input at run time; in a pattern write \d+.
[receptacle_literal] On every bench, no string literal may contain one of these words followed by a number ("cabinet 1", "drawer 3"): armchair, bathtub, bathtubbasin, bed, bowl, box, cabinet, cart, coffeemachine, coffeetable, countertop, cup, desk, diningtable, drawer, dresser, fridge, garbagecan, handtowelholder, laundryhamper, microwave, mug, ottoman, paintinghanger, pan, plate, pot, safe, shelf, sidetable, sinkbasin, sofa, stoveburner, toaster, toilet, toiletpaperhanger, towelholder, tvstand. Rewrite: take object names from the observation or the admissible commands at run time.
```

Bench-dependent parts of the other three benches:

```text
[zebralogic] "none of" list: before_call. Smallest returns: before_call -> {}. Hook lines after "applies":
before_call(view, state) -> a notes dict or None. view = {"question", "columns"}; state is always None. Read the puzzle's own clues and compute constraints the solver can use.
[spreadsheetbench] "none of" list: before_call, sheet_feedback. Smallest returns: before_call -> {}; sheet_feedback -> {"fields": {}, "request_repair": False}. Added to the entry sentence: "requests_second_call": true only if sheet_feedback may ask for a repair. Hook lines after "applies":
The view is {"instruction", "workbook_preview", "input_path", "required_output_path", "required_answer_position"}.
before_call(view, state) -> a notes dict or None; state is always None.
sheet_feedback(view, run_report, state) -> {"fields": notes dict, "request_repair": bool}. run_report = {"status", "exc_type", "message", "answer_cells"} comes from one run of the solver's code on the public input workbook; it holds no reference workbook and no grading result, and the program never sees the solver's code. request_repair asks for at most one repair attempt by the solver and counts only when the entry declares "requests_second_call": true.
[alfworld] "none of" list: alf_before_step. Smallest returns: alf_before_step -> {"fields": {}, "discourage": []}. Added to the entry sentence: "state_bytes": the largest state alf_after_step returns, 1 to 65536 bytes of JSON (left out or 0 means 65536). Hook lines after "applies":
applies reads view = {"initial_observation", "admissible_commands_at_reset", "task_text"}.
alf_before_step(view, state) -> {"fields": notes dict, "discourage": [admissible commands to advise against]}. view = {"initial_observation", "observation", "admissible_commands", "recent_history"}.
alf_after_step(event, state) -> the new state (plain JSON data). event = {"step", "action", "observation", "admissible_commands"}. state is None until alf_after_step first returns a value. Module globals are reset between calls: keep memory in state only. On this bench the notes of one step are limited to 1500 characters in all; a longer note is skipped. The first fault switches the program off for the rest of the episode.
```

Purpose `fix`: the first three paragraphs become the following; HOOKS, NOTES, CONTENT and STATIC SCREEN are the same.
The entry list ends with `, "requests_second_call"` on spreadsheetbench and `, "state_bytes"` on alfworld.

```text
A helper program you wrote for a solver model on searchqa tasks was rejected by a check before it could be tested. Correct it. Keep what the program does; change only what the check requires. You get this one correction.

WHAT YOU RECEIVE (user message, JSON). change: the entry of the rejected program. failed_source: its full text. failed.check: which check failed ("policy" = the static screen below; "hooks" = no usable hook function is defined; "structure" = the entry and the hooks do not fit together; "source" = no program text was found). Each row of failed.detail gives: rule (the name used in the screen rules below), line and source_line (where; line 0 = the file as a whole), detail (what the checker saw), rule_text (the rule in words) and rewrite (the standard legal form). failed.more counts violations not shown.

WHAT YOU RETURN. Reply with one fenced json block holding {"changes": [<the one corrected entry>]} and then one fenced python block with the complete corrected program. Put no program text inside the JSON.
Apply the rewrite on every listed line. Then read the whole program once more against every rule of the static screen: a rejected program often breaks the same rule in other places. Return the complete corrected program, not a patch, with the same entry fields ("kind": "new", "description", "hooks", "header", "max_note_chars").
```

Rules of the area:

- Limits (one convention for all areas): module constants in `T/__init__.py` are the defaults
  (`MAX_PROGRAM_PROPOSALS = 3` new, `MAX_PROGRAM_CANDIDATES = 2` at `:43` [V], `GATE_REPEATS = 3` new); the run reads
  them only through `Services.limits` (`C:61` `DEFAULT_LIMITS`, `C:158` [V]) with keys `card_rounds`,
  `max_program_proposals`, `max_program_candidates`, `program_smoke_items`, `gate_repeats`; `decisions.json` records
  the dict (`C:928` [V]). Smoke: `max_program_candidates = 1` (`T/smoke.py:28` [V]), `gate_repeats` stays 3. A real
  run requires `limits == DEFAULT_LIMITS` and `manifest['tau_rule']['repeats'] == GATE_REPEATS`.
- Bound defect (`W:359` `_bounded_entry`, line 387 [I]): `values[key] = high if before < low else min(high, before)`;
  an absent, 0 or negative `max_note_chars` becomes 4,000 and `state_bytes` 65,536, as the prompt says.
- Extra check in `W:396` `build_procedure` [O7]: a program that defines none of `NOTE_HOOKS_BY_BENCH[bench]` fails
  with check `hooks`, rule `no_hook_function`. The frozen package rule demands no entry point (`X/package.py:133, 152`
  [I]); such a program can never write a note. The check is accepted, and its order is binding: the typed-side
  `no_hook_function` check runs before the unchanged `policy.check(source, version=POLICY_VERSION)` [O7]. As built
  (4b) it runs after it (source, policy, hooks, structure) [impl 4b]. This deviates from O7
  until the coordinator either confirms O7 (4b moves the check) or corrects O7's order (section 8, still open 3). The
  frozen call is the same either way; the order decides only which evidence a program failing both checks gets
  first [I].
  Changed by O7: the first integration placed the check after the unchanged `policy.check`.
- Fix request, the one definition (user message, canonical JSON):
  `{'request': 'fix', 'bench', 'change': <the entry, without any source key>, 'failed_source': <program text>,
  'failed': {'check', 'detail': [rows], 'more'}}`; a row is `{'rule', 'line', 'detail', 'source_line', 'rule_text',
  'rewrite'}`, at most `EVIDENCE_ROWS` rows, `source_line` cut at `SOURCE_LINE_CHARS`, `more` = violations not shown.
  `check` is `policy`, `hooks`, `structure` or `source`.
- Promotion inside the unit `s<k>/programs` (there are no `program-3*` units). `W:469` `propose_programs`:
  1. one `replies.RetryBudget` per call of the function; one proposal call with `system(bench, 'propose')`;
  2. the reply is read by `replies.read_with_retry(..., read=read_proposals)`; at most 3 records, in the writer's order;
  3. per record: problem -> `unreadable`; kind not `new` -> `kind_not_new`; no free slot -> `not_needed` (not
     screened, no call); else `build_procedure`: passed -> `passed`, takes the next slot; failed -> exactly one fix
     call (`system(bench, 'fix')`, the fix request above), read by `read_with_retry(..., read=read_fix)`, screened
     again -> `passed_after_fix` (takes a slot) or `dropped_screen`;
  4. slots = `limits['max_program_candidates']`. A later proposal is used only because an earlier one failed the
     screen or was unreadable; smoke and gate failures never promote. At most 5 writer calls per unit attempt
     (1 proposal + 3 fixes + 1 format retry).
  Each row of `proposals.json`: `{'n', 'status', 'slot', 'procedure', 'screen', 'first_screen', 'fix',
  'request_sha256', 'read', 'format_retry'}`. `W:436` `_row` and `W:442` `_fix_once` are rewritten once, for this
  shape; the old reading lines `W:452-461, 483-487` are replaced by the two `read_with_retry` calls.
- `C:841` `programs()` (one merged version for this area and the gate): it iterates over ALL rows, not over
  `proposals[:max_program_candidates]` (`C:871` [V], which would test a dropped row and never the promoted third).
  A row with a slot runs `program(k, ..., slot, row, snapshot)` (units `s<k>/program-<slot>-smoke`, `-gate`);
  `dropped_screen`, `unreadable` and `kind_not_new` rows get a zero-call decision row (`candidate` and `unit` null,
  `accepted` false, `reason` = `'screen:' + reason`, `'unreadable:' + code` or `'kind_not_new'`); `not_needed` rows
  appear in `proposals.json` only. `base` (`C:889-891` [V]) gains `proposal` and `status`. The fake writer in
  `tests/test_typed_chain.py:105` returns rows of the new shape.
- Base card [D17]. With `base_card = 'historical'` the proposal payload (user message) gains the same key
  `base_card = {'meaning', 'text'}` with the engineer's label (the instruction the solver already receives; the
  program's notes add to it, do not repeat or contradict it), defined as `BASE_CARD_MEANING` in
  `T/engineer_prompt.py` [impl 5b]. The ten pinned system texts, `PINS` and `PROMPT_VERSION` are unchanged. The block
  is left out where the base text equals the format block (base 'format'; ZebraLogic); fix and format-retry requests
  carry no block.
- Shared types [D16 a]. The engineer also sees examples of every member b' in M, chosen and rendered as the current
  bench's, at most as many, labelled with their source; after an accepted card they come from
  `s<k>/member-<b'>-outcomes-card`, as the current bench's come from `s<k>/outcomes-card`. The request names the
  member sources and states the member rule. The pinned propose text says a program is kept when the solver does
  better where it applied "and no worse over all tasks", which names the home slice only; whether the member sentence
  enters the ten pinned system texts (a new `PROMPT_VERSION` and new pins) or the user payload only is settled by step
  5x, in progress at the merge (section 8, still open 2).
- As built [impl 4b, 4c]: `W` runs `engineer_prompt.verify()` once per process before the first request;
  `propose_programs` follows the promotion loop above, with one `replies.RetryBudget` per call and every send of every
  attempt kept in the unit's calls file; `C.programs` iterates over all rows and writes zero-call decision rows for
  dropped, unreadable and `kind_not_new` rows.

### 3.3 Reply reading and the format retry (D4)

New module `T/replies.py` (about 300 lines), the only reader of engineer replies in typed-v2. It uses frozen PUBLIC
helpers only (`engineer_reader.FENCE`, `MAX_REPLY_BYTES` = 1,048,576, `Unusable`, `tolerant_json`, `schema`,
`normalize`, `defined_hooks`; `profiles.HOOKS`, `profiles.MAX_CHANGES` = 3; `engineer.EDIT_KINDS`) [I].

```python
READER = 'typed-reply-reader-1'; FORMAT_RETRIES_PER_UNIT = 1; RETRY_PREVIOUS_REPLY_BYTES = 200_000
is_program(text) -> bool                                  # engineer_reader.defined_hooks(text) is non-empty
read_proposals(reply, *, parent_ids=()) -> result
read_fix(reply, *, change) -> result                      # change = {'entry': dict, 'source': str}
readable(result) -> bool
retry_request(purpose, bench, problems, previous_reply) -> (system, user) | None
class RetryBudget: take() -> bool
read_with_retry(reply, sha, *, purpose, bench, send, budget, read) -> {'result', 'request_sha256', 'format_retry'}
# result = {'records', 'problem', 'repairs', 'reply_sha256', 'reader'}
# record = {'n', 'kind', 'entry', 'source', 'problem', 'repairs', 'read'}
```

Reading rules (general tolerance, no patch for one field):
1. Size: above `MAX_REPLY_BYTES` -> problem `oversize`, nothing else is read.
2. Blocks: found with the frozen `FENCE`. A JSON candidate is a block tagged json/jsonc/json5, or an untagged block
   starting with `{` or `[`. Every other block is a code block.
3. Manifest, in this order: (a) exactly one JSON candidate that parses with `tolerant_json`; (b) several: the single
   one with a `changes` or `change` key (repair `extra_json_blocks_ignored`), else problem `several_manifests`; (c)
   none: the text outside the fences if it parses as a whole, else exactly one balanced top-level `{...}` in it
   (`manifest_outside_fence`); (d) fix only: none, but a code block exists -> the entry of the change under repair is
   reused (`manifest_absent_inherited`); (e) else `no_manifest`, or `manifest_json` when a candidate did not parse.
4. Envelope: `changes` -> its value; `change` -> its value (`alias_change`); both and different -> problem
   `ambiguous_envelope`. One object where a list is expected is wrapped (`single_change_wrapped`); an object with
   neither key but with `source`, `code` or an entry field is the one change (`bare_change`); a top-level list of
   objects is the list (`bare_list`); else `no_changes_key`. A non-object element -> `change_not_object`. An explicit
   empty list is a readable "no proposal": no problem, no retry.
5. Counts are strict: more than 3 changes -> `too_many_changes` (no truncation); a fix reply with other than one
   change -> `fix_change_count`.
6. Kind: missing -> `new` unless the id is a parent id; a revision of an unknown id is `new`
   (`unknown_revision_is_new`); a word outside `EDIT_KINDS` -> `unknown_kind`. In a fix the kind is that of the
   change under repair (`fix_kind_ignored`).
7. Block ownership. E = the `new` changes in order; B = the code blocks in order, reduced to the program blocks when
   any block is a program. `len(B) == len(E)` -> by position; else `len(B)` equals the number of entries whose inline
   source is no program -> by position among those; else one entry -> every block is its candidate; else each entry
   without a program inline source gets `blocks_not_assignable`.
8. Source of a change. Candidates: the inline value (`source`, alias `code`, unfenced if fenced) and the owned
   blocks. Keep the program candidates, equal texts once; in a fix, a candidate equal to the failed source is an echo
   and is dropped when another program remains (`echo_source_dropped`). One left -> the source; two or more
   different -> `ambiguous_source` (never guess). No program candidate: the single owned block, else the non-blank
   inline text, is returned as it is, so that the unchanged screen names the fault and the fix call gets evidence.
   No text or several non-program blocks -> `no_source`. Never inherited from the failed change or a parent; never
   altered apart from removing the fence lines. An inline placeholder beside a real fenced program is ignored
   (`inline_not_program_ignored`).
9. Entry fields go through the frozen public `normalize(entry, schema('new', ...), ...)`; its `Unusable` -> problem
   `entry_field`.
10. Strict: the reader only parses. It never executes, imports or compiles reply text and never replaces the screen:
    every returned source goes unchanged into `build_procedure` (policy check, `Procedure` validation) and then the
    sandbox smoke. Tolerance decides WHICH text is screened, never WHETHER. The text not chosen is recorded (length,
    sha256). The reader never raises for reply content (`RecursionError`, `MemoryError` -> problem `resources`).

Format retry. Trigger: a reply was delivered and nothing readable came back (a whole-reply problem, or every change
has a problem). No trigger: no reply, an empty `changes` list, at least one readable record, a readable program that
fails the screen (that is the fix call's job). Budget: 1 per attempt of the unit `s<k>/programs`, shared by the
proposal call and the fix calls; the first unreadable reply takes it, a later one is recorded with
`format_retry = {'skipped': 'budget_spent'}`; a previous reply above 200,000 bytes gives `'skipped':
'reply_too_large'`. The budget lives in memory: a unit interrupted before `proposals.json` is written starts again
from the proposal call, and every send of every attempt stays in the unit's calls file. The request is a new small
one (the proposal payload is not re-sent): system = `FORMAT_RETRY_SYSTEM`, user = canonical JSON `{"request":
"format_retry", "purpose", "bench", "problems": [{"code", "change", "detail"}], "expected_format":
REPLY_FORMAT[purpose], "previous_reply": <verbatim>}`. The retry reply is read by the same function with the same
arguments; readable -> the unit continues with it and lineage `engineer_call` is the retry call; else recorded as
unreadable, no second retry. Pinned texts:

```text
FORMAT_RETRY_SYSTEM: Your previous reply could not be read. `problems` states exactly what was unreadable. Send the same content again in the format given in `expected_format`. Do not change what the program does; repair only the format. Give each program exactly once, inside one fenced python block, and put no program text inside the JSON.
REPLY_FORMAT['propose']: Reply with one fenced json block holding {"changes": [...]} and then one fenced python block per change, in the same order. Each python block is one complete program. Put no program text inside the JSON.
REPLY_FORMAT['fix']: Reply with one fenced json block holding {"changes": [<the one corrected entry>]} and then one fenced python block with the complete corrected program. Put no program text inside the JSON.
```

`PROBLEM_SENTENCES` holds one fixed sentence template per problem code (15 codes: `oversize`, `several_manifests`,
`no_manifest`, `manifest_json`, `ambiguous_envelope`, `no_changes_key`, `change_not_object`, `too_many_changes`,
`fix_change_count`, `unknown_kind`, `blocks_not_assignable`, `ambiguous_source`, `no_source`, `entry_field`,
`resources`), filled with counts and key names only. Fixed so far: `no_changes_key`: "The JSON object has the
top-level keys [...]; none of them is `changes`."; `ambiguous_source`: "Change 1 gives two different programs: inline
`source` (N characters) and fenced block 1 (M characters). Send exactly one."; `no_manifest`: "No JSON object was
found (fenced code blocks: N; other text: M characters)." The other twelve are written in this form with the module
and pinned with it (section 8, O8). Change sites: `W:30`, `W:436`, `W:442`, `W:469`, `T/smoke.py:36-41, 180`.

Resolved [O8]: the implementer of step 3 worded the twelve remaining `PROBLEM_SENTENCES` in the form of the three
given ones (counts and key names only, never reply text); they are pinned (check 6 of `machinery.check`, completed in
step 7); the Codex review of batch 1 covered the module [O8; impl 3].
As built [impl 3; Codex review round 1 of batch 1, commit e2cf9e7]: rule 7 has one extra step A2' between A2 and A3:
when the reduction to program blocks dropped blocks, all code blocks are assigned by position to the changes without
an inline program, as the frozen reader does, so a broken sibling program still reaches the screen and its fix call;
after the review A2' applies only when every code block is a python-tagged fence (a prose, untagged or other-language
block never takes a position). Rule 3 (b) after the review: when exactly one JSON candidate parses, it is the
manifest; else one pass over `changes` and `change` together picks the single keyed object, else
`several_manifests` (no silent preference of `changes`). These are build readings of rules 3 and 7, not addendum
decisions; e2cf9e7 is on branch typed-v2-codex1-fixes and was not in the main tree at about 19:55 (section 8, still
open 4).
D16 and D17 do not change the reader: fix and format-retry requests carry no base-card or member block (3.1, 3.2).

### 3.4 Gate (D5)

Labels. `GATE_REPEATS = 3`. A gate arm runs R cells per item with labels `<arm>#<r>`, r = 1..R (`B#1..3`, `F#1..3`,
`cand_card#1..3`, `cand_program#1..3`; Changed by D17: was `C0#1..3`), all inside ONE unit.
`gates.arm_of_label(label) = label.split('#', 1)[0]` is passed as `arm_of` to `_Run.cells` (the keyword exists,
`C:664` [V]); the label enters the cell tag
(`T/units.py:253-254` [V]) and never a request, so the R cells of an item are identical requests sent fresh. Units
that decide nothing stay single-run with the plain label: `F` on learn items, program smoke, read units.

Step k, bench b: (1) `s<k>/noise`: `B#1..3` on the gate slice [D17]. (2) `s<k>/typing`: per same-signature type T,
`s<k>/noharm-<T>` runs only `F#1..3` (source provisionally merged) against the shared baseline `B@noise` [D17]. This
moves the no-harm baseline from the same unit (back to back per item, `C:719` [V]) to the earlier noise unit; time
drift between the two units now enters that comparison. (3) `s<k>/outcomes`: `F` once on the learn items, and
`F#1..3` on the gate items only when F is not a shared arm. (3m) [D16] For every other member b' of the home type:
`s<k>/member-<b'>-outcomes` (`F` once on b''s learn items, for the writers) and `s<k>/member-<b'>-base` (`F#1..3` on
b''s gate items, the member baseline; it is needed only once a candidate has passed the home rule, so when it runs is
step 5x's choice [I]). (4) `s<k>/card-r<j>`: `cand_card#1..3`; for a round that passed the home rule,
`s<k>/card-r<j>-member-<b'>` (`cand_card#1..3` on b''s gate items) [D16]. (5) After an accepted card,
`s<k>/outcomes-card`: `F` with the card on the learn items only; [D16] `s<k>/member-<b'>-outcomes-card` the same on
b''s learn items. (6) `s<k>/programs` (writer calls), `s<k>/program-<i>-smoke`, `s<k>/program-<i>-gate`:
`cand_program#1..3`; for a program that passed the home rule, `s<k>/program-<i>-member-<b'>` [D16].

Changed by D17: the learning base arm was C0 (labels `C0#1..3`, `C0@noise`); it is now B, whose mount is
`system_card(bench, '')`, the base card alone: C under 'historical', the format block (C0's text) under 'format'.
Under 'format' B's mount identity equals C0's, so every request is byte-identical to the design without D17; only the
cell tags differ, because the label enters the tag [impl 5b, 5w]. Read units keep C0 and C; B is never a read arm.
Step 5b used the interim labels `Ba`/`Bb` and `B`; step 5w replaced them by `B#1..3` and `B@noise` [impl 5b, 5w].

Changed by Q23 [RP12]: every learned-side or S-event mount that returned the format block for an item (the
unknown-type branch of `_route` / `_routed_mount`, and a typed item whose type has no card) returns
`system_card(bench, '')`: C under 'historical', the format block under 'format' [built in 5b].

Statistics, exact integer arithmetic (x = 1 for a correct cell, else 0; B = baseline arm, K = candidate arm):

```text
S[A,i] = sum_r x[A,i,r]          m[A,i] = S[A,i] / R          D = sum_i (S[K,i] - S[B,i])
q[i]   = R * sum_r x[B,i,r]^2 - S[B,i]^2                      Q = sum_i q[i]     (s2[i] = q[i] / (R * (R - 1)))
gain_points = 100 * D / (R * n)                     = 100 * mean_i (m[K,i] - m[B,i])
se_points   = (100 / (R * n)) * sqrt(2 * Q / (R - 1)) = 100 * sqrt(2 * sum_i s2[i] / (R * n^2))
tau_points  = max(TAU_MIN_POINTS = 3.0, TAU_SE_MULTIPLIER = 2.0 * se_points)
better, worse, tied = number of items with S[K,i] >, <, = S[B,i]
reaches(D, m)  := 100 * D >= 3 * R * m  and  D >= 0  and  D^2 * n^2 * (R - 1) >= 8 * Q * m^2     # gain over m items >= tau
no_regress(D)  := 100 * D >= -3 * R * n  or  D >= 0  or  D^2 * (R - 1) <= 8 * Q                  # gain >= -tau
```

In the formulas B and K are the baseline and the candidate of one comparison; the learning base arm B of D17 is
the baseline of the noise calibration and of the no-harm checks, and, through sharing case (b) below, the F of a new
type with no skill [D17].

- Card: accepted iff `reaches(D, n)` and `better > worse`; else `gain_below_tau` or `not_more_better_than_worse`
  (typed-v1's name of the second was `better_not_above_worse` [impl 5s]). For a shared type also the member rule
  below must hold, else `member_harm` [D16 b].
- Program: an item is "fired" when the candidate fired in at least one of its R cells (`C:908` [V] is the one-cell
  form) [O6]; the record keeps the fired count per item (0..R) as `fired_cells = [[item, count], ...]` for the items
  with a count above 0 [O6, O12]. With `n_f` fired items and `D_f`, `better_f`, `worse_f` over them: accepted iff
  `n_f > 0` and `reaches(D_f, n_f)` and `better_f > worse_f` and `no_regress(D)` over all items; else `never_fired`,
  `gain_below_tau`, `not_more_better_than_worse`, `harm`. Q and n are those of the whole slice, as in typed-v1. For a
  shared type also the member rule must hold, else `member_harm` [D16 b].
- Program gate on the fired items [PG]. The rule above stays the typed-v1 rule with the repeat statistics of D5: the
  gain on the fired items is compared with the tau of the whole slice, `better_f > worse_f`, and `no_regress` over
  all items. A stricter threshold for small fired subsets would change the decision rule against the owner's gate
  principle of 11/02 ("gain and no harm, not too defensive") and is not made. Informational only, never deciding:
  every program decision record stores `fired_items` (n_f), `fired_cells`, `se_points_fired = (100 / (R * n_f)) *
  sqrt(2 * Q_f / (R - 1))` (Q_f over the fired items) and `se_points_scaled = se_points * sqrt(n / n_f)`. Reports
  state for each accepted program how many items it fired on and how its gain compares with these two values.
- No-harm: merge iff `no_regress(D)` with B = `B@noise`, K = `F@noharm-<T>` [D17]; reasons `merged` /
  `harm_beyond_tau`, kept from typed-v1 [impl 5s]. The typing no-harm check is unchanged by D16 [D16 d].
- tau belongs to one comparison: it is computed from the repeats of that comparison's baseline arm. R >= 2 required.
- Baselines: card rounds: F. Programs: the incumbent F, which after an accepted card is the accepted round's
  `cand_card#r` runs (both program candidates use the same baseline). These runs were selected for being high; that
  makes program acceptance and its no-regress check stricter, never looser. Resolved [O5]: D5's sharing stays; the
  decision record says so (`baseline_selected: true`) and reports must name it when a program is accepted on such a
  baseline.
- Binary scores only [O11]: x = 1 for a correct cell, else 0; `arm_runs` refuses a `correct` value that is neither
  `True`, `False` nor `None`; records hold JSON integers only; `scores` is always `'binary'`. Changed by O11: the
  bullet "a non-binary score would use the same formulas on `Fraction` with tolerance 1e-9" is not built (no typed
  bench has a non-binary score, and unused arithmetic in the deciding module is a risk without a benefit). As built,
  `minimum_points` and `multiplier` enter the integer forms as exact fractions [impl 5s].

Shared arms. Before a gate arm P runs, its mount identity is computed for every gate item without a paid call:
`{'system_card_sha256', 'programs_offered': [[skill_id, skill sha256], ...], 'forced': candidate record sha256 or
None}` (`T/mount.py:190` `_routed_mount` is split into `_route` and `mount_identity`; built in step 5m, with
`_forced_record` shared by both, and taking `base_card` since 5b [impl 5m, 5b]). P is the same arm as an arm Q already
run in this step iff the identities are equal on EVERY gate item; then P runs no cell and uses Q's R runs. Q is
searched in the order `B@noise` [D17], `F@noharm-<T>`, `F@outcomes`, `cand_card@card-r<j>`, `F@outcomes-card`,
`cand_program@program-<i>-gate`; as built, among the step's arms of the same bench in run order, so member arms are
searched among the arms of their member bench [impl 5w; D16 b]. Cases that follow: (a) the baseline side of every
no-harm check is `B@noise`; (b) a new type with no skills: F = `B@noise`, also when some gate items are unknown under
the new type map, because an unknown or card-less item mounts `system_card(bench, '')`, B's text, under either base
[Q23]; (c) a merged source: F = `F@noharm-<T>`; (d) a failed no-harm check and a new type: some gate items may still
route to the old type, so F may differ and `F#1..3` run in `s<k>/outcomes`; (e) after an accepted card: F =
`cand_card@card-r<j>`; (f) a round-2 text equal to round 1, or a candidate that reaches no home-type gate item, is an
earlier arm: no cells, gain 0, rejected. The sharing decision is written once per unit before any cell (`plan.json`:
unit, arm, labels, repeats, items, identity list sha256, `shared_from`; as built also bench, step, the per-item
identity digests and `compared` [impl 5w]); a resumed unit must find the same plan (as built, a different plan pauses
`gate_plan_changed` [impl 5w]); a shared row whose recorded `system_card_sha256` differs from the identity pauses
`shared_arm_mismatch`. Shared rows keep their own unit, label and mount record; every consumer looks rows up by
(unit, label): `_correct` (`C:221`), `outcomes_for_writer`, `_outcome_counts` in `finalize` (`C:917`), readout
`_unit_summary` (`T/readout.py:219`).

Changed by D17: the search began with `C0@noise`, and cases (a) and (b) named `C0@noise`.

Cells. A decision and `noise.json` need all `n * R` cells of both arms.
- No record for a cell: pause `incomplete_unit:missing_cells` (as today).
- `correct is None` with `infrastructure_unknown` or `configuration_error`: re-run by the existing rule
  (`T/units.py:316` [V], predicate unchanged); the first record is archived under `rerun/` and the number of re-runs
  per arm is stored in the decision. Still unknown after the unit's attempts: the done marker is archived and the
  chain pauses `gate_cells_unknown`; nothing is decided, no item is excluded.
- `correct is None` from a final model-side verdict (token `unknown` or `unknown_artifact`, neither flag set): the
  cell is present and final. It is NEVER run again: re-drawing an arm until its answer is scorable would select in
  favour of that arm, send more than R requests and pause again on a program that always writes an unscorable
  file. It is scored x = 0 and counted per arm in `unknown_final` (section 8, O1; `spec/gate.md` 1.7 re-ran these
  cells, which the code facts above rule out).
- Rerun entries are kept per (unit, tag) and removed when the cell has been run again: today the set holds bare
  tags (`T/units.py:116-117, 319, 344` [V]) and labels such as `F#1` recur in several units of a step, so a tag left
  in the set would re-draw a finished cell of a later unit. `run_unit` gets the unit name for this.
- Resolved [O1]: a cell whose final outcome is a model-side unknown (`unknown`, `unknown_artifact`) is scored 0, never
  re-run and counted in `unknown_final`; infrastructure and configuration unknowns are re-run by the existing rule and
  pause the chain if they stay unknown; the same holds for both arms of every comparison, member comparisons included
  [D16 b]. Size [F13]: in typed-v1 this would have moved at most one item in a slice.
- As built [impl 5w]: `units.run_unit(..., unit=)` takes the unit name (required); rerun entries are `(unit, tag)`
  pairs, discarded once the cell has run again; `mark_infrastructure_reruns` moves the earlier record to
  `rerun/<tag>-<n>.json`, so the file count is the re-run count; `arm_runs` maps a missing or still-unknown cell to
  `incomplete_unit:missing_cells` or (done marker archived) `gate_cells_unknown`.

Records [O12]. `per_item` of a decision record is the list `[[item, S_B, S_K], ...]` in the item order of the slice
(for binary scores the sum of squares equals the sum, so it is not stored); `noise.json` stores `per_item = [[item,
S], ...]`; program decisions add `fired_cells = [[item, count], ...]` for the items with a count above 0. Where
`spec/gate.md` 3.2 shows a dictionary with squares, this list form holds.

Module placement [MP]. The pure repeat statistics live in the typed-owned module `T/gatestats.py` (labels,
`arm_runs`, `repeat_statistics`, `calibration`, the three decisions, `recompute`); it imports nothing from the frozen
machinery and touches no file (as built it imports only `math`, `fractions` and `collections.abc` and takes R as a
parameter [impl 5s]). `T/gates.py` drops its three typed-v1 decision functions and re-exports these names, so
`gates.recompute` and the other names of this section resolve as written; `paired_statistics`, `split_pairs` and
`noise_threshold` stay in `T/gates.py` for the readout of read events [built in 5w].

Shared types [D16]. At step k with current bench b and home type T (after typing), the OTHER MEMBERS M are the
earlier benches b' with a source in T. When M is not empty:
- (a) Writers: 3.1 and 3.2. Member examples come from `s<k>/member-<b'>-outcomes` (F once on b''s LEARN slice), after
  an accepted card from `s<k>/member-<b'>-outcomes-card`.
- (b) Gate: a candidate (card round or program) is accepted iff the D5 home rule holds on b's gate slice (unchanged)
  AND for every b' in M `no_regress(D_b')` holds on b''s gate slice: R = 3 runs per item and arm; member baseline = the
  current mount F on b' items (`s<k>/member-<b'>-base`, `F#1..3`; after an accepted card, that card's member runs, as
  O5, with `baseline_selected: true`); tau from that comparison's baseline repeats (D5); O1 applies. The member
  comparison runs only for a candidate that passed the home rule. Reason on failure: `member_harm` (naming the bench).
  Units `s<k>/member-<b'>-base` (`F#1..3`), `s<k>/card-r<j>-member-<b'>` (`cand_card#1..3`),
  `s<k>/program-<i>-member-<b'>` (`cand_program#1..3`); D5 arm sharing (identities, `plan.json`) and the per-(unit,
  tag) rerun rule apply to them.
- (c) Records and reports: every decision record of a shared type stores per member: items, D, better, worse, tied,
  `gain_points`, `se_points`, `tau_points`, `no_regress`, units, labels, `baseline_selected`; `gates.recompute`
  reproduces the member verdicts (the member verdict function lives in `T/gatestats.py`, which stays pure [impl 5x
  plan]). Readout and reports show for each accepted skill its home gain and every member gain ("related gain":
  informational, it decides nothing beyond `no_regress`).
- (d) Scope: a type with one bench changes nothing: no extra unit, cell or request; every request equals the D5
  behaviour byte for byte (golden test). The typing no-harm merge check is unchanged. Reads (D9, D10, D12, RP1 to
  RP11) are unchanged: a member panel whose requests change is read fresh before and after by the economy plan (3.7).
- (e) Cost [I]: only when a later bench joins an earlier bench's type; in this bench order only OfficeQA can join
  SearchQA's type (step 2). Per chain about 1.5 to 4 M tokens (member outcomes about 0.3 M each, member baseline about
  0.6 M, about 0.6 M per candidate that passes the home rule); 0 if OfficeQA opens its own type. D6 caps unchanged.
- Build: step 5x, after the Step 5 wiring 5w (IMPLEMENTATION-ORDER).

Cost on the gate slices, cells per step [I]: typed-v1 at most 8n; typed-v2 15n (B 3n, two card rounds 6n, two program
gates 6n) plus 3n for each no-harm check and 3n in case (d): 21n with one check, 6,930 cells over the five steps (sum
of n = 330) against 2,640. Without sharing it would be 24n and more. Changed by D17: "C0 3n" is now "B 3n" (same
count). D16 adds, for a shared type only, the member units above (about 1.5 to 4 M tokens per chain) [D16 e]. D17
makes cells longer, not more numerous: C adds about 900 to 2,900 characters to every system message of
non-ZebraLogic cells, and ALFWorld carries it on every call of an episode (D's per-episode cost with a card was
43,500 against 24,800 blank [F12]); rough total plus 10 to 20 M tokens per chain [D17, I]. The token projection is
F12; with D16 and D17 the worst case grows to about 123 M of G's 150 M cap (82 per cent) and 145 M of D's 170 M (85
per cent) [`spec/read-plan.md` K-D]; the D6 caps hold.

Change sites: `T/gates.py` new `repeat_labels`, `arm_of_label`, `repeat_of_label`, `arm_runs`, `repeat_statistics`,
`calibration`, `recompute(record)` and new bodies of `card_decision` (`:130`), `program_decision` (`:142`),
`no_harm_decision` (`:167`); `paired_statistics` (`:78`), `split_pairs` (`:101`), `noise_threshold` (`:112`) stay
for the readout of read events. `C`: `cells` (`:477`), new `gate_arm` and `identities`, `noise` (`:655`), `no_harm`
(`:712`, returns the STORED record; today it returns the fresh dict, `C:722-724` [V]), `outcomes` (`:726`), `cards`
and `card_decision` (`:731, :773`), `program_decision` (`:886`), `finalize` (`:917`). `T/units.py:116-117, 301-345`.
`T/prepare.py:255` (`tau_rule` gains `'repeats': 3, 'se': 'baseline_repeats'`). `T/readout.py:61, 153, 174, 219,
707`. `T/smoke.py:28, 263, 293`.

Changed by [MP]: the new helpers and decision bodies listed above for `T/gates.py` live in `T/gatestats.py`;
`T/gates.py` re-exports them and keeps the three read-side functions.
As built [impl 5w] the wiring uses these names. `C`: `BASE_ARM = 'B'`, `PLAN = 'plan.json'`, `GATE_PAUSES`;
`Services.identity_fn` (wired to `mount.mount_identity` by `real_services` and by the fake services, with the same
`base_card` as the mounts); `_Run.gate_arms`, `repeats()`, `identities()` (zero calls), `gate_arm(unit, bench, arm,
*, candidate, typemap, library, extra_jobs)`, `register_stored(unit)` (re-registers a stored arm on resume),
`compare(kind, baseline, candidate, *, fired_cells)`, module helper `recompute_decision`; `MIN_NOISE_PAIRS_FRACTION`
and the pause `noise_uncalibrated` are removed; `run` refuses `limits['gate_repeats']` other than an int >= 2;
`real_services` refuses a manifest whose `tau_rule` differs from `prepare.tau_rule()`. `W` `revision_result` requires
a typed-v2 card record and reads `gain_points`, `tied`, `excluded_unknown` by name. A gate-accepted program whose
description failed keeps typed-v1's `accepted: false`, reason `description_failed`, and stores the gate's verdict in
`gate_verdict`. D17's base is threaded through `builder`, the reads and both writers as the keyword `base_card` [impl
5b]; D16's member units and verdicts are step 5x.

### 3.5 Version, identity, machinery guard, beside typed-v1 (D1, D6, D7)

- Literals: `VERSION = CONFIGURATION = 'typed-v2'` (`T/__init__.py:9-10` [V]); `EVIDENCE = {'run':
  'typed_v2_real_run', 'smoke': 'typed_v2_smoke', 'test': 'engineering_fixture'}` (`:63` [V]); `LIBRARY_VERSION =
  'typed-v2-library'` (`T/library.py:15` [V]); `TYPEMAP_VERSION = 'typed-v2-typemap'` (`T/tasktypes.py` [I]);
  `ROOT_NAME = re.compile(r'^execskill-\d{8}-typed-v2(-smoke)?$')` (`T/prepare.py:34` [V]). `MACHINERY`,
  `MACHINERY_SNAPSHOT`, `MACHINERY_MANIFEST` (`T/__init__.py:56-58` [V]) stay: the machinery is still main-v10.
- One version mechanism, no compatibility switch. The library starts empty. Every load requires the new literal, so
  a typed-v1 library, type map, manifest or chain state is refused. `prepare.own_root(root)` refuses a root whose
  name, manifest `version` / `configuration` or chain state `version` belongs to another typed version; it is
  called by every command of `scripts/run_typed.py` (`prepare`, `smoke`, `run`, `readout`, `status`) and by
  `reads.read_panel` (`T/reads.py:179`), because `_open_state` checks only the chain state (`C:939-948` [V]).
- Exception to "new names", to be confirmed (O4): the draw keys keep their typed-v1 values, `SEED = 20261110`
  (`T/__init__.py:13` [V]), `SLICE_TAG = 'typed-v1:%s:slices'` (`T/prepare.py:39` [V]), `EXAMPLE_TAG =
  'typed-v1:writer-examples'` (`W:36` [V]), so that typed-v2 learns and gates on the same practice items. The
  manifest records them as `draw_keys`.
  Resolved [O4]: confirmed. The draw keys keep their typed-v1 values (`SEED`, `SLICE_TAG`, `EXAMPLE_TAG`): the same
  practice items as typed-v1. This is the one stated exception to D6; the manifest records them as `draw_keys`. (The
  carry of the reference row C, which O4 also kept possible, was dropped later [RP1].)
- `T/machinery.py` (new): `LIST = 'docs/handoff/typed-v2/machinery-main-v10.sha256'` (564 rows [V]),
  `LIST_SHA256 = '3c37fdd90de0e6b51013af7fd4f166f3fa9a1fead5836b335111a4775202599f'` [F11: verified on dl, zero
  call], `LIST_FILES = 564`,
  `REQUIRED` (every frozen name that `T/` uses, the private ones of 3.1 included), `listed()`, `compare(root)`,
  `loaded()`, `require_symbols()`, `check(*, real)`. `check(real=True)` runs at every real start (run, resume, smoke
  on dl) and refuses before any call when one of these fails: (1) the list file has `LIST_SHA256` and 564 rows; (2)
  every listed file under the bound snapshot has its listed sha256; (3) tree side: every `skillopt/**/*.py` outside
  `T/` equals the list and no unlisted `.py` exists there (564 today [V]; an edited copy would be silently ignored
  by the bound run, a new module would silently become importable); (4) every imported `skillopt.*` module outside
  `skillopt.execskill.typed` has its file under the snapshot, every `typed` module under this tree; (5) every name
  of `REQUIRED` exists; (6) pins, the one rule for all pinned texts of `T/`: `engineer_prompt.verify()`,
  `cards.COPIED_SOURCE_SHA256`, the card retry texts, the three reply texts and `PROBLEM_SENTENCES`. Without a
  snapshot (`real=False`, Mac tests) it runs (1), (3), (5), (6).
  As built in step 1m, check 6 is a stub that passes; step 7 completes it [impl 1m]. Interface requirement [Q19,
  RP12; `spec/read-plan.md` 5.3]: the check also pins the `scripts.*` modules the bound run imports, at least
  `scripts/weak_solver_probe.py` (it sets chain G's thinking, effort and max tokens and the request body of both
  chains, and is on neither pinned list); built in step 7.
- Data files: 64 files that are not `.py` exist under `skillopt/` outside `T/` [V] (prompts, sandbox files); the
  bound run reads the snapshot's copies and the 564-row list does not cover them. A second list
  `machinery-main-v10-data.sha256` is made on dl from the snapshot, pinned as `machinery.DATA_LIST_SHA256` and
  checked by (2) and (3) (O2: it cannot be made without the snapshot).
  Resolved [F11, O2]: the list was made on dl from the snapshot (64 rows, `LC_ALL=C` sorted) and is pinned as
  `DATA_LIST_SHA256 = '75ad90d48b644a1dddb43fc5e83edb855418229bd9930eed4e3c6f073b337a48'`; the 64 local files equal
  it.
- `bind_machinery` (`scripts/run_typed.py:35-54` [V]) also refuses a snapshot that holds `skillopt/execskill/typed`.
- `chain.start_checks(root, manifest, *, check, provenance)`, called by `run` before the ledger opens (`C:953-973`):
  `own_root`; the `check` result equals `manifest['machinery_code']`; the current `typed_code` (sha256 list over
  `T/**` and `scripts/run_typed.py`) equals `manifest['provenance']['typed_code']`. The wide `tree_provenance`
  (`skillopt/`, `scripts/`, `tests/`; `T/prepare.py:226-236` [V]) stays as information only: a touched test or ops
  helper must not block a resume, a touched `T/` file must. The chain state stores `machinery_code` and
  `container_scope`.
- Caps: `manifest['caps']`, fixed at `prepare`; `Services(cap=manifest['caps'][chain])` replaces
  `services.cap or CAPS[chain]` (`C:973` [V]). The ledger refuses a changed cap (`T/units.py:114-115` [V]): a wrong
  cap means a new root.
- Beside typed-v1 (D7): `scope = '%s:%s:' % (VERSION, Path(root).name)`; the worker tag is
  `sandbox.unit_tag(chain, scope + unit)` (`C:1155` [V]) and the drain is `sandbox.drain_unit(chain, scope + unit,
  ...)` (`C:1164` [V]). The tag is 12 hex of the sha256 of that string (`X/sandbox/client.py:138-143` [V]), so a
  typed-v1 and a typed-v2 unit of the same chain letter and unit name no longer share a container prefix and
  `drain_unit` (`:316-325` [V]) cannot remove or trip over the other run's containers. No request changes.
- Sealed manifest fields after the merge (each compared with the code or checked at load): `version`,
  `configuration`; `caps`, `draw_keys` [O4], `widths`, `learn_widths` [D15] (compared with the code constants by
  `prepare.sealed_constants` [impl 1a]); `machinery_code` (eight keys) and `provenance.typed_code` [impl 1b];
  `tau_rule` with `repeats`, `se` [D5]; `schedule`, `memory_lock` [D8] (run and smoke: `learn_first` [D9],
  `unit_shared` [D13]); `base_card` [D17] (`'format'` | `'historical'`; refused when missing or unknown [impl 5b]);
  `read_plan` [D9] and, in a smoke manifest only, `read_plan_probe` [Q20] (3.7 A). Of the fields added after the first
  integration only `base_card` changes request content (the system text of learned mounts, 3.4, 3.7 B);
  `schedule`, `memory_lock`, `widths`, `learn_widths` and `read_plan` enter no request, cell tag or identity [D8,
  D13, D15, R14].
- The chain state also records `base_card`, and a resume with another base is refused [impl 5b]. It binds the hash of
  the solver-settings record (3.7 A, R75) [RP2].
- `own_root` is also the first call of the new commands `plan-replay` and, after launch, `replicate` (for `--root`);
  `replicate --source` may name a typed-v1 root, the one exception to "no typed-v2 helper names a typed-v1 path"
  [RP1, R83].

### 3.6 Schedule and memory lock (D8)

- `SCHEDULES = ('interleaved', 'learn_first')`, default `interleaved`; `MEMORY_LOCKS = ('per_cell_plain',
  'unit_shared')`, default `per_cell_plain`. Both are sealed manifest fields, set only by `prepare(..., schedule=,
  memory_lock=)` (CLI `--schedule`, `--memory-lock` on `prepare`); `run` reads them from the manifest.
  Run values [D9, D13]: the real run and the smoke set `schedule = learn_first` (and `memory_lock = unit_shared`,
  below). `interleaved` stays the code default; `read_plan = economy` is allowed only with `learn_first` (3.7 A).
- `interleaved` is the typed-v1 order: confirm, anchors C0 and C, then per step learn and read `S<k>`
  (`C:979-982` [V]). `learn_first`: confirm; freeze s0; steps 1..5 learn and freeze; then C0, C and mark `step-0`;
  then S1..S5, each read from its frozen files, mark `step-<k>`. The order never enters a request or an identity.
  Changed by D10 (R20, R35): under `read_plan = economy` the read part of `learn_first` is replaced: after the last
  freeze come the planning pass (pseudo-unit `read-plan`), its automatic replay and `read_classes()` (3.7);
  `read_anchors` and `read_step` are never called. Under `full` the order above stands.
  Learning is closed once reading has begun [R79]: with `learn_first` and either read plan, `learn(k)` never runs its
  body and `freeze_anchor` never writes once `state['phase'] == 'read'`, `read-plan` is in `done_units`, or
  `read-plan.json`, the sealed plan directory or any read unit directory exists; a missing or unequal `s<k>` file or
  receipt then pauses `frozen_state_changed` and is resolved by restoring the files to the recorded hashes, never by
  learning again.
- `s<k>/frozen.json`, write-once: `{version, chain, step, bench, library_record_sha256, typemap_record_sha256,
  library_file_sha256, typemap_file_sha256, at, record_sha256}`. State gains `schedule`, `phase` (`learn` | `read`),
  `read_mounts`. `_Run` gains `freeze_anchor`, `read_anchors`, `learn`, `read_step`, `learned`, `freeze`,
  `load_frozen`, `bind_read`. Pauses: `frozen_state_changed` (a frozen file differs from its receipt),
  `read_mount_changed`.
  Phase names are `learn` and `read`; this section wins over `spec/schedule-lock.md` S10 (`learning` / `reading`)
  [`spec/read-plan.md` 5.7]. Under `economy` the planning pass sets `phase = 'read'`, `current_unit = 'read-plan'` and
  all seven `read_mounts` entries from the frozen receipts before it opens anything (R20; schedule-lock Q14).
- Lock: `Services.heavy(bench, unit=None)`, built by `chain.heavy_for(manifest, root, chain)`. `per_cell_plain` is
  today's call, unchanged (`C:1131-1132` [V]). `unit_shared` calls the existing frozen function on the same lock
  file with `root`, `memory_lock_chain`, `memory_lock_unit` (`X/v218_lock.py:97-101` [V]). Memory ceilings of the two
  chains sum to 9,728 MiB with the plain lock and 14,848 MiB with the shared one, against the measured limit of
  14,336 MiB [F9: 15,032,385,536 bytes; `spec/schedule-lock.md` L3 assumed 15,360, the 15 GiB named at
  `X/chain.py:86`; its "MB" are MiB]. By ceilings the shared mode exceeds the limit (by 512 MiB), so the code default
  stays `per_cell_plain` (schedule-lock L7). D13 sets `unit_shared` for the run and the smoke on F9's measured history
  (`failcnt` 0, no memory kill, peak 14,166,765,568 bytes with page cache), guarded by the ops sampler (6), not on the
  ceilings.
  Changed by F9: the first integration compared the ceilings with schedule-lock's 15,360 MB, under which the shared
  mode stays about 0.5 GiB below the limit; against the measured limit it is 0.5 GiB above it.
- Value for the real run and the smoke (addendum D13): `unit_shared`, sealed by `prepare --memory-lock
  unit_shared`. Basis, measured read-only on dl on 2026-11-12 (addendum F9, F10): 7 CPUs, memory limit
  15,032,385,536 bytes, no swap; since boot on 2026-10-14 `memory.failcnt` 0 and no memory kill while main-v6 to
  main-v9 and cross-v5 ran this shared lock; typed-v1 sheet cells took 27 to 41 s each under the plain lock and a
  test panel 3.6 to 6.2 h when both chains were on sheet cells. With `unit_shared` two sheet cells of one unit run
  at once and waits are written to `<chain>/lock-waits.jsonl`. In the same change the ALFWorld preparation reset
  of a read unit, which takes no lock today (`T/reads.py:229-230`, `X/evaluation.py:506-519` [V]), is wrapped:
  `heavy_for` also returns the lock setting it built, kept as `Services.lock_setting` (None with
  `per_cell_plain`), and `_from_services` passes `v218_lock.call(reset, lock_setting, 'alfworld', unit=unit)`
  (`X/v218_lock.py:194-200` [V]) instead of the bare reset: lock first, then the episode slot, as main-v10 did
  (`X/v225_read.py:316-323` [V]). With `per_cell_plain` the reset stays bare. The lock mode enters no request, no
  cell tag and no mount identity.
  Considered and not taken now [D13]: locking only the native operation with model calls outside (`v218_lock.call` /
  `workers` / `engine` inside `T/mount.py` `solve`; schedule-lock L2 c): larger gain, but new call sites and a new
  memory analysis.
  The read plan reuses this wrap [R23, R24]: the planning pass wraps its ALFWorld preparation resets with the same
  helper as `_from_services`. R24 (spec) puts the extraction of `reads.open_panel` from `_read` (one panel path for
  read units and the pass) in the same change as the reset wrap, so that `T/reads.py` is edited once; O10 says only
  that the read plan shares `T/reads.py` with the reset wrap of D13. Step 6 lists the wrap, and the RP decisions do
  not touch Steps 1 to 7 [RP header of 17:29], so who makes the wrap is open (section 8, still open 1).
  Changed by RP1: D13 also put the lock mode into "every carry receipt"; there is no carry, and the post-read
  replicate command prints typed-v1's lock mode (`per_cell_plain`) in its heading (R86).
- Change sites: `C:98-162` (`Services`), `C:451` `load_state`, `C:589-653` (`reads`, `anchors`, `step`), `C:917`
  `finalize`, `C:939-985`, `C:1131-1132`; `T/reads.py:229-230, 253-298, 324-345`; `T/smoke.py:293`; `T/readout.py:645, 689`;
  `T/prepare.py:255-302`; `scripts/run_typed.py` (options of `prepare`).
- Learning widths [D15]. New typed-owned constant `LEARN_WIDTHS = {searchqa: 6, officeqa: 6, zebralogic: 6,
  spreadsheetbench: 2, alfworld: 2}`, used by the learning units (`C` `cells`, before `widths=WIDTHS`); `WIDTHS` (3, 3,
  3, 2, 2) keeps serving the read units, where five panels already run side by side. Both are sealed in the manifest
  (`widths`, `learn_widths`); the smoke uses the same values. A width enters no request, no cell tag, no identity and
  no decision; all arms of one unit run under the same width. Evidence: typed-v1's read phase sent up to 13 requests
  at once per chain to the same providers for days (five panels, inner widths 3, 3, 3, 2, 2) and ran mounted material
  in the sandbox at that load; a learning unit sends 6. Effect: GLM answers one ZebraLogic item in about 52 s, so 200
  cells take 0.97 h at width 3 [F10]; the typed-v2 ZebraLogic step has up to 2,300 cells, about 10 h at width 3 and
  about 5 h at width 6. Rate-limit errors become infrastructure unknowns and are re-run by the existing rule. The
  widths are not changed inside a root; a pause caused by rate limits is resumed with the same values and reported.
  As built [impl 1a, 1b]: `prepare.sealed_constants()` seals and `load_manifest` compares `caps`, `draw_keys`,
  `widths`, `learn_widths`; `_Run.cells` passes `widths=LEARN_WIDTHS` (every unit run through `cells` is a learning
  unit); a fake smoke at the read widths sends the same requests in the same unit order (test).

### 3.7 Economy read plan (D9, D10, D11 as revised by RP1, D12; RP1..RP13)

A summary of the corrected `spec/read-plan.md` (fix2) with its rule ids; the spec holds the detail, the [V] citations
and the critic history (A1..A17, CB1..CB31, I-1..I-16, ADV1..ADV14). Nothing on the learning side changes here. The RP
decisions bind the corrected spec and "do not touch Steps 1 to 7 of IMPLEMENTATION-ORDER.md"; the read plan is still
built after Step 6 [RP header of 17:29; O10]. The pure core `T/readplan.py` exists (H); the pass, the read phase, the
CLI and the readout are still to be built (IMPLEMENTATION-ORDER, Step R; its grouping "batch 3" and the ids there are
a proposal of this merge [I]).

Decisions.
- [D9] Run mode: `schedule = learn_first` and the sealed field `read_plan = economy` for the real run and the smoke.
  `full` (every event reads five panels fresh, the typed-v1 behaviour) stays the code default and the only value
  allowed with `interleaved`; `prepare` refuses `economy` without `learn_first`.
- [D10] Every distinct set of requests is read fresh exactly once: (a) the unit of reading stays the whole panel of
  one bench for one event; no item-level mixing; (b) after the last freeze (s5) and before any read call, a zero-call
  planning pass computes, inside the consent-gated read path, for every bench and every event E in (C0, C, S1..S5)
  the per-item MOUNT IDENTITY under E's arm and E's frozen library and type map; two events are in one CLASS for a
  bench iff the identities of ALL items of the panel are equal; (c) each class is read once, with fresh calls, by the
  read unit of its LATEST event; so the final library (S5) is always read fresh on all five panels, and a panel that a
  step changed gets a fresh reading of the state before and after the change, both in the same read phase (no claimed
  effect rests on a cross-date comparison); (d) every other (event, bench) of a class gets an ALIAS record naming the
  representative and storing the proof (both identity lists' hashes, item count); an alias is never a result of its
  own; the readout shows the representative's reading for it and marks it "same requests as <event>"; a difference
  between two events of one class is zero by construction and is shown as a dash, never as a measured 0.0; (e)
  order: S5 on the five panels first, then the other representatives in descending event order; order enters no
  request or identity; (f) fallback is always "read fresh": a missing, unreadable or unequal identity, a failed
  self-check or any doubt makes that (event, bench) its own class; nothing is skipped without a stored proof; (g) the
  plan (`read-plan.json` per chain: class table, representatives, identity-list hashes; hashes and counts only, no
  test content, no scores) is written once, self-hashed, bound into the run state; resume re-verifies it and pauses
  on a difference (`read_plan_changed`, R44); a zero-call replay must reproduce it byte for byte (the owner's 10/24
  replay rule); (h) everything the pass opens is handled as a read unit handles it: owner consent first, panel
  registry and SpreadsheetBench test qualification by the same path as in typed-v1, no test content outside the
  sealed unit directories, only hashes and counts in open files or logs.
- [D11 as revised by RP1] No carry into the run: the reference row C is read fresh through its D10 class, like every
  other event. typed-v1's C0 and C readings of 2026-11-11 serve ONLY as an earlier, cross-date replicate (noise and
  drift reference, read under `per_cell_plain`) in a separate zero-call, read-only, consent-gated command run after
  the typed-v2 read phase (E).
  Changed by RP1: D11 would have copied typed-v1's finished C unit into `<chain>/carried/typed-v1/<unit>/` with a
  write-once receipt and made C an alias of it; dropped with `T/carry.py`, R58, P9, P10, R61, the CB23 / CB26
  machinery, the 'carried' table kind and tests T13-T15. Reason: four of four verifiers recommended it; carrying C
  saves about 9 to 11 M tokens for both chains (7 to 9 per cent of the economy total) and 2 to 6 h, but makes the main
  contrast "learned library versus hand-written card" cross-date on 8 of 10 bench-chain cells; solver temperature,
  thinking flag, provider route and later ALFWorld turns can be shown equal only by code equality, which is a doubt,
  and doubt means read fresh. The deviation is in the safe direction; the owner is told in plain words.
- [D12] For the read plan: a fresh five-panel reading of the final library; a fresh same-phase baseline for every
  panel whose requests changed; no statistic or decision reads an aliased cell as an independent sample.

Terms. Event = C0, C, S1..S5. Pair = one (event, bench); a chain has 35. Unit = the read unit of a pair
(`test-read-<event>-<bench>`; smoke `practice-read-<event>-<bench>`). Class, representative (the latest event of a
class; only its unit is read), alias, fallback (a pair made its own class because of a doubt), settled (R46).

A. Manifest and chain start (R1..R7, R75).
- R1 [RP13]: `READ_PLANS = ('full', 'economy')`, `READ_PLAN_DEFAULT = 'full'`, `IDENTITY_VERSION =
  'typed-v2-mount-identity-1'`, the record versions and the pause reasons stay defined in `T/readplan.py` and are
  re-exported by `T/__init__.py`.
- R2, R3: `prepare(..., read_plan='full')` puts `read_plan` into the hashed `fields`; allowed pairs (`interleaved`,
  `full`), (`learn_first`, `full`), (`learn_first`, `economy`); `load_manifest` repeats the check. R5: the chain state
  gets `state['read_plan']` with `mode`; a reopened state whose mode differs from the manifest is a hard error. R6:
  with `full` there is no pass, no plan file and no alias; R75 and R79 apply in both modes.
- R4 (CLI): `prepare --read-plan {full,economy}`; `prepare --smoke --read-plan-probe <event>:<bench>`; `run` and
  `smoke` gain `--stop-after-plan` (R77); `smoke` gains `--resume` (it had none); new command `plan-replay` (R47).
- R7 [Q20]: the smoke is prepared with `learn_first`, `economy`, `unit_shared` (D13), `base_card = 'historical'`
  (D17), the run's widths (D15) and the smoke-only field `read_plan_probe = ['C0', 'zebralogic']`, which forces one
  fallback class with the real pass code (on ZebraLogic C0 and C send the same requests under every base and C is
  later, so C0 would be an alias). `prepare` refuses the probe on a real root and with `full`. The real run uses the
  same values without the probe.
- R75 [RP2, Q22]: at every start and resume, in both modes, before `confirm`, the chain builds a credential-free
  record from the solver block it runs with and writes `<chain>/solver-settings.json` with `write_once` (per bench:
  model asked, provider route name, max tokens B, nominal M, thinking / reasoning setting, accepted response model
  ids, read timeout; no URL, key, proxy or credential path); its sha256 is bound in `state['solver_settings_sha256']`;
  a resume whose record is not byte-equal pauses `solver_settings_changed` before any call. Provenance only: it
  enters no request, identity or decision. The plan header binds its hash.

B. The per-item mount identity (R8..R19, R91; RP3, RP8, RP9).
- R9: `identity = canonical_sha256({'v', 'bench', 'public_sha256', 'view_sha256', 'system_sha256', 'programs',
  'selection_sha256'})`. R10 covers every input that can change a request: the system text (`system_sha256` =
  `mount_identity['system_card_sha256']`), the first user text (`public_sha256`), the view (`view_sha256`), the
  selection request (`selection['attempts'][0]` of the capture-mounted record; None when there is no selection or
  `attempts` is empty), the offered programs in library order (their skill sha256 values), and run constants per
  (chain, bench), bound in the plan header (`run_constants_sha256`; the API parameters through
  `solver_settings_sha256`).
- R12, R14 [RP8]: not hashed: the type id (the identity hashes what the type selects, never the id), skill ids,
  source, distances, event, arm name, unit name, cell tag, package label, the row's `step`, library and type-map record
  hashes, container name, lock mode, widths. The descriptive fields are stored beside the identity in the sealed file
  and never decide a class. The unit label reaches the container only as `package_sha256`, which the bound worker
  echoes and never passes to procedures; test T7 (bound driver) must pass before the smoke; if it fails, items with
  offered programs carry the event in their identity.
- R16 [RP9]: one routing path, no third mount implementation: per (event, bench, item) the pass calls
  `services.identity_fn` (= `mount.mount_identity`, step 5m) and the real `services.mount_fn` with the capture
  selector; both must agree on the system hash and the offered ids, else fallback `identity_disagreement`; any other
  exception of these calls is fallback `identity_exception`; stops and pauses propagate. R11: read arms are C0, C and
  F only, so `forced` is always None.
- R17, R18: `capture_selector` returns a fixed non-ok receipt, so `_select` records its first request hash and sends
  nothing. The pass makes no model call and touches no ledger; it costs machine time only (one view per item, two
  embedder batches, the ALFWorld preparation resets, and the SpreadsheetBench qualification when the pass is the
  first caller).
- R19 [RP3]: exact first-request hashes are MANDATORY for every event and every item without offered programs on
  SearchQA, OfficeQA, ZebraLogic and SpreadsheetBench, captured through the injected `solve_fn` with a capture call
  that keeps the first send's sha256(system NUL user), charges nothing and returns no answer; none on ALFWorld (RP3
  option 1 a: this narrows D10 b's full request hash of C0 and C to the four benches); a capture without exactly one
  send makes that pair fallback `capture_failed`.
- R91 [D17; Q23 answered yes in RP12]: the identity hashes the system text, so the classes are right under both
  `base_card` values; only which events share a class changes. Binding case for the run, R91 (b): under
  'historical' an unknown item and a typed item without a card both mount `historical_text(b)` (the C request), so a
  never-changed bench has {C0} > C0 and {C, S1..S5} > S5; a bench changed at step k has {C0}, {C, S1..S(k-1)} >
  S(k-1) (k = 1: {C} alone) and {S(k)..S5} > S5; a type-map-only change stays one class. Under 'format' (golden
  tests) C0 and C exchange roles (R91 a). ZebraLogic: C0 and C send the same requests under every base, so
  {C0, C, S1..S(k-1)} and {S(k)..S5} (R91 d). A bench changed by more than one step, or by a later member's skill (F14,
  D16), gets one more class per change. Case (c), the old unknown branch under 'historical', is not built.

C. The planning pass (R20..R34, R76..R81, R92; RP6, RP11, RP13).
- R20: under `economy` only. Run order: `confirm`, `freeze_anchor`, `learn(1..5)`, the pass (pseudo-unit
  `read-plan`), the replay (R76), the optional stop (R77), `read_classes()` (D). Before anything is opened the pass
  persists `phase = 'read'`, `current_unit = 'read-plan'` and the seven `read_mounts` entries. R21: consent first on a
  real root (`reads.consent`); without consent nothing is opened and the chain pauses as for a read unit.
- R22..R26: panels are opened through one panel path, `reads.open_panel` (R24, extracted from `_read`), with the
  arguments `_read` passes and, for SpreadsheetBench, under the heavy lock; the first caller writes the write-once
  registry entry and runs the qualification, later callers verify (no new lock); a failed qualification's route-B
  `Pause` propagates and is recovered as today. ALFWorld views come from the preparation resets, wrapped as in 3.6
  under `unit_shared` (R23). The smoke uses the held-out practice panel, with no consent and no registry entry (R25).
  One view per item and one vector batch per bench over exactly the list `_read` embeds (R26).
- R27 [RP13]: C0 and C use the s0 state; S<k> uses the state named by `s<k>/frozen.json` through `load_frozen(k)`,
  never the chain's live library. Integration requirement [RP13]: the pass mounts every item with exactly the frozen
  library and type map it records (`identities_record(frozen=...)`, `item_components(arm=...)`); a test proves that
  the objects passed to the mount calls are the loaded frozen ones.
- R28, R29: per (bench, event) `identity_list_sha256` over `[[sha256(item id), identity], ...]` in sorted id order,
  and `first_request_list_sha256` (null on ALFWorld). Two events are one class iff both have status `ok`, their
  identity lists are equal and their first-request lists are equal wherever both are non-null; two `ok` events with
  equal identity lists but different first requests both fall back with `first_request_mismatch`. [RP13]: the literal
  reading holds: when one event of a group of equal identities has different first requests, the whole group is read
  fresh (an incomplete identity is signalled; any doubt means read fresh).
- R30: the vector batch runs twice per bench in two subprocesses; an S event whose two identity lists differ falls
  back with `embedder_unstable`; descriptive flips with an equal identity are only counted.
- R31, R81: fallback reasons come from the one closed tuple `READ_PLAN_REASONS` (also every void reason, replay detail
  and recovery outcome; the recovery outcome names of the core module are adopted [RP13]): `identity_exception`,
  `identity_disagreement`, `capture_failed`, `embedder_unstable`, `first_request_mismatch`, and in the smoke only
  `smoke_probe`. A fallback pair is its own class and is read fresh; no fallback removes a read. Exceptions are stored
  by class name only.
- R32, R78: sealed, under `<chain>/test-read-plan/` (smoke `practice-read-plan/`): `inputs-<bench>.json` (sorted ids,
  view hashes, the ALFWorld views, both vector runs) and `identities-<bench>.json`; open: `<chain>/read-plan.json`
  (hashes and counts only, no time stamp, no host name, self-hashed `plan_sha256`); then the binding in
  `state['read_plan']` (`plan_sha256`, `file_sha256`, `bound_at`) and `mark('read-plan')`. The header binds the
  manifest record hash, `base_card` by name, the seven frozen receipts, `solver_settings_sha256`, per bench
  `run_constants_sha256` and `registry_sha256`, and the sha256 of every sealed file. Re-runs and replays load the
  ALFWorld views and both vector runs from the hash-checked inputs file and recompute only the other views, which must
  equal their stored hashes; so the byte equality of D10 (g) tests the rule, the frozen states and the code, not the
  embedder.
- R33 [RP11, Q24]: pauses and stops raised by called code (typed `Paused`, `units.Stop`, route-B `Pause`, stop kinds)
  and every exception of the panel path propagate unchanged; a non-stop exception of a per-item identity call is a
  fallback; only the pass's own detected inconsistencies pause `read_plan_failed`, with a fixed code
  (`inputs_mismatch`, `view_mismatch`, `sealed_file_mismatch`, `plan_file_mismatch`, `plan_self_check`); a non-stop
  exception raised by the pass's own code outside the panel path also counts as `read_plan_failed`, code
  `pass_exception` (class name only) [Q24 option A]. The first recovery re-runs the pass; a second failure with the
  same code voids the plan (`void_reason = 'pass_failed'`) and all 35 pairs of the chain are read fresh in the economy
  order.
- R76 [RP6, Q21]: right after the binding and before any read unit, the chain runs `run_typed.py
  --machinery-snapshot <bound snapshot> plan-replay ...` as a child process (fresh interpreter, same bound machinery,
  `PYTHONHASHSEED` explicitly different from the parent's and recorded); `equal` lets the chain go on; `different`, an
  error or a timeout pauses `read_plan_changed` (detail `replay_different` or `replay_error:<code>`); a second replay
  error with the same code voids the plan (R44 d).
- R77 [RP6]: `--stop-after-plan` raises the recorded pause `stopped_after_plan` after an `equal` replay (exit 5). The
  real run does not stop after the plan; the smoke uses the stop once.
- R79: learning is closed once reading has begun (3.6). R80: `write_once` = a temporary
  `.<name>.<pid>.<16 hex>.part` file, fsync, `os.link`, unlink; equal bytes are accepted, different bytes raise
  `WriteOnceMismatch`, mapped to the caller's reason; readers accept only the closed names; stale `.part` files are
  removed by the next pass or settling. Used for the solver settings, the sealed files, the plan and the alias records.
- R92: three fakes-only kill points (`after-first-inputs`, `after-plan-file`, `replay-child`) through
  `services.checkpoint`, used by `smoke --fake --fake-kill-at <point>`; real services have no checkpoint.

D. The read phase (R35..R47).
- R35, R36: `_Run.read_classes()` reads under `economy`; nothing opens a panel before the pass has set the phase.
  First sweep `for event in (S5, S4, S3, S2, S1, C, C0)`: the benches where the event represents an unsettled class;
  final sweep: every pair still unsettled (voided aliases, a void plan), read fresh as its own class, again S5..C0.
  Each pair is read fresh at most once.
- R37, R38: per event the frozen state is bound (`load_frozen`, `bind_read`) and `reads(event, benches=...)` runs the
  unchanged read path, so a fresh unit under `economy` is the unit `full` would run (same name, tags and requests;
  T18). An alias pair never runs: no unit directory, cell, mirror or ledger entry.
- R39: when the representative's unit is complete: the post-read check R41; if it passes, for every unsettled member
  M: check `read_mounts[M]` against the plan (else pause `read_mount_changed`, nothing written for M), write the
  alias record `<chain>/read-alias/<M>-<bench>.json` with `write_once`, set the state entry `{kind: 'alias', status:
  'alias', alias_of, items, alias_sha256}` and mark `alias-<M>-<bench>`. The state entry is the only authority.
- R40: only fresh units charge. Worst case = `full` (35 units per chain), for which the caps are sized; best case 9
  fresh units per chain (S5 on five panels plus one more class on each of the four benches whose C differs from C0);
  typical for the run (R91 b): a non-ZebraLogic bench changed once 3 fresh units, unchanged 2; ZebraLogic 2 or 1.
- R41 [RP3, RP13]: post-read check inside the read path, counts only: per planned item the representative's cell is
  compared with the plan on the hashed components (system, selection, offered program hashes, `public_hash`, and the
  first request where planned); passed iff all items are equal. Infrastructure unknowns inside a complete
  representative do not block the alias (RP3 option 2 a): its `unknown`, `infrastructure_unknown` and
  `configuration_errors` counts go into every alias record and are shown beside every member; `verify_alias`
  compares these counts with the representative's mirror (R44 a, RP13).
- R42 [RP10]: a failed check is a fallback without a pause; it voids EVERY alias of that bench, settled or not
  (records archived under `read-alias/archived/`, state entries `void_alias`); those pairs are read fresh, bounded by
  the `full` plan; recorded and reported as a defect signal.
- R44: at every start and resume with a bound plan: file bytes, self-hash, manifest and sealed-file hashes as bound
  (else `read_plan_changed`); frozen receipts and solver settings keep their own reasons (`frozen_state_changed`,
  `solver_settings_changed`); alias records are verified (else `read_alias_invalid`). Recovery archives only the
  plan-owned files that failed; a lost sealed file voids the plan (`sealed_file_invalid`); a lost plan file is
  restored by an in-process recompute that must hash to the bound value; then the child replay decides; a void plan
  turns every alias into `void_alias`, read fresh in the final sweep.
- R45: every resume consumes one owner recovery record (`recovery.json`, under the standing delegation of 11/11), a
  crash included; the resume points P1..P12 (P9, P10 retired with the carry) are tabled in the spec.
- R46: before `state['complete']` all 35 pairs are settled: fresh (`read-` marker, complete mirror, sealed
  `done.json` with `cells == expected_cells` = the plan's item count) or alias (`alias-` marker, state entry, verified
  record, representative complete); else pause `read_plan_incomplete`. Then `step-0`..`step-5` are marked, as under
  `full`.
- R47, R47b: `plan-replay --root R --chain X [--smoke] [--fake]`: `own_root`, the bound start checks, consent first on
  a real root, then the pass in memory with zero calls from the stored inputs; panels are re-opened WITHOUT the heavy
  lock after checking that the five registry entries and the qualification pointer exist (else `different`, code
  `qualification_missing`); compares bytes with the plan and every sealed identity file; prints `equal` / `different`
  with counts, exit 0 / 3; a re-embedding count is information only. Every error is caught and only `{command, chain,
  verdict: 'error', error_class, reason}` is printed, never a traceback.

E. The post-read replicate command (R82..R88; RP1). Not part of the run; built after launch. A zero-call, read-only,
consent-gated command [RP1]: `replicate --root <typed-v2 root> --chain <G|D> --source <typed-v1 root>` runs only on a
complete typed-v2 chain, needs a consent that is valid in both roots (R83), reads both roots and writes neither. It
opens typed-v1 sealed cells, which F7 keeps unopened until the typed-v2 code and run plan are frozen. It matches
typed-v1's C0 / C cells to the typed-v2 fresh cells that read the same requests by cell tag and
`request_sha256[0]`, checks completeness, registry, machinery record, judge versions and the observed settings, and
prints per (chain, event, bench) agreement, flip and unmatched counts under the heading "earlier replicate (typed-v1,
read <window>, lock per_cell_plain): noise and drift reference, never a baseline". It prints counts and verdicts only,
never test content: no item id, text, reply or per-item score; it parses only the named keys, and its tests grep every
output for planted ids, texts and score keys (R86, R87). An error prints only the fixed R47b record `{command, chain,
verdict: 'error', error_class, reason}`, never a traceback. It never writes into the typed-v2 run state and never
becomes a baseline, a table row or a readout input. About 180 lines of code and 220 of tests (T27; the test source is
made by typed-v1's own `prepare --smoke` from `git archive 9ca2754`).

F. The readout (R63..R74, R89, R90; RP4, RP5, RP7).
- R63, R64: a resolver gives every pair `{source: fresh | alias | void_alias | pending | invalid, of, class,
  independent}` from the state, checked against the plan and the alias records; `independent` is true only for a
  fresh unit. Alias pairs are never loaded as units, so a consumer that does not dereference them prints a dash,
  never a zero. With `full` every pair is fresh.
- R65, R66: a fresh pair shows its value; an alias cell prints `=<event>` and no number of its own: the
  representative's reading stands in the same column (D10 d); beside it the representative's `u/i/c` (unknown /
  infrastructure / configuration counts from the alias record), zeros included; a legend under each table reads
  `=X u/i/c: same requests as event X (not read again)`. Every exported grid value is an object `{value, source, of,
  independent, kind}`; an alias has `value: null` and `of: <event>`, a structural zero `kind: 'structural'`. Closed
  mode lists the alias pairs from the alias records as `same requests as <event>`, with the same counts (R65).
- R67, R68 [RP5]: a delta between two events of one class prints `-` ("same requests, not measured"), never `0.0`;
  between classes it is computed from the two fresh representatives and labelled `requests: identical | different
  (d of n items) | unverified` by first inputs; an all-identical delta is a noise sample, not an effect; a contrast
  that is not same-phase goes to a reference block (point value only, with both units' time ranges). Every "against
  C0" number uses the fresh representative of C0's class, every "against C" number that of C's class; no cross-date
  number enters any table of this readout. R68 is a rule of the typed-v2 readout (spec 1.F, typed-v2 events only); the
  cross-run, cross-date comparison rows that D17 asks for are a separate report block (6), not a readout table.
- R69 [RP7]: `in-run replicates: <n>` is printed beside every contrast (0 unless a fallback read two identical
  classes); the practice-side gate noise of each step (`se_points`, `tau_points` of `s<k>/noise.json`) is shown beside
  the read tables. No same-phase ZebraLogic replicate is built (about 1.0 to 1.2 M tokens per chain; owner option).
- R70 [RP4]: values reach the formulas through the resolver; a term inside one class is structural.
  `forgetting` / `forgetting_after_home`: if an earlier event shares the final event's class, print the measured
  maximum over the other classes when it is above 0, else `-` with the count of by-construction terms; without such
  events, the signed measured maximum. Every macro row prints (a) the five-bench mean with structural zeros entered
  as 0 (`k of 5 structural`) and (b) the mean over measured benches (`n of 5`); a split-phase term enters no mean and
  no maximum (`mixed: k same-phase, m split, no mean`).
- R89, R90 [RP5]: same phase = equal sets of returned model ids over all sends of the two units AND no splitting
  recovery between them; a recovery does not split iff its pause lasted at most 24 h and its record carries
  `same_phase: true` (written before the resume, blind to results, stating that no code, configuration, provider route
  or credential changed); a missing field splits; a crash without a pause record is bounded from stored file times,
  never treated as 0 h. 24 h instead of 6 h: the read phase itself spans most of a day and an overnight pause on an
  unattended machine must not void it. Every fresh unit's time range and model-id counts are printed.
- R71..R74: costs count fresh units only, plus one line `economy: <a> pairs aliased, <f> fallbacks, <v> voided
  aliases` and no "tokens saved" figure; mount checks run over fresh units, aliases get planned columns; a classes
  block per bench; the status adds phase, mode, short plan hash and read counts; an `invalid` or `pending` pair shows
  no value; an `economy` root whose plan fails its self-hash renders no read table. Under D17 the readout keeps both
  `S<k> - C0` and `S<k> - C` (spec 5.5); the readout edits of this area come last on `T/readout.py`.

G. Records: section 4.1 (plan, sealed files, alias records, solver settings, state keys); the open names hold none of
the `FORBIDDEN_PATH_WORDS`; the sealed name `test-read-plan` contains `test` on purpose and is written only with
`allow_sealed=True` (spec 3.8).

H. Placement and size. `T/readplan.py` is the one new module of this area. Its pure core is built [RP13; impl
rp-core]: branch typed-v2-readplan-core, commit 3f7e933 on base 8375ecb, 1,410 lines, 56 tests in
`tests/test_typed_readplan_core.py`, one adversarial review (four minor findings, fixed); it imports only `T/__init__`,
`T/library` and `T/units` and holds the identity records, classes and representatives for both base values and
ZebraLogic, the sealed inputs and identity records, the self-hashed plan with `write_once` and a strict canonical
load, the byte-equal replay comparison, the alias records and the open-record checks. The spec's change list
(section 2) estimates the rest at about 1,155 lines of code and 1,395 of tests in total, counting the module at about
460 lines, which the built core already exceeds. `T/mount.py` gets nothing from this area (step 5m owns `_route` /
`mount_identity`, step 5b owns `base_card` and the unknown branch); `T/reads.py` only the extraction of `open_panel`;
in `C` nothing of `read_one`, `read_event`, `confirm` or the learning code apart from R79's guard. No request text,
cell tag, unit name, ledger identity or library / type-map record changes.

I. Risks (spec section 6) and open checks. K-A: a wrong identity would alias two different request sets (guards: one
routing path, mandatory first requests on four benches, R29 c, R41 on every representative, RP10, the replay;
residual: on ALFWorld and for items with offered programs a member's proof is the equality of two values of one
tested function). K-B: no in-run replicate (stated beside every contrast). K-C: the read phase spans most of a day;
S5 is read first, earlier states later; same phase by R89. K-D: a fallback raises the cost up to `full` without a
pause; with D16 and D17 the worst case is about 82 and 85 per cent of the caps. K-F: ALFWorld machine time in the
pass. K-G: embedder drift between the pass and a representative's own unit (R41 fails and RP10 voids the bench's
aliases; residual: a member's own routing is not re-checked at read time). K-H: the pass's real consent / registry /
qualification path and its live ALFWorld resets first run in the real run (the smoke reads practice panels and skips
resets; T12 covers them with fakes; a failure costs a pause, not tokens). K-E retired with the carry. Open checks:
N13 `X/policy.py` was not opened (the R14 residual); N15 that `evaluation._with_views` accepts a reset function
returning stored views (R47); N16 embedder determinism across processes is not measured (the replay's information
count measures it). N14 (`mount_identity` did not exist) is closed by step 5m.

## 4. Records and identity

**4.1 Changed records.**

| Record | Change |
|---|---|
| `manifest.json` (sealed at prepare) | `version`, `configuration` = `typed-v2`; new `machinery_code = {snapshot, bound, typed_from, list, list_sha256, files, data_list_sha256, symbols}`, `draw_keys` [O4], `caps`, `widths`, `learn_widths` [D15], `schedule`, `memory_lock` [D8; run and smoke `learn_first` D9, `unit_shared` D13], `base_card` [D17], `read_plan` [D9] (+ `read_plan_probe` in a smoke manifest only [Q20]), `provenance.typed_code`; `tau_rule` gains `repeats`, `se` |
| chain state | `version`; new `machinery_code`, `container_scope`, `base_card` [D17; impl 5b], `schedule`, `phase` (`learn` / `read`), `read_mounts`; `solver_settings_sha256` [RP2]; `read_plan = {mode, plan_sha256, file_sha256, bound_at, replay: {verdict, at, hash_seed}, fallbacks, failures, void, void_reason, recoveries}` [D10 g; R5, spec 3.6]; `reads[event][bench]` gains `kind` (`alias`, `void_alias`; fresh when absent) and `status: 'alias'`; `done_units` gains `read-plan`, `alias-<event>-<bench>` (never `read-...`) and, at the end, `step-0`..`step-5` (R46) |
| `s<k>/noise.json` | arms `B#1..3` [D17] (mount arm `B`), `repeats`, `per_item = [[item, S], ...]` [O12], `variance_sum` (Q), `se_points`, `tau_points`, `minimum_points`, `multiplier`, `unknown_final`, `reruns`, `scores: 'binary'` [O11]; the pair fields (`minimum_pairs`, pair counts) go |
| `plan.json` in every gate unit | new, write-once: unit, arm, labels, repeats, items, identity list sha256, `shared_from` (as built also bench, step, the per-item identity digests and `compared` [impl 5w]); member gate units have one too [D16 b] |
| decision records (card round, program, no-harm) | `repeats`, `n`, `difference_sum` (D), `variance_sum` (Q), `gain_points`, `se_points`, `tau_points`, `minimum_points`, `multiplier`, `better`, `worse`, `tied`, `baseline = {unit, arm, shared}`, `candidate = {unit, arm}`, `baseline_selected` [O5], `per_item = [[item, S_B, S_K], ...]` [O12], `unknown_final`, `reruns`, `scores: 'binary'` [O11]; `excluded_unknown` is kept and always 0 (the round-2 card request reads it, `W:222` `revision_result` [I]); programs add `proposal`, `status`, `fired_items`, `fired_cells = [[item, count], ...]` [O6, O12], `difference_sum_fired` and the informational `se_points_fired`, `se_points_scaled` [PG]; a shared type adds per member: items, D, better, worse, tied, `gain_points`, `se_points`, `tau_points`, `no_regress`, units, labels, `baseline_selected` [D16 c] |
| `s<k>/decisions.json` | `tau_points` stays the value of `s<k>/noise` (now `B@noise` [D17]); every decision row carries its own tau, Q and baseline; `limits` has the five keys of 3.2; a skill's origin stores the tau of its own decision (as built also `repeats`, `se_points`, and for programs `gain_points_fired`, `fired_items` [impl 5w]) |
| `s<k>/programs/proposals.json` | rows `{n, status, slot, procedure, screen, first_screen, fix, request_sha256, read, format_retry}` |
| card write result | `card_limits`; attempt rows gain `bullets`; `chars` = content characters of the learned text (C is never counted [D17]) |
| writer requests | card writer request and proposal payload: key `base_card = {meaning, text}` under 'historical' [D17]; member example blocks, member sources and rule for a shared type [D16 a] |
| `s<k>/member-<b'>-*` units | new [D16]: `member-<b'>-outcomes`, `member-<b'>-outcomes-card` (single-run learn units), `member-<b'>-base`, `card-r<j>-member-<b'>`, `program-<i>-member-<b'>` (gate units with repeat labels and `plan.json`) |
| `s<k>/frozen.json` | new (3.6) |
| `<chain>/solver-settings.json` | new [RP2, R75]: version `typed-v2-solver-settings-1`, chain, per bench `{model, route, max_tokens, nominal_tokens (null for G), thinking, reasoning_effort, response_model_ids, read_timeout}`, `record_sha256`; open, write-once, credential-free |
| `<chain>/read-plan.json` | new [D10 g, R32 b]: version `typed-v2-read-plan-1`, `identity_version`, chain, smoke, schedule, read_plan, base_card, `manifest_record_sha256`, `solver_settings_sha256`, events, order, `frozen` per event (step, record and file hashes of library and type map, receipt hash), per bench `{items, item_set_sha256, registry_sha256 (null in a smoke), run_constants_sha256, inputs_sha256, identities_sha256, embed: {runs: 2, descriptive_flips}, events: {event: {arm, status, reason, identity_list_sha256, first_request_list_sha256, captured, typed, unknown, with_card, with_programs}}, classes: [{id, members, representative, both list hashes}]}`, `read_order`, `counts = {pairs, fresh, alias, fallback}`, `plan_sha256`; open, write-once, hashes and counts only, no time stamp |
| `<chain>/test-read-plan/inputs-<bench>.json`, `identities-<bench>.json` (smoke: `practice-read-plan/`) | new, SEALED [R32 a, R78]: inputs = sorted item ids, one view hash per item, ALFWorld views or null, both vector runs or null, `views_sha256`, `vectors_sha256`; identities = item ids, `inputs_sha256`, per event `{arm, step, status, reason, identity: [...], first_request: [...] or null, components: [{public_sha256, view_sha256, system_sha256, selection_sha256, programs, type, source, unknown_reason, card_skill, offered}]}`; each with `record_sha256` |
| `<chain>/read-alias/<event>-<bench>.json` | new [D10 d, R39]: version `typed-v2-read-alias-1`, chain, event, bench, kind `alias`, `representative = {event, unit}`, items, `identity_list_sha256` and `first_request_list_sha256` as `{member, representative}` (the proof), `plan_sha256`, `check = {items, equal, unequal}`, `representative_aggregate_sha256`, `representative_counts = {unknown, infrastructure_unknown, configuration_errors}` [RP3], `record_sha256`; open, write-once, no time stamp; voided records move to `read-alias/archived/<event>-<bench>-<n>.json` |
| library, type map | version literals `typed-v2-library`, `typed-v2-typemap` |
| cell rows of gate units | `arm` holds the label `<arm>#<r>`; the mount record keeps the plain arm |

`gates.recompute(record)` must reproduce every stored decision from its `per_item` list. Stored records, not fresh
computations, are returned on resume.
As built [impl 5s, 5w]: the arm references of a decision record are named `baseline` and `candidate_arm`, each
`{unit, arm, shared_from}`, because a program record's `candidate` is its slot (3.2); `baseline_selected` is in every
comparison; `mean_points` is kept as an alias of `gain_points`; a description failure keeps `accepted: false`,
`description_failed` and stores `gate_verdict`, which `chain.recompute_decision` restores before `gates.recompute`.
Open read-plan files hold hashes and counts only; item ids appear only in the sealed `test-read-plan/` files; no
`carried` directory exists [RP1].

**4.2 Requests that change against typed-v1 (complete).** (1) card writer, attempt 2 after a length failure: the
typed retry sentence; (2) card writer, round 2: `previous_card` up to 4,500 characters and `result` numbers computed
on item means with this decision's tau; (3) the engineer system text, both purposes, five benches; (4) the fix user
message: failed source and screen evidence added; (5) the new format-retry request; (6) up to 5 writer calls per
programs unit; (7) later solver system messages and describer requests carry cards of up to 4,500 characters; (8)
each gate cell's request is sent R times and the no-harm baseline is the noise unit. Unchanged: the first-attempt
card request, a content-violation retry, the construction of solver and selection requests, the step label, the
draw keys, the read-unit requests.

Changed by D17: under `base_card = 'historical'` (the run and the smoke) the "unchanged" list above no longer holds
for (i) the first-attempt card request, which carries the base-card block, and (ii) the solver system message of every
learned mount and of every S<k> read cell on the four non-ZebraLogic benches, which composes on C. The list holds
under 'format' (golden tests) and on ZebraLogic. The construction code of solver and selection requests is
unchanged; only the card text it receives differs.
Request changes added by the merge: (9) [D17] every B cell sends C (under 'historical'); every learned or S-event
mount sends `T + CARD_JOIN + C`, or C alone for an unknown or card-less item [Q23]; (10) [D17] the card writer
request (both attempts, both rounds) and the proposal payload carry `base_card = {meaning, text}`; fix and
format-retry requests do not; (11) [D16] for a shared type the writer requests carry member example blocks and name
the member sources and rule, the revision summary adds member counts and points, and member units send F and
candidate runs on the members' learn and gate slices; (12) [D10] the planning pass sends nothing (R18); under
`economy` a fresh read unit sends exactly what the same unit sends under `full` (R37, T18) and an alias pair sends
nothing; (13) [D13, D15] lock mode and widths change no request. The R repeats of a gate cell remain identical
requests sent fresh.

**4.3 Pins (all verified by `machinery.check`, 3.5).** `engineer_prompt.PINS` (10) with `PROMPT_VERSION`; `cards`
retry texts and `COPIED_SOURCE_SHA256`; `replies` texts with `READER`; `machinery.LIST_SHA256` and
`DATA_LIST_SHA256`. Existing tests that pin typed-v1 texts or versions are updated, never deleted.

Added by the merge: the two base-card labels (card writer in `W`, engineer in `T/engineer_prompt.py`) are pinned by
sha256 in `tests/test_typed2_base.py`; the ten engineer system texts, `PINS` and `PROMPT_VERSION` are unchanged by D17
[impl 5b]; the fifteen `PROBLEM_SENTENCES` are pinned [O8]; `DATA_LIST_SHA256 =
'75ad90d48b644a1dddb43fc5e83edb855418229bd9930eed4e3c6f073b337a48'` [F11]; the `scripts.*` modules the bound run
imports join the checked machinery in step 7 [Q19, RP12]; the read plan pins `IDENTITY_VERSION`, the record versions
(`typed-v2-read-plan-1`, `typed-v2-read-alias-1`, `typed-v2-solver-settings-1`) and the closed `READ_PLAN_REASONS`
tuple [R1, R81]. As built, check 6 is a stub until step 7 [impl 1m].

**4.4 What refuses what.** `prepare`: a root name not matching `ROOT_NAME`, an unknown `schedule` or `memory_lock`.
`own_root`: any root, manifest or state of another typed version (every command and `read_panel`). Library and type
map loads: another version literal. `bind_machinery`: a snapshot with a `typed` package. `machinery.check`: any
difference in lists, loaded files, names or pins. `start_checks`: a changed `T/` file or launcher since prepare, a
different machinery record. Ledger: a changed cap. Gate: `shared_arm_mismatch`, `gate_cells_unknown`,
`incomplete_unit:missing_cells`. Schedule: `frozen_state_changed`, `read_mount_changed`. Consent: unchanged, exactly
the six route-B fields (`T/reads.py:100-108` [V]).

Added by the merge. `prepare`: an unknown `base_card` or `read_plan`, `economy` without `learn_first` [D9], a
`read_plan_probe` on a real root or with `full` [Q20]; a refused machinery leaves no root [impl 1b]. `load_manifest`:
a missing or unknown `base_card` [D17; impl 5b], a forbidden schedule / read-plan pair (R3), any sealed constant or
code identity that differs from the code [impl 1a, 1b]. Chain: a resume with another `base_card` [impl 5b]; a state
whose read-plan mode differs from the manifest (hard error, R5); `limits['gate_repeats']` other than an int >= 2 and
a `tau_rule` other than `prepare.tau_rule()` [impl 5w]. Pauses: gate `gate_plan_changed` [impl 5w]; start and resume
`solver_settings_changed` [Q22]; read plan `read_plan_failed`, `read_plan_changed`, `read_alias_invalid`,
`read_plan_incomplete`, `stopped_after_plan` (3.7); `noise_uncalibrated` is gone [impl 5w]. Rejection reason, not a
pause: `member_harm` [D16 b]. `plan-replay`: verdict `different` with code `qualification_missing` when a registry
entry or the qualification pointer is missing (R47). Consent: unchanged, exactly the six route-B fields; the note of
every typed-v2 consent names the run root and states the read plan, an operations rule [O9].

## 5. Tests

All local runs: `<python> -m pytest -q -p no:cacheprovider <files>` with
`TMPDIR=/tmp/typed2-neutral` (a plain name; `/tmp/typed-neutral` in ten test files becomes `/tmp/typed2-neutral`).

- `tests/test_typed_cards.py` (new): counting without the newline (3,000 accepted, 4,500 accepted, 4,501 rejected),
  bullets, each retry sentence, the join, the room rule, equality of `RETRY_FRAME` / `RETRY_SHORT` with the bound
  texts, a drift corpus comparing `content_violation` with the frozen function, `COPIED_SOURCE_SHA256`.
- `tests/test_typed_engineer_prompt.py` (new): the ten pins; every list in the text equals the bound list; for each
  of the 22 rule rows a legal and an illegal example run through the real `policy.check` (the pair table of
  `spec/engineer.md` 2.6); evidence rows; `_bounded_entry`; the hooks check; the prompt contains `REPLY_FORMAT`. Its
  one case that patches a bound list uses the `monkeypatch` fixture and never runs in the bound child process.
- `tests/test_typed_replies.py` (new): fixture table of twelve reply shapes (the two F6 losses among them); parity
  with the frozen reader on well-formed replies; never raises; never executes; tolerance does not weaken the screen;
  retry request text per problem code; budget; pins.
- `tests/test_typed_core.py`, `test_typed_chain.py`, `test_typed_e2e.py`, `test_typed_readout.py` (gate): the integer
  forms equal the D5 formulas (property test, binary scores only [O11]); the +11.0 / 20 better / 9 worse case; fired
  subset; no-regress; each decision row stores and follows its own tau; `recompute`; sharing cases (a) to (f) and
  `plan.json` on resume; `shared_arm_mismatch`; a deterministic model-side unknown cell is scored 0, never re-run
  and counted; an infrastructure cell is re-run once, archived and counted per arm; a double fault never draws a
  finished cell of another unit; missing cell pauses; `no_harm` returns the stored record.
  Changed by O11: "also non-binary at 1e-9" is not built; the property test covers binary scores only (as built: 2,000
  random cases, an exhaustive enumeration of small slices hitting all four sides of tau, and the +11.0 / 20 better /
  9 worse case [impl 5s]). With D17 the noise and no-harm cases run on `B#1..3` and `B@noise`.
- Promotion and resume: a dropped row never reaches a gate unit and a promoted third row does; an interruption
  inside the promotion loop, and one after the format retry, keep every send in the calls file and send at most 5
  calls per attempt; a golden test of the round-2 card request bytes.
- `tests/test_typed2_identity.py` (new): literals; `own_root` refusals for each command and for `read_panel`; a
  typed-v1 library, type map, manifest and state are refused; draw keys give the typed-v1 slices; caps come from the
  manifest; container scope gives different tags for the two versions; a cap projection that includes the ALFWorld
  step.
- `tests/test_typed_schedule.py` (new, 13 cases): both orders produce the same requests and the same unit names;
  frozen receipts; both pauses; lock choice; `prepare` options. `tests/test_typed_cli.py`, `test_typed_reads.py`
  updated for versions and options.
- `tests/test_typed2_machinery.py` (new) with the child driver `tests/typed2_bound_driver.py`, the ONE bound harness
  for all areas: a stand-in snapshot is built under `/tmp/typed2-neutral/<id>/snap` from the 564 listed files and
  the 64 data files, and a fresh interpreter runs `bind_machinery` and then imports every `T/` module, calls
  `machinery.check(real=True)`, renders the ten prompts, screens a card and reads a reply. Guard cases: an altered
  listed file, an altered data file, an extra module under this tree's `X/`, a missing private name, a snapshot
  with a `typed` package. The same driver is run once on dl against the real snapshot before the smoke (Python 3.11
  there, 3.13 on the Mac).

Added by the merge (test files as built or planned; same command; the full typed selection is
`tests/test_typed_*.py tests/test_typed2_*.py`):
- `tests/test_typed2_services.py` (step 1b, 14 cases): start checks, container scope (typed-v1 and typed-v2 tags
  differ), caps from the manifest, and the learning widths [D15]: learning units at `LEARN_WIDTHS`, read units at
  `WIDTHS`, and the same smoke at the read widths sends the same requests in the same unit order.
- `tests/test_typed_gate_stats.py` (step 5s, 18 tests): the integer forms against the D5 formulas in `Fraction`,
  binary only [O11]; record key sets and JSON types; `recompute`; purity of `T/gatestats.py` [MP].
- `tests/test_typed_mount_identity.py` (step 5m): 50 golden digests of `mount()` records and selection requests
  before and after the split; `mount_identity` equals the fields of `mount()` and makes no solver, router or
  embedding call. Since 5b also the arm `B` on five benches.
- `tests/test_typed2_base.py` (step 5b, D17, 16 tests): under 'format' every request and cell digest of the run before
  D17 (cell tags differ only by the label B); under 'historical' every B cell sends C and every learned cell sends C or
  `T + CARD_JOIN + C`; unknown and card-less items mount byte-equal C under 'historical' and C0's text under 'format'
  [Q23]; read arms C0 and C keep their mounts; writer blocks only where they add; a 4,400-character card passes beside
  C; the base sealed, a missing or unknown value refused, a resume with another base refused; CLI `--base-card`.
- `tests/test_typed2_gate.py` (step 5w, 12 tests): the gate cases of this section through the real chain with
  `B#1..3` and `B@noise`, `recompute` of every record, n * R cells per fresh gate unit, sharing cases (a), (b), (c),
  (e), (f), `gate_plan_changed`, `shared_arm_mismatch`, and per-(unit, tag) reruns. Case (d) has no dedicated test
  yet [impl 5w].
- `tests/test_typed2_shared.py` (step 5x, D16, planned): SearchQA and OfficeQA in one type: member learn and gate
  units, member examples in both writers, `member_harm` naming the bench, the member baseline after an accepted card
  is that card's member runs (`baseline_selected`), `recompute` reproduces the member verdicts, related gains in the
  readout, no gate item in any writer request; golden: one bench per type gives every request, unit and cell of 5w
  [D16 d].
- `tests/test_typed_readplan_core.py` (read-plan core, 56 tests): identity records, classes for both base values and
  ZebraLogic, sealed records, plan bytes and self-hash, `write_once`, the replay comparison, alias records, open-record
  checks.
- Read-plan integration (spec 4.2): new `tests/test_typed_readplan.py` with T1..T6 (T3..T6 under both base values;
  the binding variant of T6 is Q23 yes), T8..T12, T18, T19, T21..T23 (T23's reason check covers the read-plan parts
  of the state only [RP13]), T25, T26, and the RP13 test that the pass mounts with the loaded frozen objects; T16, T17
  in `tests/test_typed_schedule.py` or `tests/test_typed_chain.py`; T24 and the three kill points in
  `tests/test_typed_cli.py`; T20 in `tests/test_typed_readout.py`; `mount_identity`, the capture and T7 under
  `bind_machinery` in `tests/typed2_bound_driver.py` (spec section 2; T7 must pass before the smoke [R14]; who writes
  these lines follows the order chosen in section 8, still open 9); T27 after launch in
  `tests/test_typed_replicate.py`. The existing 35-unit tests stay and run under `read_plan = full` (T17).
- Read-plan smoke (spec 4.3): S1 the smoke manifest (3.7 A); S2 the fake smoke (CLI stop after the plan and resume; a
  scripted variant with an alias bench, a bench changed at step 3, the ZebraLogic probe and an interrupt inside an S5
  unit; the three SIGKILL points); S3 the real smoke on dl (section 6); S4 not exercised before the real run: the real
  consent / registry / qualification path and the live ALFWorld resets of the pass (K-H).
- Counts as built (Python 3.13; also 3.10 as a syntax floor; the Mac has no 3.11): 126 typed tests before the build,
  484 after batch 1, 500 after 5b, 512 after 5w [impl reports].

## 6. Operations on the Linux machine

- Names (D6): code snapshot `/data/execskill-code-<date>-typed-v2`, build tree `/data/execskill-dev-typed2`, run
  root `/data/execskill-<date>-typed-v2`, smoke root `...-typed-v2-smoke`, ops `/data/typed-v2-ops`, TMPDIR
  `/tmp/typed2run-<phase>-<chain>`, tmux `typed2-run-G|D`, `typed2-smoke-G|D` (always addressed as `-t =NAME`).
- Launcher: a copy of typed-v1's `run-typed.sh` in the new ops directory with the new names, the same
  `--machinery-snapshot /data/execskill-code-20261109-main-v10`, and `sha256sum --quiet -c` on both machinery lists
  before start. The typed-v1 ops helpers are not edited; those that read gate labels, limits or decisions
  (`decdump.py`, `reuse.py`, `cost.py`, `attdump.py`, `fault_probe.py`) are copied and adapted to the label
  `<arm>#<r>` and the new decision fields.
- Order before a paid call: full local tests; Linux suite alone on dl; data list made from the snapshot and pinned
  (done [F11]); bound driver on dl against the real snapshot (Python 3.11); caps decided (done: the D6 caps stay
  [F12, O3]); `prepare --schedule learn_first --read-plan economy --memory-lock unit_shared --base-card historical`
  (caps, draw keys, widths, learning widths and the code identity are sealed from the code; check the printed
  `base_card`) [D9, D13, D15, D17; impl 5b]; smoke (below; the smoke root prepared the same way plus the probe
  [Q20]); the corrected token figure (F12 plus the D16 and D17 increments) reported to the owner before launch [F12];
  the owner told in plain words that C is read fresh and not carried [RP1]; consent written by the owner or under the
  standing delegation for the new root, its note naming the root and stating the read plan [O9]; first real responses
  confirmed.
  Changed by D9, D17, O9: the old order named only schedule, lock and caps at `prepare` and a consent note naming the
  root.
- Caps (D6): G 150,000,000 and D 170,000,000, fixed before `prepare`. Resolved [O3, F12]: the projection gives a worst
  case of 98.9 M (G) and 121.2 M (D), 66 and 71 per cent of the caps; with D16 and D17 about 123 M (82 per cent) and
  145 M (85 per cent) [K-D]; the caps stay.
- Beside typed-v1: typed-v1 is stopped and frozen (F3). The container scope (3.5) keeps the two runs apart if it is
  ever resumed; the machine-wide memory lock is shared by all runs and has no fairness.
- Machine (addendum D13, D14): both chains run on dl; the second machine is not used. An ops-side sampler (no run
  code) logs cgroup memory use and `memory.failcnt` during smoke and run; a non-zero `failcnt` or any memory kill
  is reported and the affected unit is treated as a faulty attempt.
- Wall time is not budgeted: a gate unit takes about three times as long as in typed-v1; SpreadsheetBench runs 150
  cells per gate arm at width 2.
- Learning widths [D15]: with width 6 the ZebraLogic step takes about 5 h instead of about 10 h. Rate-limit errors
  become infrastructure unknowns (re-run by the existing rule); a pause they cause is resumed with the same widths
  and reported. The read phase spans most of a day (K-C). D14 put the second machine's gain at 2 to 12 h of about 30.
- Smoke [D9, D13, D15, D17, RP6, Q20; spec 4.3 S3]: `learn_first`, `economy`, `unit_shared`, `base_card =
  'historical'`, the run's `widths` / `learn_widths`, `read_plan_probe = ['C0', 'zebralogic']`. (a) `smoke --chain X
  --stop-after-plan` once: exit 5 after an `equal` replay; the ledger is unchanged across the pass; ops checks the
  planned fresh units, writes `recovery.json` and runs `smoke --chain X --resume`. (b) One kill inside a fresh read
  unit, chosen from the bound `read_order`: the first event whose bench list holds text benches only, else S5 once its
  sheet and ALFWorld units are done, else a declared cleanup test inside S5 with a container listing before the
  resume (an untagged scoring container is removed by its exact name); then `recovery.json` with `same_phase: true`
  and `smoke --resume`. (c) It passes only if the pass sent nothing, at least one alias exists and its representative
  passed R41, at least one fresh unit completed, the probe pair was read fresh with reason `smoke_probe` and would
  otherwise have been an alias, (a) and (b) completed, no `execskill-sbx-<chain>-` container remains, the readout
  renders the classes block and R46 passed. The real run does not stop after the plan [RP6].
- Recovery records [RP5, R45, R89]: every resume consumes one `recovery.json` (standing delegation of 11/11). In the
  read phase the record carries `same_phase: true` only when no code, configuration, provider route or credential
  changed, written before the resume and blind to results; a pause above 24 h or a missing field splits the phase, and
  contrasts across it become references. A re-read after a split is a separate owner decision, taken before the sealed
  reads are opened.
- After launch [RP1]: the post-read `replicate` command (3.7 E) is built and run on complete chains only, with the
  typed-v1 root as `--source`; its output is a noise and drift reference, never a baseline or a table row.
- Reporting [D16 c, D17, O5, PG, RP7]: each accepted skill shows its home gain and every member gain ("related
  gain", informational); a program accepted on a selected baseline is named (`baseline_selected`); each accepted
  program states its fired items and its gain beside `se_points_fired` and `se_points_scaled`; `in-run replicates:
  <n>` stands beside every contrast (0 as planned: no in-run replicate is built, RP7; n > 0 only when a fallback read
  two classes with identical requests, R69); a same-phase ZebraLogic replicate (about 1.0 to 1.2 M tokens per chain)
  is offered to the owner as an option only. Comparison with SkillOpt and GEPA [D17]: a separate block, labelled
  cross-run and cross-date, shows the typed-v2 rows and the v2.24 SkillOpt / GEPA rows against the same C row,
  stating that typed-v2 starts from C while those baselines started from an empty skill, and that the v2.24 rows were
  read on 2026-11-07/08. It is not a table of the typed-v2 readout, to which R68 ("no cross-date number enters any
  table", 3.7 F) applies.
- Ops helpers [impl 5w; R73]: the copies of `decdump.py`, `reuse.py`, `cost.py`, `attdump.py`, `fault_probe.py` read
  `<arm>#<r>`, `per_item`, `baseline`, `candidate_arm`, `gate_verdict` and the run counts of `decisions.json`; the
  copies of `mounts.py` / `mounts2.py` print settled and alias counts from the state. A draft launcher exists as
  `SkillOpt-scratch/typed-v2-build/ops/run-typed2.sh` (not reviewed by this merge).

## 7. Owner decisions taken (formerly: hooks waiting for the owner)

Changed by D9..D12, D16, D17: this section listed the owner's two open points of `DECISIONS.md` section 3 (the read
policy; whether typed-v1 stops early) and described D9..D12 as hooks that were not designed in. All are decided and
designed in:
- typed-v1 stopped early, on 2026-11-12 at 15:13, and stays frozen [F7; owner message of about 14:2x] (2, F3).
- Read policy: `learn_first` with the economy read plan [D9, D10]; C read fresh, no carry [RP1, revising D11]; nothing
  of D1..D8 is cut [D12] (3.6, 3.7).
- Lock and machine of this run: `unit_shared` [D13]; both chains on dl [D14] (3.6, 6).
- Learning widths [D15] (3.6).
- Shared-type learning and gating, the owner's choice "A" [D16] (3.1, 3.2, 3.4).
- Learning starts from the historical card C, a coordinator decision under the owner's goal for the night [D17] (3.1,
  3.2, 3.4, 3.7 B).
The hooks the first integration provided (`learn_first` and the frozen receipts, `mount_identity`, the sealed manifest
fields and `own_root`) are the ones the read plan uses (3.7).
Options left to the owner, not designed in: a same-phase ZebraLogic replicate in the read phase [RP7]; the second
machine for a faster follow-up [D14]; a re-read after a split phase, decided before the sealed reads are opened
[R89]; the two static-screen relaxations with the next machinery snapshot [D1]. Also not designed in, considered by
the coordinator and not taken now: locking only the native operation with model calls outside (`v218_lock.call` /
`workers` / `engine` inside `T/mount.py` `solve`): larger gain, but new call sites and a new memory analysis [D13]
(3.6).

## 8. Open points for the coordinator (answers folded in; O7 partly resolved; "Still open" below)

- O1 (gate). Resolved [O1, F13]: a final model-side unknown cell (`unknown`, `unknown_artifact`) is scored 0, never
  re-run and counted in `unknown_final`; infrastructure and configuration unknowns are re-run and pause the chain if
  they stay unknown; the same for both arms of every comparison (3.4).
- O2 (guard). Resolved [F11]: the data list was made on dl from the snapshot; `DATA_LIST_SHA256` is pinned (2, 3.5).
- O3 (caps). Resolved [F12]: a projection from the typed-v1 ledger with the ALFWorld step and the tripled gate arms;
  the D6 caps stay (2, 3.4, 6).
- O4 (identity). Resolved [O4]: the draw keys keep their typed-v1 values, the one stated exception to D6 (3.5).
- O5 (gate). Resolved [O5]: D5's sharing stays; after an accepted card the program baseline is the card's three gate
  runs; the record says `baseline_selected: true` and reports name it (3.4).
- O6 (gate). Resolved [O6]: fired = fired in at least one of the R cells; the record keeps the fired count per item
  (0..R). The no-harm baseline is the earlier noise unit, now `B@noise` [D17] (3.4).
- O7 (engineer). Partly resolved [O7]. O7 in full: "The typed-side `no_hook_function` check is accepted (it runs
  before the frozen `policy.check`, whose call is unchanged)." Resolved: the check is accepted, and the `policy.check`
  call is unchanged. Order open: O7 binds "before"; the build (4b) runs the check after `policy.check` (still open
  3) (3.2).
- O8 (reply). Resolved [O8]: the implementer worded the twelve remaining `PROBLEM_SENTENCES` (counts and key names
  only), pinned, reviewed (3.3).
- O9 (consent). Resolved [O9]: an operations rule, no code: the note of every typed-v2 consent names the run root and
  states the read plan (4.4, 6).
- O10 (read plan). Resolved [O10; RP1..RP13]: integrated in this merge (3.7); built after step 6; it shares
  `T/reads.py` with the reset wrap of D13 (3.6); `schedule` of the real run is `learn_first` [D9]. The RP decisions
  "do not touch Steps 1 to 7 of IMPLEMENTATION-ORDER.md" [RP header of 17:29]. Who makes the reset wrap, and whether
  step 7 comes before or after the read plan, are open (still open 1 and 9).
- O11 (added by the coordinator, binary scores). Decided [O11]: the gate statistics are built for binary scores only
  (3.4, 5).
- O12 (added by the coordinator, per-item records). Decided [O12]: the list forms (3.4, 4.1).
- Program gate on the fired items. Decided [PG]: no stricter threshold for small fired subsets; informational
  `se_points_fired`, `se_points_scaled` (3.4).
- Read-plan questions. Decided [RP12]: Q19 retired (the `scripts.*` modules join the machinery check, step 7); Q20
  smoke-only probe accepted; Q21 a replay child that crashes or times out pauses `read_plan_changed`
  (`replay_error`), a second error with the same code voids the plan; Q22 `solver_settings_changed` pauses a resume
  before any call; Q23 yes, binding for step 5b; Q24 option A (`pass_exception`). Decided [RP13]: the R29 literal
  reading; R44 a `verify_alias` compares the representative's counts from its mirror; T23's reason check covers the
  read-plan parts of the state only; the recovery outcome names of `T/readplan.py` adopted; R1's constants stay in
  `T/readplan.py`, re-exported by `T/__init__.py`; the planning pass mounts with exactly the frozen library and type
  map it records, proved by a test (3.7).

Still open after the merge (all answered on 2026-11-12 by RP14, RP15 and RP16 of the addendum; kept as the record of the merge). These are not decided by the addendum; they are listed for the coordinator and the
reviews [merge note]:
1. Owner of the D13 reset wrap. The RP decisions do not touch Steps 1 to 7 of IMPLEMENTATION-ORDER.md, and the read
   plan is built after Step 6 [RP header of 17:29; O10]. Step 6 lists the wrap of `_from_services`
   (`T/reads.py:229-230`). R24 (spec) wants the `open_panel` extraction, a read-plan change, in the same change as the
   wrap, so that `T/reads.py` is edited once; O10 says only that the read plan shares `T/reads.py` with the wrap. The
   open choice: either Step 6 keeps the wrap, and `T/reads.py` is then edited twice, against R24; or the coordinator
   moves the wrap into the read-plan piece. (The first merge also named Step 6 as a possible owner of the extraction;
   that would put a read-plan change into Step 6, which the RP decisions leave untouched.)
2. Step 5x (in progress at the merge): whether D16's member sentence enters the ten pinned engineer system texts (a new
   `PROMPT_VERSION` and new pins) or the user payloads only; the pinned propose text names the home slice only.
3. O7's order. O7 binds the typed-side hooks check before the frozen `policy.check` (3.2); the build (4b) runs it
   after it (source, policy, hooks, structure) [impl 4b]. This deviates from O7 until the coordinator either confirms
   O7 (4b moves the check) or corrects O7's order.
4. The Codex review fixes of batch 1 (commit e2cf9e7, branch typed-v2-codex1-fixes: reply rules 3 and 7, the version
   guard of the readout's public entries) were not in the main tree at about 19:55.
5. Step 4a's proposal: the [import] rule sentence states a from-import permission that the screen does not grant for
   banned members (`from datetime import time` is rejected); a fix needs a new `PROMPT_VERSION` and new pins [impl
   4a].
6. Step 5b's reading of D17 for the card screen (C added to the screen's public text) and the two label wordings are
   flagged for the batch-2 review [impl 5b].
7. Small build gaps: `T/gatestats.py` docstrings still name C0 as the noise baseline (D17 says B) [impl 5b, 5w]; case
   (d) of arm sharing has no dedicated chain test [impl 5w]; the reason rename changes the round-2 card request's
   `failing_clause` text, which 4.2 (2) does not name [impl 5s]; the test case "a cap projection that includes the
   ALFWorld step" of section 5 is assigned to no step (F12 made the projection ops-side) [impl 1a].
8. The spec's open checks N13, N15, N16 (3.7 I).
9. Order of step 7 against the read plan. O10 fixes only that the read plan comes after step 6; BS lists the rest as
   "step 5 wiring, steps 6 and 7 and the read plan". This merge proposes step 7 last (IMPLEMENTATION-ORDER, batch 3,
   a merge proposal [I]), so that its AST scan of `T/` covers `T/readplan.py`. The spec's change list (section 2)
   books the read plan's `REQUIRED` additions and its +40 lines in `tests/typed2_bound_driver.py` (`mount_identity`,
   the capture and T7 under `bind_machinery`; a file step 7 creates) as read-plan changes, which fits step 7 before
   the read plan [I]. The order the coordinator chooses decides who writes those lines.

History of the first integration (kept unchanged):

**Cross-check fixes.** Applied (31, the six test gaps of section 7 counted as one): 1.2 monkeypatch case; 1.3 private names in `REQUIRED` and the copy hash; 1.4
data-file list; 1.5 tree-side check; 2.1 no re-run of model-side unknown cells; 2.3, 2.5 stated; 2.4 own tau per
decision; 2.6 cost maximum 21n; 2.7 gate takes the rows with a slot; 2.9 draw-key exception stated; 2.10 one pin
rule and the narrow `typed_code`; 2.11 container scope; 3.1, 3.2 one merged version of the shared functions; 3.3 one
fix request; 3.4 one bound harness; 3.5 round-2 card request listed as changed; 3.6 one services pass; 3.7 one
limits convention; 3.8 implementation order; 4.3 `own_root` everywhere; 4.4 shared rows; 4.5 stored records; 4.6
re-run counts; 5.1, 5.5 retry budget per attempt and its test; 5.2 rerun entries per unit; 5.3 cap; 6 request list;
7 test gaps. Rejected (2): 4.2 a consent field for root or version (`T/reads.py:100-101` [V] demands exactly the
frozen route-B fields and consent rules are out of scope); the "re-run every unknown cell" rule of `spec/gate.md`
1.7, replaced by 2.1. Not decidable here (3): 2.2 (O5), 2.8 (O3), 5.4 wall time.
