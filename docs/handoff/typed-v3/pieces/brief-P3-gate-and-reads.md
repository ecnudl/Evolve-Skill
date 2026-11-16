# Brief P3: typed-v3 decision rules on the gate list J, the screen run, and the read rows

You implement ONE piece of the next version of a research codebase. Work in the git tree
`<repo-root>` (branch `research/typed-skills-v3`) AS IT IS NOW (earlier pieces
added: P1 the version switch, `program_learning`, `archive`, the probe and repair rounds; P2 the item stage: under
`item_stage == 'planned'` a step's gate list is J = the real gate slice R followed by judging-side made items of
the classes attack A, guard G, calibration K, with informational `by_class` gains in every decision row). Read
their code first and follow their conventions. Do not touch any other repository, do not push, do not commit. No
network, no paid model calls: tests use the in-memory fakes of the existing suite.

## Read first

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md`: you implement T7 (decisions, screen run) and T2 (reads), and the
   readout's part of T9 (the archive's gain apart from what the step learned after it).
2. `skillopt/execskill/typed/gatestats.py` (all of it: `repeat_statistics`, `_derive`, `_subset`, `card_decision`,
   `program_decision`, `no_harm_decision`, `member_decision`, `recompute`), `gates.py`,
   `chain.py` (`compare`, `gate_arm`, `cards`, `card_decision`, `programs`, `program_decision`, `recompute_decision`,
   `read_anchors`, `read_step`, `reads`, the schedule handling), `readplan.py` only as far as the `'full'` plan and
   the `'interleaved'` schedule need it, `reads.py`, `readout.py` (how rows C0, C, S1..S5 are tabulated, the
   contrasts, the 5x5 block, the continual-learning metrics), `prepare.py`, `scripts/run_typed.py`.
3. The tests of gatestats, chain and readout.

## What to build

### A. Sealed option `gate_rule` in `('whole', 'evolution')`, default `'whole'` (today's rules, byte-identical)

Under `'evolution'` (only meaningful when a step has made items; on a step whose J is the real slice alone it
reduces exactly to today's rules, with E = J):
- Let E = R + A (the real gate items and the judging-side attack items) and J the whole list.
- CARD: accepted iff (1) the gain on E reaches tau_E, where tau_E = max(TAU_MIN_POINTS, TAU_SE_MULTIPLIER x the
  standard error computed from the BASELINE's own repeats on the items of E), (2) more items of E got better than
  worse, (3) `no_regress` holds on J exactly as `no_harm_decision` defines it over all items of J. Reasons, in this
  order: `gain_below_tau`, `not_more_better_than_worse`, `harm`, `accepted`. The record keeps the whole-list
  statistics as today plus an `evolution` block (n, difference sum, gain points, se and tau on E, better / worse /
  tied on E) from which the decision can be recomputed by `recompute`.
- PROGRAM: today's rule over J (fired on at least one item of J; the gain on the fired items reaches the
  whole-list tau; more fired items better than worse; `no_regress` on J). No change of the arithmetic.
- TYPING no-harm and MEMBER checks: unchanged.
- Exact integer arithmetic as the module does it; no float decides anything that an integer comparison can decide.

### B. Sealed option `gate_screen` in `(False, True)`, default False

Under True, before the R paid runs of a candidate's gate unit (card round, program slot, archive package): unit
`<gate unit's stem>-screen`: the candidate's arm ONCE on the judging-side attack and guard items (A + G; when a
step has no made items there is no screen and the gate runs as today). Let b = the sum over those items of the
baseline's right runs (R runs each, from the arm the candidate is compared with) and c = the candidate's right
count in its one run: the candidate goes on iff R * c >= b (its pass count is not below the baseline's mean), and
for a program or package additionally iff it fired on at least one of those items. A candidate that does not go on
gets a decision with zero gate cells: `accepted: False`, reason `screen`, and the screen record (b, c, R, fired
count). The screen's cells are NEVER used as gate runs (the gate's R runs are all fresh; state why in the
docstring: a candidate that passed by luck would carry that luck). Write-once record `screen.json`; resume-safe.
The revision round of a card (round 2) still happens after a round refused at the screen, with the examples the
existing code would use after a refused round.

### C. Reads (T2)

- A sealed option `read_anchors`: a tuple among `('C0', 'C')` (default: today's) and `('C',)`. With `('C',)` the
  event C0 is never read, never planned, never required for completion, and the readout tabulates rows C, S1..S5,
  with contrasts S<k> - C and S<k> - S<k-1> only (every place that reads a C0 mirror must tolerate its absence
  under this option and only under it; with the default the behaviour and bytes of today).
- The typed-v3 real run seals schedule `'interleaved'` and read plan `'full'`: after step k the frozen state S<k>
  is read fresh on all five panels. Check that this combination runs and resumes in this tree (it is typed-v1's
  order; typed-v2 used `'learn_first'` + `'economy'`); fix what the later changes broke for it, with tests.
- The readout additionally reports, per step: the item block (counts by class, the two checks), every decision's
  `by_class` gains and `evolution` block, the screen records, the repair history of programs, and for an archive
  package its own gate decision apart from the step's later candidates.

### D. `prepare` and the CLI

A preset `--typed-v3` (or the existing style of flags, whichever fits the file) that seals: base card
`historical`, schedule `interleaved`, read plan `full`, read anchors `('C',)`, memory lock `unit_shared`,
`program_learning = 'repair'`, `item_stage = 'planned'`, `gate_rule = 'evolution'`, `gate_screen = True`, the
archive packages of the chain from the tree's index, the quotas of T5. A manifest sealed without the preset stays
a typed-v2 style manifest. The smoke preset mirrors it with the tiny slices and limits the smoke already uses.

## Rules that are not negotiable

- Default options: every existing test passes unchanged; records byte-identical.
- `recompute` must reproduce every new decision from its stored record alone; add the new kinds to whatever
  verifies stored decisions at resume and in the readout.
- Write-once, resume-safe (kill and resume around the screen unit and between the screen and the gate).
- No path with a forbidden word inside run roots. Deterministic records. Do not weaken any `require` or guard.
- The test panels are read only through the existing consent-gated read code; nothing else may open them.

## Tests (fakes only; expected values computed independently, by hand where numbers are small)

At least: default rules unchanged; a card with a gain on E above tau_E and no regression on J is accepted; the
same card with a regression on guard items beyond tau_J is refused with `harm`; a card whose gain sits only on K is
refused; tau_E is computed from the baseline's repeats on E (a hand-computed case with unequal variance on E and on
J); a step without made items gives today's decision under `'evolution'`; the screen passes exactly at R * c == b
and fails at R * c == b - 1; a program that never fires on A + G is refused at the screen; screen cells never
appear in a gate arm; `read_anchors = ('C',)` completes a chain with rows C, S1..S5 and the readout holds no C0
row; `'interleaved'` + `'full'` reads S<k> after step k and resumes after a kill in the middle of a read event;
the preset seals exactly the fields listed in D.

## Report back

As the earlier pieces: files changed and created, exact test commands with counts, existing tests edited and why,
what you could not do or did differently and why, open risks. Never report a part as done that has failing or
missing tests.
