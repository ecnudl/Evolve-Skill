# Brief P2: typed-v3 item stage (items made after the train results, from an analyst's plan)

You implement ONE piece of the next version of a research codebase. Work in the git tree
`<repo-root>` (branch `research/typed-skills-v3`) AS IT IS NOW (an earlier piece,
P1, added the version switch, sealed options `program_learning` and `archive`, a zero-call probe and repair rounds:
read its code before you start and follow its conventions). Do not touch any other repository, do not push, do not
commit. No network, no paid model calls: tests use the in-memory fakes of the existing suite.

## Read first

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md`: you implement T3 (steps 1 to 5 and the unit order), T4, T5 for
   ZebraLogic, SearchQA and ALFWorld (NOT OfficeQA and SpreadsheetBench: they get a registry entry that returns "no
   made items" with a recorded reason, another piece adds their makers), T6, and the gate LIST J of T3.5. You do NOT
   implement T7 (decision rules, screen run) or T2 (reads): another piece does. After your piece a step of a bench
   with made items runs every gate unit on J with the EXISTING decision rules.
2. `skillopt/execskill/typed/chain.py`: `Services`, `_Run.learn`, `noise`, `typing`, `outcomes`, `cards`,
   `programs` (as changed by P1), `items`, `vectors_of`, `views_of`, `cells`, `builder`, `gate_arm`, `identities`,
   `compare`, `finalize`, `record`, `members_of` and the member checks.
3. `skillopt/execskill/typed/writers.py`: `write_card`, `outcomes_for_writer`, `screen_card` (what a writer may
   see and how examples are bounded and screened), `propose_programs` and P1's `repair_program`.
4. `skillopt/execskill/typed/bank/zebra.py` (`learn`, `make`, `row_of`, `certify`, `REMOVAL_WEIGHTS`, `profile`),
   `bank/zebra_build.py` (`stage_language`, `_made`, `item_digest`, how a made puzzle becomes a benchmark item with
   `zebralogic.normalize`), `bank/env.py` (`read_object`, the tolerant JSON reading of a role reply).
5. `skillopt/execskill/typed/prepare.py` and `scripts/run_typed.py` (sealed options), `tasktypes.py`
   (`public_text`, `embed_texts`), `mount.py` (`view_of`).
6. The chain tests with fakes.

## What to build

### A. Sealed option and limits

`item_stage` in `('none', 'planned')`, default `'none'` (the step flow of today, byte-identical records). Under
`'planned'` the flow of T3. A sealed table `item_quotas` (default: the table of T5: per bench judging A / G / K and
shown attack / guard counts; a bench absent from the table or with all zeros gets no made items) and the constants
of T4 (evidence of a weakness: at least 3 learn items failed in at least 2 of R runs; fewer than 3 kept weaknesses:
attack = 20 % of the bench's made judging count, rounded down, the rest to calibration) and of T3.4 (attack must be
at least 5 points below calibration).

### B. Units of the step under `'planned'` (bench b at step k), in this order

1. `s<k>/diagnose`: arm B (the base card alone, as `noise` mounts it) R times on the LEARN slice (labels `B#1..R`),
   through `_Run.cells`. Record per item the number of right runs.
2. `s<k>/items-plan`: ONE analyst call (role client, purpose `item_analyst`; a new Services field
   `plan_items(...)` with the real implementation in a new module `skillopt/execskill/typed/items/plan.py`).
   System prompt: a fixed text that explains the task (design practice items that help this solver improve on this
   kind of task and items that would show a regression), the three classes, the output object of T4 and the
   maker's capability sheet. User payload (JSON): bench, the bench's task description as writers get it, for each
   learn item its public text (bounded exactly as writers' examples are bounded), its R outcomes and ONE wrong
   reply excerpt when it has one, the experience log (C below), the capability sheet (D below). The reply is read
   with the tolerant reader and ONE format retry; fixed code validates it (T4: drop a weakness without evidence;
   unknown spec fields are dropped and recorded; ids are made unique). An unreadable plan after the retry: the
   plan is "no weakness" (attack share 20 % as calibration-like items drawn by the maker's default) and the record
   says so; the step goes on (infrastructure failures follow the chain's existing rule: one automatic retry, then
   pause).
3. `s<k>/items`: the maker of the bench (Services field `make_items(...)`, registry in
   `skillopt/execskill/typed/items/__init__.py`) returns for the plan and the quotas a list of item records; each
   made or selected item is written as `s<k>/items/<item id>.json` in the benchmark's own item form with a record
   `{'item': id, 'class': 'attack'|'guard'|'calibration', 'weakness': id|None, 'side': 'shown'|'judging',
   'family': str, 'source': 'made'|'selected', 'certificate': {...}|None, 'item_sha256': ...}` (the hash covers
   everything a solver and the judge read: reuse `zebra_build.item_digest`'s idea for every bench).
4. `s<k>/items-check`: arm B ONCE on the judging-side attack and calibration items; pass rates of the two classes;
   `holds` = attack at least 5 points below calibration. Not held and at least one weakness kept: `items-plan-2`
   (the analyst gets its first plan and, per weakness, the count and pass rate of its attack items, counts only),
   `items-2` (replacement attack items; the first attack items are kept on disk and marked `replaced`, never
   used), `items-check-2`. No third attempt. These cells are used for nothing else.
5. `s<k>/items.json` (write-once): the final lists (shown, judging by class), every item's hash, the plan hash,
   the two check records. From here on, for THIS step and THIS bench only, the gate items are J = the real gate
   slice followed by the judging-side attack, guard and calibration items (in that order), and the writers' learn
   material is extended as in E. A member bench of a shared type keeps its real gate slice; a later step never
   uses an earlier step's made items. Implement this at ONE place (how `_Run` answers "the gate items of bench x
   in the current step") and make every gate unit, identity and plan use it; made items need routing views and
   embedding vectors exactly like practice items (`view_fn`, `tasktypes.embed_texts` with the services' embedder),
   computed when the list is sealed and again on resume, never stored in a writer-visible place.
6. Then the existing units: `noise` (B x R on J) ... `finalize`. `decisions.json` gets a block `items` (counts by
   class and side, the plan's weaknesses with their evidence counts, both checks) and every decision row reports,
   beside its existing statistics over J, the gain in points on each of R, A, G, K (informational fields
   `by_class`; they decide nothing in this piece).

### C. Experience log (input of the analyst)

Built by fixed code from THIS chain's earlier steps' `decisions.json` and item records: per earlier step its bench,
for every candidate its kind (card / program / archive), accepted or the refusal reason, the gain in points and n,
and the earlier step's weaknesses (id and description) with how the accepted candidates did on their attack items.
Counts and descriptions only: no item text, no reply, nothing of a gate or judging item.

### D. Makers (tools exist before evolution; an item exists only after a plan)

`skillopt/execskill/typed/items/zebra_items.py`: capability sheet = {sizes: the ten judged sizes present in the
practice slices; `emphasis`: per clue kind a factor in [0.5, 2.0] (default 1) that divides the kind's removal weight
(a larger factor keeps more clues of that kind); `search`: 'any' | 'needed' ('needed': keep only puzzles the first
solver does not settle without search)}. Attack items: for each kept weakness in turn, puzzles of its `sizes` (or
all sizes), its `emphasis` and `search`. Guard items: sizes where every learn item was right in all R runs (none
such: the two sizes with the highest pass rate), natural weights. Calibration items: natural weights, sizes in the
proportion of the real gate slice (largest remainder). The language is learned once per step from the pinned
practice pool exactly as `zebra_build.stage_language` does (both proofs must pass) and its record is stored in the
unit. Every puzzle is made from a seed that names version, chain, step, class, weakness and number, refused when
its text equals a pool puzzle's or an earlier made puzzle's of this run (any step), certified by `zebra.certify`
(both solvers, unique solution, no removable clue) BEFORE its item is written, and turned into an item with
`zebralogic.normalize`. A made puzzle is its own family. No model call.

`skillopt/execskill/typed/items/select_items.py`:
- SearchQA: the candidates are the practice-source items that are in neither the learn nor the gate slice. A
  selector call (role client, purpose `item_selector`) per batch of 25 candidates (public text bounded) returns for
  each candidate the id of the weakness or guard description it matches, or none; fixed code takes, in the pool's
  order, attack items per weakness in turn and guard items; calibration items are a seeded draw from the
  candidates not chosen. Shortfalls go to calibration and are recorded. An item is selected at most once in the
  whole run (any step): keep a run-level record.
- ALFWorld: candidates = practice-source games (those with a registered routing view) outside learn and gate; the
  six task types are read from the game's own identity or view by fixed code (find how the tree names them); the
  analyst's spec names task types; attack = games of the weaknesses' types, guard = types solved in all R runs,
  calibration = the gate slice's type proportions. No model call.
Registry entries for `officeqa` and `spreadsheetbench`: return no items with reason `maker_not_built`.

### E. What writers see (T6)

`outcomes` additionally runs F once on the SHOWN made items; the card writer's and the engineer's examples are the
learn examples plus the shown items' (attack first), bounded and screened by the existing functions; the card
leakage screen's corpus and practice ids include the shown items. P1's probe and paid feedback round take the
shown items beside the learn items. A judging-side item or a gate item never reaches a writer: add a test that
scans every writer request of a full fake step for the public text of every judging-side and gate item.

## Rules that are not negotiable

- Default options: every existing test passes unchanged; records byte-identical.
- Write-once, resume-safe: kill and resume inside each of the five new units (after the analyst call and before the
  plan record; in the middle of making; between check and replacement; before `items.json`) must give the same
  final records as an uninterrupted run, with no repeated model call whose record exists.
- Leakage: the analyst sees learn items only; no judging-side made item, gate item or reference answer reaches the
  analyst, the selector's output, a writer or the engineer. The selector sees candidate items' PUBLIC text only.
- No path with a forbidden word (`FORBIDDEN_PATH_WORDS`) inside run roots. Deterministic records.
- Ledger: every analyst and selector call is charged like any role call of the chain.
- Do not weaken any `require`, screen or guard.

## Tests (fakes only)

Expected values computed independently of the code under check. At least: the default flow is unchanged; the plan
validation (evidence rule, fewer-than-3 rule, unknown fields); quotas and the 20 % rule give the exact counts of T5
for each bench; the ZebraLogic maker certifies every puzzle, refuses a duplicate text, follows sizes / emphasis /
search, is reproducible from its seeds, and its calibration sizes follow the gate's proportions; the SearchQA
selector takes items once per run and sends shortfalls to calibration; the ALFWorld selection is by type; the check
and the one replacement; J's order and that members keep their real slice; every gate unit of a step runs on J;
writers see shown items and never a judging-side or gate item; resume at the four points.

## Report back

As P1: files changed and created, exact test commands with counts, existing tests edited and why, what you could
not do or did differently and why, open risks. Never report a part as done that has failing or missing tests.
