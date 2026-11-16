# Brief P3b: typed-v3 decision rules on J, the screen run, the readout additions and the CLI presets (chain wiring)

You implement ONE piece of the next version of a research codebase. Work in the git worktree
`<repo-root>` (branch `research/typed-skills-v3-p3b`, at the integrated commit aaebef2) AS IT IS NOW,
and ONLY there (another builder changes the main tree's cell and read machinery at the same time: a sealed option
`resume_replay` ('off'|'on') that replays saved solver replies on resume; your preset must seal it 'on': add the preset
entry; if the option does not exist yet in your tree, seal the field anyway through prepare's options and say so). Earlier pieces are
in it: P1 (program learning with repair, the archive candidate), P2a and P2b (the item stage, integrated with P1 and P3r in aaebef2: under
`item_stage == 'planned'` a step's gate list J = the real gate slice R followed by judging-side attack A, guard G and
calibration K items, with `by_class` gains in every decision row), and P3a (in `gatestats.py`: the card rule on E =
R + A with tau from the baseline's repeats on E, the screen's pass rule and its count helper, `class_gains`,
`recompute` for the new kinds). Read their code and their reports first
(`<claude-job-tmp>/report-P1.md`, `report-P2a.md`, `report-P2b.md`, `report-P3a.md`, `report-P3r.md`). Do not
touch any other repository, do not push, do not commit. No network, no paid model calls: tests use the in-memory
fakes of the existing suite.

## Read first

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md` T2, T7, T9 (the readout's part) and
   `<scratch>/typed-v3-design/build/brief-P3-gate-and-reads.md`: you implement
   its sections A (wiring only: the arithmetic exists in P3a's functions; use them, do not write it again), B (the
   screen unit, its record, resume; the pass rule is P3a's), the READOUT ADDITIONS of C (the read rows themselves,
   `read_anchors`, interleaved + full and the consent are DONE by piece P3r: read its report
   `docs/handoff/typed-v3/pieces/report-P3r.md` and do not redo them) and D (prepare and the CLI presets), with its
   rules and tests.
2. The files that brief names (`gatestats.py` as changed by P3a, `gates.py`, `chain.py`, `readplan.py` as far as the
   `'full'` plan and the `'interleaved'` schedule need it, `reads.py`, `readout.py`, `prepare.py`,
   `scripts/run_typed.py`) and their tests.

## Notes that are not in the P3 brief

- OfficeQA has no made items (audit B36) and SpreadsheetBench's maker is not built: on their steps J = R and the
  rules reduce to today's (P3a documents the exact reduction; test it through the chain).
- The screen applies to every candidate that reaches a gate unit on a step with made items: card rounds, engineer
  program slots and the archive package (P1's `program-0`). The screen's baseline b comes from the R runs of the arm
  the candidate is compared with on the screen items (A + G), which exist in the step's `noise` unit for the base
  arm and in an accepted candidate's gate arm for a later current arm; find where they are and use them, never new
  runs. The screen's own cells (unit `<gate unit stem>-screen`) are never used as gate runs.
- The readout must state, for an archive package, its own gate decision apart from the step's later candidates,
  and that the archive's test readings were known when the rule was set (T9).
- The preset `--typed-v3` seals (P3r's flags: `--schedule interleaved --read-plan full --read-anchors C --base-card
  historical`): base card `historical`, schedule `interleaved`, read plan `full`, read anchors `('C',)`, memory lock `unit_shared`, `program_learning = 'repair'`, `item_stage = 'planned'`, `gate_rule =
  'evolution'`, `gate_screen = True`, the archive packages of the chain from the tree's index (P1), the item quotas
  (P2b's sealed table). A manifest sealed without the preset stays a typed-v2 style manifest. The smoke preset
  mirrors it with the tiny slices and limits the smoke already uses (check that the item stage and the screen run in
  the smoke with tiny quotas, so the smoke exercises every new unit).
- From the one review of P3a (`docs/handoff/typed-v3/pieces/review-P3a-codex.txt`): `screen_counts` now takes only
  the bare arm label of the screen unit for the candidate; pass it the screen unit's OWN cells and the candidate's
  actual arm, never a gate unit's cells. `recompute` checks an evolution card's consistency, not its provenance: at
  the decision and on resume, check that `evolution.item_ids` equals R + A of the step's sealed `items.json`, in J's
  order (a test: a record with a forged E is refused by the chain).
- The consent record of the real run will list the arms `C`, `S1`..`S5` only; find what validates consents and
  make sure `('C',)` anchors and that list agree (do not weaken the consent check).

## Rules and tests

As in the P3 brief ("Rules that are not negotiable", "Tests"), plus: a chain with `--typed-v3` and fakes completes
both chains end to end through all five steps with reads after every step (rows C, S1..S5, no C0), resumes after a
kill in the middle of a read event, after the screen unit and between the screen and the gate, with the same final
records as an uninterrupted run.

## Report back

Plain text: (a) files changed and created; (b) exact test commands with counts (new tests and the whole typed
selection `tests/test_typed*.py`); (c) existing tests edited and why; (d) what you could not do or did differently,
and why; (e) open risks; (f) the exact `prepare` command lines (real run and smoke) the operator must use. Never
report a part as done that has failing or missing tests. Keep a short progress note at
`<claude-job-tmp>/build-P3b-progress.md` and continue from it if it exists.
