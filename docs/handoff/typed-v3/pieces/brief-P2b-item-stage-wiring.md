# Brief P2b: typed-v3 item stage wired into the chain (units, the gate list J, what writers see, resume)

You implement ONE piece of the next version of a research codebase. Work in the git worktree
`<repo-root>` (branch `research/typed-skills-v3-p2b`, at the merge commit bd421da of P1,
P2a and P3a) AS IT IS NOW, and ONLY there (another builder is changing the main tree at the same time). Earlier pieces are
already in it: P1 (version switch `typed-v3`, sealed options `program_learning` and `archive`, the zero-call probe,
repair rounds, the paid feedback round, the archive candidate), P2a (the package `skillopt/execskill/typed/items/`:
quotas and counts, item records and hashes, the analyst's request and plan validation, the experience log, the
ZebraLogic maker, the SearchQA and ALFWorld selectors, the maker registry) and P3a (in `gatestats.py`: the typed-v3
card rule on E, the screen's pass rule, `class_gains`). Read their code and their reports first:
`<claude-job-tmp>/report-P1.md`, `report-P2a.md`, `report-P3a.md` (the reports name the public
functions and what this piece must do). Do not touch any other repository, do not push, do not commit. No network,
no paid model calls: tests use the in-memory fakes of the existing suite.

## Read first

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md` (T3, T4, T5, T6; the last section: OfficeQA gets NO made items after
   the audit B36, and SpreadsheetBench's maker is not built) and
   `<scratch>/typed-v3-design/build/brief-P2-item-stage.md`: you implement its
   sections A (the sealed option and the table, using P2a's constants), B (the units), E (what writers see), the J
   list of B.5 and its rules and tests, using P2a's tools instead of writing them again.
2. `skillopt/execskill/typed/chain.py` (`Services`, `_Run.learn`, `noise`, `typing`, `outcomes`, `cards`,
   `programs` as changed by P1, `items`, `vectors_of`, `views_of`, `cells`, `builder`, `gate_arm`, `identities`,
   `compare`, `finalize`, `record`, `members_of` and the member checks), `writers.py` (`write_card`,
   `outcomes_for_writer`, `screen_card`, `propose_programs`, P1's `repair_program`), `prepare.py`,
   `scripts/run_typed.py`, `tasktypes.py` (`public_text`, `embed_texts`), `mount.py` (`view_of`), the chain tests
   with fakes, and P2a's package and tests.

## What to build (summary; the P2 brief is the specification)

- Sealed option `item_stage` in `('none', 'planned')`, default `'none'` (today's records byte-identical), and the
  sealed `item_quotas` table (default P2a's `ITEM_QUOTAS` with OfficeQA and SpreadsheetBench at zero; record the
  reasons `audit_bing_B36` and `maker_not_built` in each step's items block). Prepare and CLI flags in the existing
  style; a real run reads them back only from the manifest.
- Under `'planned'`, for bench b at step k, the units in this order: `s<k>/diagnose` (arm B R times on the learn
  slice through `_Run.cells`), `s<k>/items-plan` (one analyst call through a new `Services` field whose real
  implementation calls P2a's `request_plan` and `validate_plan`), `s<k>/items` (the maker through a new `Services`
  field and P2a's registry; every item written as `s<k>/items/<item id>.json` in the benchmark's own form with its
  record), `s<k>/items-check` (arm B ONCE on the judging-side attack and calibration items; holds iff attack at
  least 5 points below calibration; if not held and at least one weakness kept: `items-plan-2`, `items-2` (the
  first attack items kept on disk and marked `replaced`), `items-check-2`; no third attempt; these cells are used
  for nothing else), then the write-once `s<k>/items.json` (final lists by side and class, every item's hash, the
  plan's hash, both check records). A step with no made items (a bench at zero, or a maker that returns none) writes
  `items.json` with the reason and runs exactly as today.
- The gate list J: ONE place in `_Run` answers "the gate items of bench x in the current step": for the step's own
  bench after `items.json` is sealed, J = the real gate slice followed by the judging-side attack, guard and
  calibration items in that order; for every other bench (a member of a shared type) its real gate slice; a later
  step never uses an earlier step's made items. Every gate unit, identity, plan and member check uses that one
  place. Made items get routing views and embedding vectors exactly like practice items (`view_fn`,
  `tasktypes.embed_texts` with the services' embedder), computed when the list is sealed and again on resume, never
  stored where a writer can see them.
- `decisions.json` gets the block `items` (counts by class and side, the plan's weaknesses with their evidence
  counts, both checks, the reason when there are no made items) and every decision row carries `by_class` (P3a's
  `class_gains` over J with the class map of the step; informational, deciding nothing in this piece).
- What writers see (T6, P2 brief E): `outcomes` also runs F once on the SHOWN made items; the card writer's and the
  engineer's examples are the learn examples plus the shown items' (attack first), bounded and screened by the
  existing functions; the card leakage screen's corpus and practice ids include the shown items; P1's probe and its
  paid feedback round take the shown items beside the learn items. No judging-side item, gate item or reference
  answer reaches a writer, the analyst or the selector: add a test that scans every role request of a full fake
  step for the public text and the reference of every judging-side and gate item.
- The experience log passed to the analyst is built by P2a's function from THIS chain's earlier steps' records.

## Decisions already taken for this piece (follow them; they are recorded in the design record)

- Item files: P2a's `ItemStore` names files by SLOT (`items/<slot>.json`, `records/<slot>.json`), because pool ids can
  contain the word "test", ':' or '/'. Use the store; do NOT write `s<k>/items/<item id>.json`. Records keep the real
  ids; `items.json` lists slots, ids, classes, sides and hashes.
- `items-2` (the one replacement round when the check does not hold and round 1 kept at least one weakness): it
  replaces attack items only. Per side it makes at most as many attack items as round 1 made, split in turn over
  plan 2's kept weaknesses; when plan 2 keeps fewer than 3 weaknesses the count is min(round-1 attack count, the 20 %
  rule's attack count of `counts`); when plan 2 keeps none, nothing is replaced (round 1's attack items stay, not
  marked replaced) and the record says so. Round 1's guard and calibration items stay as they are in every case.
- The registry passed to a maker holds the chain's records from OTHER units only (earlier steps; round 1 including
  replaced items when making round 2); OfficeQA and SpreadsheetBench steps skip the analyst call (their maker is
  not built or their quota is zero) and record the reason in the items block.

## Rules that are not negotiable

- Default options: every existing test passes unchanged; records of a typed-v2 style run byte-identical.
- Write-once, resume-safe: kill and resume inside each new unit (after the analyst call and before the plan record;
  in the middle of making; between the check and the replacement; before `items.json`) gives the same final records
  as an uninterrupted run, with no repeated model call whose record exists.
- Ledger: every analyst and selector call is charged like any role call of the chain.
- No path with a forbidden word (`FORBIDDEN_PATH_WORDS`) inside run roots. Deterministic records.
- Do not weaken any `require`, screen or guard. The test panels are not touched by anything here.

## Tests (fakes only; expected values computed independently)

As listed in the P2 brief ("Tests"), for the parts you wire: the default flow unchanged; the units in order with
their records; quotas per bench with OfficeQA and SpreadsheetBench at zero and their reasons; the check and the one
replacement; J's order, that members keep their real slice, that a later step does not reuse made items; every
gate unit of a step runs on J (identities include the made items' hashes); writers see the shown items and never a
judging-side or gate item; the analyst's ledger charge; resume at the four points.

## Report back

Plain text: (a) files changed and created, one line each; (b) exact test commands with counts (the new tests and
the whole typed selection `tests/test_typed*.py`); (c) every existing test you edited and why; (d) what you could
not do or did differently, and why; (e) open risks; (f) what the next piece (P3b: the T7 rules on J, the screen run,
the reads, the CLI preset) must know. Never report a part as done that has failing or missing tests. Keep a short
progress note at `<claude-job-tmp>/build-P2b-progress.md` and continue from it if it exists.
