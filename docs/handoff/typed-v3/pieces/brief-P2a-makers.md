# Brief P2a: typed-v3 item makers, selectors and the analyst's plan (new files only)

You implement ONE self-contained part of the next version of a research codebase: the TOOLS of the item stage. The
chain integration (the new units of a step, `items.json`, the gate list J, what writers see, resume) is a later
piece (P2b) that will call what you build. A third piece (P1, program learning) is being built at the same time in
another working tree; you must not depend on it and must not touch the files it changes.

## Where to work

- Git worktree `<repo-root>` (branch `research/typed-skills-v3-items`,
  created from commit `d25619c` of `research/typed-skills-v3`). Work ONLY there. Do not commit, do not push, do not
  touch any other tree or repository, the frozen snapshots, or anything on a remote machine.
- **New files only.** Create the package `skillopt/execskill/typed/items/` (`__init__.py`, `plan.py`,
  `zebra_items.py`, `select_items.py`, more modules if useful) and tests `tests/test_typed3_items_*.py`. Do NOT
  edit any existing file (not `chain.py`, `prepare.py`, `writers.py`, `typed/__init__.py`, `bank/*`, existing
  tests). If something you need from an existing module is missing, implement it in your package (or note in your
  report exactly which small change P2b must make, with the reason).
- No network, no paid model call, no real model client: the role-model calls you implement are functions that take
  a client object as an argument; tests use fakes (look at how the existing tests fake the role client of writers,
  e.g. in the chain/writer tests and `typed/smoke.py`).
- Tests need TMPDIR to be a directory whose name contains no word like "test": use `/tmp/typed3-items-neutral`
  (create it). Run: `cd <repo-root> && TMPDIR=/tmp/typed3-items-neutral python3 -m pytest tests/test_typed3_items_*.py -q -p no:cacheprovider`
  and, at the end, the whole typed selection `tests/test_typed*.py` (it must stay green; it was 874 passed before).

## Read first (in the worktree)

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md`: T3 (the step flow you serve), T4 (the plan), T5 (makers and
   quotas), T6 (what a writer may see). Also `<scratch>/typed-v3-design/build/brief-P2-item-stage.md`:
   the full piece P2; YOU implement its sections A (as data and pure functions), B.2's validation and request
   building, C and D. Its sections B (units), E (writers) and the J list are P2b's, not yours.
2. `skillopt/execskill/typed/bank/zebra.py` (`learn`, `make`, `true_clues`, `thin`, `row_of`, `certify`,
   `REMOVAL_WEIGHTS`, `solve_plainly`, `profile`, `compare`), `bank/zebra_build.py` (`stage_language`, `_made`,
   `item_name`, `item_digest`, `row_of_task`, `stage_make`, how a made puzzle becomes a benchmark item with
   `zebralogic.normalize`), `bank/env.py` (`read_object`, the tolerant JSON reading of a role reply).
   `docs/handoff/typed-v3/BANK-PILOT.md` B31-B33 and B35 explain what was checked about these puzzles.
3. `skillopt/execskill/typed/writers.py` (how a role call is made, recorded and charged; how learn examples are
   bounded for writers: reuse that bounding for the analyst and selector payloads), `tasktypes.py`
   (`public_text`), `mount.py` (`view_of`), `prepare.py` (`load_pool`, the practice slices, how ALFWorld games and
   their routing views are pinned), `units.py` (`write_json`, the path-word guard `FORBIDDEN_PATH_WORDS`),
   `chain.py` only to learn the formats of a step's `decisions.json` (for the experience log) and of cells/outcomes.

## What to build

### 1. `items/__init__.py`: constants, quotas, counts, records, registry

- The quota table of T5 as data (`ITEM_QUOTAS`): per bench, judging attack / guard / calibration and shown attack /
  guard: searchqa 60/45/45 and 27/13; officeqa 32/24/24 and 16/8; zebralogic 80/60/60 and 40/20;
  spreadsheetbench 24/18/18 and 13/7; alfworld 16/12/12 and 8/4. A bench absent or all zeros: no made items.
- Constants of T4 and T3.4: a weakness needs at least 3 evidence items, each failed by B in at least 2 of R runs;
  fewer than 3 kept weaknesses: judging attack = floor(20 % of the bench's judging total), guard unchanged, the rest
  calibration; shown side under the same condition: shown attack = floor(20 % of the shown total), the rest shown
  guard (this shown-side rule is a decision of this brief: T4 speaks of judging items only; write it in a
  docstring). The plan check holds when the attack items' pass rate is at least 5 points below the calibration
  items'. Use exact integer or fraction arithmetic for every count and comparison.
- `counts(bench, kept_weaknesses, quotas=ITEM_QUOTAS)` -> the exact per-class, per-side counts, and, when there
  are kept weaknesses, the split of the attack counts over them "in turn" (round robin in plan order; state the
  rule for a remainder). Hand-check the numbers for every bench in tests (e.g. zebralogic with 0, 1, 2, 3 and 5
  kept weaknesses).
- The item record `{'item', 'class', 'weakness', 'side', 'family', 'source', 'certificate', 'item_sha256'}` with
  a validating constructor, and `item_sha256(bench, item)`: the hash of everything a solver and the judge read of
  the item, in its benchmark form (for zebralogic use `zebra_build.item_digest`'s definition; for searchqa and
  alfworld define it the same way over the item's own fields; document which fields).
- A registry `MAKERS` from bench name to a maker object with one entry point (choose a clean signature; P2b will
  call it with the plan, the counts, the bench's pinned pool / learn ids / gate ids, the learn outcomes of B, the
  step identity (version, chain, step), a run-level registry of what was already made or selected, and an output
  writer). `officeqa` and `spreadsheetbench` return no items with reason `maker_not_built` (recorded, no error).

### 2. `items/plan.py`: the analyst (T4) and the experience log (P2 brief C)

- `ANALYST_SYSTEM`: a fixed text explaining the task (design practice items that help this solver improve on this
  kind of task, and items that would show a regression), the three classes, the output object of T4 (`weaknesses`
  [{id, description, evidence: [learn item ids], signature, spec}], `guards` [{description, spec}], `note`), and
  that `spec` must use only the fields of the capability sheet given in the payload.
- `analyst_payload(...)`: JSON with the bench, the task description as writers get it, per learn item its public
  text (bounded exactly like writers' examples), its R outcomes, ONE wrong reply excerpt (bounded) when it has one,
  the experience log, the capability sheet. Nothing of a gate item, a judging-side item or a reference answer.
- `request_plan(client, payload, ...)`: one role call (purpose `item_analyst`), the reply read with the tolerant
  reader, ONE format retry when unreadable; returns the raw object or "unreadable" with both replies recorded.
  Charging and recording follow the role-call conventions of `writers.py` (find how a writer's call is recorded
  and charged and do the same through the client you are given).
- `validate_plan(raw, learn_outcomes, R, capability_sheet)` -> (plan, record): keeps a weakness only when at least
  3 of its evidence ids are learn items and B failed each counted one in at least 2 of R runs (an evidence id that
  is not a learn item is dropped and recorded); unknown spec fields are dropped and recorded; ids are made unique
  deterministically; an unreadable plan becomes "no weakness" and the record says so.
- `experience_log(earlier_steps)`: built by fixed code from earlier steps' decision records and item records of
  THIS chain: per earlier step its bench, for every candidate its kind (card / program / archive), accepted or the
  refusal reason, the gain in points and n, and the earlier step's weaknesses (id, description) with how the
  accepted candidates did on their attack items. Counts and descriptions only: no item text, no reply, nothing of a
  gate or judging item. Define the input format you need from P2b precisely (a list of plain dicts) and test it.

### 3. `items/zebra_items.py`: the ZebraLogic maker (P2 brief D, first paragraph; no model call)

Capability sheet = {sizes: the judged sizes present in the practice slices; `emphasis`: per clue kind a factor in
[0.5, 2.0] (default 1) that DIVIDES the kind's removal weight (a larger factor keeps more clues of that kind);
`search`: 'any' | 'needed' ('needed': keep only puzzles the first solver does not settle without search, i.e. the
measure `zebra.compare` uses)}. Attack items: for each kept weakness in turn, puzzles of its sizes (or all sizes),
its emphasis and its search setting. Guard items: sizes where every learn item was right in all R runs (none such:
the two sizes with the highest pass rate; ties broken by a stated deterministic rule), natural weights.
Calibration items: natural weights, sizes in the proportion of the real gate slice (largest remainder; ties by a
stated rule). With no kept weakness, attack items are drawn like calibration items. The language is learned once
per step from the pinned practice pool exactly as `zebra_build.stage_language` does (both proofs must pass; store
its record). Every puzzle is made from a seed that names version, chain, step, class, weakness and number; it is
refused when its text equals a pool puzzle's or an earlier made puzzle's of this run (the run-level registry), and
certified by `zebra.certify` (both solvers, unique solution, no removable clue) BEFORE its item is written; then it
becomes an item with `zebralogic.normalize` exactly as the bank does. A made puzzle is its own family. A bounded
number of attempts per item (state it); a shortfall is recorded, never silently filled with another class.
Deterministic: the same inputs give byte-identical items and records.

### 4. `items/select_items.py`: selectors (P2 brief D, second paragraph)

- SearchQA: candidates are the practice-source items in neither the learn nor the gate slice of the run (find how
  the run's pool and slices are pinned) and not selected before in this run (run-level registry). A selector call
  (role client, purpose `item_selector`) per batch of 25 candidates, public text only (bounded), returns per
  candidate the id of the weakness or guard description it matches, or none (tolerant reader, one format retry per
  batch; an unreadable batch selects nothing and is recorded). Fixed code takes, in the pool's order, attack items
  per weakness in turn and guard items; calibration items are a seeded draw from the candidates not chosen;
  shortfalls go to calibration and are recorded. The selector never sees a reference answer.
- ALFWorld: candidates = practice-source games with a registered routing view, outside learn and gate, not
  selected before in this run; the six task types are read from the game's own identity or view by fixed code
  (find how the tree names them); attack = games of the weaknesses' types (the plan's spec names task types),
  guard = types solved in all R runs, calibration = the gate slice's type proportions (largest remainder). No model
  call. Shortfalls recorded.
- Both: shown and judging sides never share an item; a selected item keeps its real reference; family = the item
  itself (state if the tree has a better family notion, e.g. an ALFWorld game's scene, and use it if it exists).

## Rules that are not negotiable

- Leakage: the analyst and the selector see learn items' public text and outcomes only (the selector: candidates'
  public text only). No gate item, judging-side made item or reference answer reaches a role call. Add a test that
  scans every fake request for the public text and references of gate items and judging-side items.
- No path with a forbidden word (`units.FORBIDDEN_PATH_WORDS`) in anything you write; reuse the existing writer
  guard where files are written.
- Deterministic records; exact arithmetic for counts and the check rule; no float decides a count.
- Do not weaken any existing `require`, screen or guard; do not edit existing files.

## Tests (fakes only; expected values computed independently of the code, by hand where small)

At least: quotas and the 20 % rule give the exact counts of T5 for every bench (and the attack split over 1, 2, 3, 5
weaknesses); plan validation (evidence rule with exactly 2 vs 3 failing items and 1 vs 2 failed runs, non-learn
evidence ids, unknown spec fields, duplicate ids, unreadable reply after one retry); the experience log holds no
text of items or replies; the ZebraLogic maker certifies every puzzle, refuses a duplicate text (pool and earlier
made), follows sizes / emphasis / search (show the effect of emphasis on clue-kind counts over a small sample and
that 'needed' puzzles are not settled without search), is reproducible from its seeds, and its calibration sizes
follow the gate's proportions by largest remainder; the SearchQA selector takes items once per run, sends
shortfalls to calibration, sends public text only; the ALFWorld selection is by type with the gate's proportions;
`officeqa` / `spreadsheetbench` return `maker_not_built`; the leakage scan.

## Report back

Plain text for the engineer who reviews your diff: (a) files created and the public functions with their
signatures (P2b will call them: make the interface section precise), (b) exact test commands and pass/fail counts
(new tests and the whole typed selection), (c) what you could not do or decided differently and why, (d) every
place where P2b must do something (inputs it must pass, records it must keep, a change to an existing file it must
make), (e) open risks. Never report a part as done that has failing or missing tests.

Keep a short progress note at `<claude-job-tmp>/build-P2a-progress.md` (done / next / which
tests pass) after each step; if it exists when you start, continue from it (the network may cut your session).
