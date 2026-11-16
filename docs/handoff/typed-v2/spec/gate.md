# typed-v2 spec: gate with three repeats (D5)

Area: gate. Written 2026-11-12 (design only; no code edited). `T/` = `skillopt/execskill/typed/`, `X/` =
`skillopt/execskill/`. [V] = I opened and read the cited lines in this tree; [I] = inferred.

## 0. Blockers

No blockers. Everything below fits in `T/`, `tests/`, `docs/`; no file of the frozen machinery is edited (F1, D1).
Two points where D5 needs a precise reading are settled in 1.6 (what "identical requests" means when a type has
programs) and 1.7 (what a "missing cell" is); the second is also question 3 of section 6.

## 1. Behaviour

### 1.1 typed-v1 today (from the code)

1. One learning step runs these gate-slice arms (n = gate items of the bench) [V `T/chain.py:637-653`]:
   - `s<k>/noise`: mount arm C0 twice per item, cell labels `C0a`, `C0b`, mapped by `arm_of=lambda arm: 'C0'`
     (`chain.py:664`); 2n cells.
   - `s<k>/noharm-<T>`, one unit per existing type with the same signature: labels `F` (source provisionally merged
     in a scratch type map) and `C0`; 2n cells (`chain.py:712-724`).
   - `s<k>/outcomes`: `F` once on learn + gate (`chain.py:726-729`); n gate cells.
   - `s<k>/card-r<j>`, j <= 2: `cand_card` once on gate (`chain.py:780-781`); n cells per round.
     `s<k>/card-r<j>-learn` is a learn-slice unit (`chain.py:762-765`).
   - `s<k>/outcomes-card`, only after an accepted card: `F` once on learn + gate (`chain.py:850-851`); n gate cells.
   - `s<k>/program-<i>-gate`, i <= 2: `cand_program` once on gate (`chain.py:904-905`); n cells each.
     `s<k>/program-<i>-smoke` is a learn-slice unit (`chain.py:894-896`).
2. Baselines [V]: no-harm compares F against the C0 cells of the same unit (`chain.py:720-721`); a card round compares
   `cand_card` against `F` of `s<k>/outcomes` (`chain.py:782-783`), also in round 2; a program compares `cand_program`
   against `F` of `s<k>/outcomes-card` if a card was accepted, else of `s<k>/outcomes` (`chain.py:850-851, 906-907`).
3. tau [V `T/gates.py:112-121`]: per item d = C0b - C0a on items where both are known (`split_pairs`, `gates.py:101-109`);
   `se = sqrt(sum((d - mean)^2) / (n-1) / n)` (`gates.py:90`); `tau = max(3.0, 2 * 100 * se)`. One tau per step
   (`chain.py:645`), used by every decision of the step. Fewer than `ceil(0.5 * n)` known pairs pauses
   `noise_uncalibrated` (`chain.py:65, 668-671`).
4. Rules [V `T/gates.py:130-173`]: card accepts iff `mean_points >= tau` and `better > worse`; program accepts iff the
   same holds on the fired items and the whole-slice mean is `>= -tau`; no-harm merges iff `mean_points >= -tau`.
   Items with an unknown outcome on either side are excluded and counted (`excluded_unknown`).
5. After an accepted card the library gets the card (`apply_card`, `chain.py:835-839`), the round loop stops
   (`chain.py:757-759`), and the incumbent F is run again with the card (item 1, `outcomes-card`). After an accepted
   program the library gets the program, but the second candidate is still mounted from the snapshot taken before
   the first (`chain.py:869, 904-905`) and compared with the same baseline: the baseline is never re-run.

### 1.2 typed-v2: repeats and labels

6. `GATE_REPEATS = 3` (R). A gate cell has the label `<arm>#<r>`, r = 1..R: `C0#1..3`, `F#1..3`, `cand_card#1..3`,
   `cand_program#1..3`. A single-run cell keeps the bare label (`F`, `cand_card`, `cand_program`): the learn part of
   `outcomes` / `outcomes-card`, `card-r<j>-learn`, `program-<i>-smoke`, and every read unit.
7. The R repeats of an arm on an item are R jobs of ONE unit (`(bench, item, ('C0#1', 'C0#2', 'C0#3'))`). The label
   reaches `mount` and `solve` only through `arm_of = gates.arm_of_label` (`label.split('#', 1)[0]`), so both still
   see a member of `MOUNT_ARMS`. `row['arm']` stays the label, as today. Label consumers [V]: `T/units.py:367` and
   `T/chain.py:234` keep the label; `T/smoke.py:275` and `T/mount.py:347-348` see only the mount arm;
   `T/reads.py:361, 437-458` belong to read units, which never get a repeat label; `T/readout.py:228` folds it (3.4).
8. Each repeat is a fresh call: nothing in the tree returns a stored reply for an equal request
   (`CallRecorder.__call__` always calls the client, `T/units.py:219` [V]); reuse is by cell tag only, and the tag
   contains the label (section 3.1).

### 1.3 typed-v2: step flow (unit names and `done_units` order unchanged)

9. `s<k>/noise`: `C0#1..3` on gate, always, once per step. It is the calibration, the C0 side of every no-harm
   check, and the incumbent of the card gates whenever F is the same arm as C0 (1.6).
10. `s<k>/noharm-<T>`: runs only `F#1..3` under the scratch type map; its baseline is `C0` of `s<k>/noise`.
11. `s<k>/outcomes`: `F` once on learn; on gate either nothing (F shared, 1.6) or `F#1..3`.
12. `s<k>/card-r<j>`: `cand_card#1..3` on gate against the incumbent F. `card-r<j>-learn` is unchanged.
13. `s<k>/outcomes-card` (after an accepted card): `F` once on learn; on gate nothing when F with the card is the same
    arm as the accepted round's `cand_card` (the normal case), else `F#1..3`.
14. `s<k>/program-<i>-gate`: `cand_program#1..3` on gate against the current incumbent (the accepted card round's runs
    after a card, else the F of item 11). `program-<i>-smoke` is unchanged.

### 1.4 Statistics (one function, exact)

15. Inputs: gate items i = 1..n, baseline arm B and candidate arm K, each with R known scores `x[A,i,r]`. A cell's
    score is `1` / `0` for `correct` True / False (the only outcomes the bound judge produces today, `T/mount.py:407`
    [V]); a numeric score is converted with `fractions.Fraction(x)`. All sums below are `int` or `Fraction`.
    - `S[A,i] = sum_r x[A,i,r]`; `q[i] = R * sum_r x[B,i,r]^2 - S[B,i]^2` (binary: `S[B,i] * (R - S[B,i])`);
      `D = sum_i (S[K,i] - S[B,i])`; `Q = sum_i q[i]`. Then `sum_i s2[i] = Q / (R * (R-1))`.
    - reported floats: `gain_points = 100 * D / (R * n)`; `se_points = (100 / (R * n)) * sqrt(2 * Q / (R - 1))`
      (this is D5's `100 * sqrt(2 * sum_i s2[i] / (R * n^2))`); `tau_points = max(a, c * se_points)` with
      `a = TAU_MIN_POINTS = 3.0`, `c = TAU_SE_MULTIPLIER = 2.0`.
    - decided without floats (`a`, `c` as `Fraction`):
      `reaches(D, m) := 100*D >= a*R*m  and  D >= 0  and  D^2 * n^2 * (R-1) >= 2 * c^2 * Q * m^2` (gain over m items
      `>= tau`; m = n for the whole slice), and
      `no_regress(D) := 100*D >= -a*R*n  or  D >= 0  or  D^2 * (R-1) <= 2 * c^2 * Q` (whole-slice gain `>= -tau`).
    - `better` / `worse` / `tied`: items with `S[K,i] - S[B,i]` `> e` / `< -e` / otherwise; `e = 0` when every score
      is binary, `e = Fraction(1, 10**9)` otherwise.
16. Card: accepted iff `reaches(D, n)` and `better > worse`. Reasons as typed-v1: `accepted`, `gain_below_tau`,
    `better_not_above_worse`.
17. Program: an item is fired iff the candidate's id is in `fired` of at least one of its R candidate cells (today:
    of its one cell, `chain.py:908`). With `D_f`, `better_f`, `worse_f` over the `n_f` fired items: accepted iff
    `n_f > 0` and `reaches(D_f, n_f)` and `better_f > worse_f` and `no_regress(D)`. Reasons as typed-v1.
18. No-harm (form unchanged, on item means): K = F with the source merged, B = C0; merge iff `no_regress(D)`.
19. `R >= 2` is required (the variance needs it); `gate_repeats < 2` is refused when the run starts.

### 1.5 Baseline and tau of each comparison

20. tau is computed from the baseline arm's own R repeats, per comparison (D5: "noise from the incumbent's own
    repeats"). No-harm: B = C0 of `s<k>/noise`. Card rounds: B = the incumbent F (which is C0's runs for a new type
    without skills, or the F runs of `s<k>/noharm-<T>` after a merge, or `F#r` of `s<k>/outcomes`). Programs: B = the
    incumbent F, which after a card acceptance is the accepted round's `cand_card#r` runs. Both program candidates use
    the same B (as typed-v1, item 5).
21. `decisions.json['tau_points']` stays the value of `s<k>/noise` (C0). Every decision record carries its own tau,
    its inputs and the unit and arm of its baseline.

### 1.6 Shared runs ("the same arm")

22. Rule. Before a gate arm P runs, its mount identity is computed for every gate item without any paid call:
    `{'system_card_sha256', 'programs_offered': [[skill_id, skill sha256], ...], 'forced': candidate procedure
    record_sha256 or None}`, from the same routing as `_routed_mount` up to, not including, the selection call
    (`T/mount.py:190-221` [V]; C0 is the format block with nothing offered, `mount.py:169-170`). P is the same arm
    as an arm Q already run in this step iff the identities are equal on EVERY gate item (all or nothing). Then P
    runs no cell and uses Q's R runs. Q is searched in run order: `C0@noise`, `F@noharm-<T>`, `F@outcomes`,
    `cand_card@card-r<j>`, `F@outcomes-card`, `cand_program@program-<i>-gate`.
23. Why identity and not request hashes: for a type with programs the request also depends on the selection call,
    which is itself a fresh model call per cell (`mount.py:221-223` [V]); two arms with equal identities draw from
    the same request distribution, which is what "the same arm" means. For a type without programs equal identity
    is equal request bytes (system card + the item's user text; `solve` gets the same `step` label in every unit of
    a step, `chain.py:461, 473` [V]).
24. Cases in one step (each follows from the rule; none is hard-coded):
    - (a) C0 side of every no-harm check = `C0@noise`. Always.
    - (b) step opens a new type, no existing type has the signature: `F` = `C0@noise` (no card and no programs give
      the format block and nothing enabled, `mount.py:66-69, 200-204, 224-229` [V]). `s<k>/outcomes` has learn cells only.
    - (c) source merged into T: `F` = `F@noharm-<T>` (same type map content as the scratch map, `chain.py:716-717` [V]).
    - (d) no-harm failed and a new type opens: some gate items may still route to the old type (`TypeMap.assign`
      takes the nearest source, `T/tasktypes.py` [V]), so `F` may differ from C0: then `F#1..3` run in `s<k>/outcomes`.
    - (e) after an accepted card: `F` with the card = `cand_card@card-r<j>` of the accepted round (`apply_card`
      installs the gated text, `chain.py:787, 835-839` [V]; other-type items already mount as F, `mount.py:210-215`).
    - (f) degenerate: a round-2 text equal to round 1, or a candidate that reaches no gate item of its home type, is
      the same arm as an earlier one: no cells, gain 0, rejected (`gain_below_tau` / `never_fired`).
    - Never shared: a card candidate with a new text and a program candidate with at least one home-type gate item.
25. The sharing decision is written once per unit (`plan.json`, write-once like every phase record,
    `chain.py:316-323` [V]) before any cell runs, so a resumed unit has the same jobs [I: `run_unit(resume=True)`
    accepts a unit directory that already holds this one file]. When shared runs are used, each
    row's recorded `system_card_sha256` (`mount.py:176`) is checked against the identity; a difference pauses
    `shared_arm_mismatch`.

### 1.7 Missing cells

26. A decision (and `noise.json`) needs a record with a known score for all `n * R` cells of both arms.
    - no record: pause `incomplete_unit:missing_cells`, as today (`chain.py:508-510` [V]).
    - a record with `correct is None` left after the unit's normal attempts (one automatic retry on an infrastructure
      stop, `chain.py:499-504` [V]): the done marker is archived (`units.archive_done`, the `noise_uncalibrated`
      pattern of `chain.py:669-671`) and the chain pauses `gate_cells_unknown` with the count. Nothing is decided,
      no item is excluded, no cell is counted as wrong.
    - after the recovery the unit is re-entered; every `correct is None` cell of that gate unit is archived under
      `rerun/` and run again under the same label; known cells are kept. Still unknown: the same pause again.
27. Unknown outcomes today [V]: a shell or judge exception (`mount.py:394-402`), a judge token starting with
    `unknown` (`mount.py:407`), an infrastructure-unknown receipt. A program fault alone does not make a cell unknown
    (`X/outcomes_ext.py:8-10`). `MIN_NOISE_PAIRS_FRACTION` and `excluded_unknown > 0` no longer occur in a decision.

### 1.8 Limits

28. `T/__init__.py`: `GATE_REPEATS = 3`. `DEFAULT_LIMITS` and `SMOKE_LIMITS` gain `'gate_repeats': GATE_REPEATS` (the
    smoke gate slice has 3 items: 9 cells per arm). `real_services` passes no limits, so the real run gets the
    default (`chain.py:158, 1127-1138` [V]). The value is written into `decisions.json['limits']` (`chain.py:928`)
    and into the manifest's `tau_rule` (section 3.3); a run whose limits disagree with its manifest does not start.

### 1.9 Cost (gate-slice cells per learning step; one cell = one solver episode)

Gate sizes from `T/__init__.py:17-23` [V]. typed-v1 maximum = 8n (noise 2n, outcomes n, two card rounds 2n,
outcomes-card n, two program gates 2n). typed-v2 maximum = 15n (C0 3n, two card rounds 6n, two program gates 6n; F
and F-with-card are shared). Minimum (two rejected rounds, no program gate): 5n against 9n. Each no-harm check adds
2n against 3n; case (d) adds 3n. Without sharing typed-v2 would be 24n.

| bench | n | typed-v1 max | typed-v2 max | per no-harm check v1 / v2 |
|---|---|---|---|---|
| searchqa | 100 | 800 | 1,500 | 200 / 300 |
| officeqa | 40 | 320 | 600 | 80 / 120 |
| zebralogic | 100 | 800 | 1,500 | 200 / 300 |
| spreadsheetbench | 50 | 400 | 750 | 100 / 150 |
| alfworld | 40 | 320 | 600 | 80 / 120 |
| all five steps | 330 | 2,640 | 4,950 | |

Caps: the typed-v1 design expected about 17M learning + 76M read tokens per chain for G
(`docs/handoff/typed-v1/DESIGN.md:115-117` [V]). Gate cells grow by at most 15/8; learn cells, writer calls and reads do
not change. Even if all 17M were gate cells, learning stays under 32M and the chain under about 108M of 150,000,000.
So the typed-v1 caps (G 150,000,000; D 170,000,000) hold on the design estimate [I: I could not read the real typed-v1
ledger; D has no stated estimate]. Check before `prepare`: section 6, question 5.

## 2. Change list

| file | today | change | new names |
|---|---|---|---|
| `T/__init__.py` | 29-30, 42-44 | add the repeat count | `GATE_REPEATS = 3` |
| `T/gates.py` | 101-173 | `paired_statistics`, `split_pairs`, `noise_threshold` stay (the readout's read-side contrasts use them, `T/readout.py:413-416, 444-454` [V]). `card_decision`, `program_decision`, `no_harm_decision` (130-173) are replaced by the repeat versions of 1.4 | `REPEAT_SEP = '#'`; `repeat_labels(arm, repeats) -> tuple`; `arm_of_label(label) -> str`; `repeat_of_label(label) -> int or None`; `arm_runs(cells, items, arm, repeats) -> {'sums', 'squares', 'unknown'}`; `repeat_statistics(baseline, candidate, *, items, repeats, minimum_points, multiplier, subset=None) -> dict`; `calibration(baseline, *, items, repeats, ...) -> dict`; `card_decision(stats)`, `program_decision(stats, fired_stats, fired_cells)`, `no_harm_decision(stats)`; `recompute(record) -> dict` (offline check from `per_item`) |
| `T/mount.py` | 190-238 | split `_routed_mount` into the pure routing part and the selection part; add the identity function of 1.6. `mount()` output unchanged | `_route(...)`; `mount_identity(bench, item, *, arm, typemap, library, vector, candidate=None, view=None, runtime=None) -> dict` |
| `T/units.py` | 301-321 | `mark_infrastructure_reruns(unit_dir, ledger, *, any_unknown=False)`: with `any_unknown` every `correct is None` cell is archived and marked (today only flagged ones, line 316) | keyword `any_unknown` |
| `T/chain.py` | 61-62 | `DEFAULT_LIMITS` gains `'gate_repeats': GATE_REPEATS` | |
| `T/chain.py` | 65, 668-671 | `MIN_NOISE_PAIRS_FRACTION` and the `noise_uncalibrated` pause are removed (1.7 replaces them) | pause reasons `gate_cells_unknown`, `shared_arm_mismatch` |
| `T/chain.py` | 227-245 | `_with_selection`: also set `row['repeat'] = gates.repeat_of_label(arm)` (line 234 keeps `row['arm'] = arm`) | cell field `repeat` |
| `T/chain.py` | 477-512 | `cells(..., rerun_unknown=False)` passes `any_unknown` to line 489 | keyword |
| `T/chain.py` | new, after 512 | `gate_arm(unit, bench, arm, *, earlier, candidate=None, typemap=None, library=None, extra_jobs=())`: writes `plan.json` (1.6), runs `repeat_labels(arm, R)` unless shared, checks completeness (1.7), returns `{'unit', 'arm', 'shared_from', 'runs': {(item_id, r): row}, 'identity'}` | `_Run.gate_arm`, `_Run.identities` |
| `T/chain.py` | 637-653 | `step`: carries the list of gate arms run so far and the incumbent instead of one `tau` | |
| `T/chain.py` | 655-676 | `noise`: `C0#1..3` through `gate_arm`; record of 3.2 | |
| `T/chain.py` | 678-724 | `typing` / `no_harm`: only `F#r` under the scratch map; baseline `C0@noise`; evidence keys (699) gain `repeats`, `se_points` | |
| `T/chain.py` | 726-729 | `outcomes`: learn jobs `('F',)` plus gate jobs only when F is not shared; returns learn cells and the incumbent arm | |
| `T/chain.py` | 731-788 | `cards` / `card_decision`: `cand_card#r` through `gate_arm`; `chars` stays the card area's field | |
| `T/chain.py` | 841-915 | `programs` / `program_decision`: `outcomes-card` learn only + shared gate (850-851); gate `cand_program#r` (904-905); fired per item over repeats (908) | |
| `T/chain.py` | 917-930 | `finalize`: fields of 3.2 | |
| `T/chain.py` | `run` near 973; `real_services` 1075-1138 | `run` refuses `limits['gate_repeats'] < 2`; `real_services` requires the manifest's `tau_rule['repeats'] == GATE_REPEATS` [I: that the manifest is in scope there; `_open_state`, 939-948, has neither] | |
| `T/chain.py` | 146-147, 1125-1133 | `Services` gains `identity_fn`; `real_services` wires `mount.mount_identity` with the same view wrapper as `mount_fn` | `Services.identity_fn` |
| `T/smoke.py` | 28, 263-283, 300-306 | `SMOKE_LIMITS` gains `gate_repeats`; `fake_solve` finds the repeat by matching `tag` against `units.cell_tag(bench, id, label)` and hands the script `{**mounted, 'repeat': r}`; the row's `mount` is unchanged; `fake_services` wires `identity_fn` | `smoke.repeat_of_tag` |
| `T/prepare.py` | 283 | `tau_rule` gains `'repeats': GATE_REPEATS, 'se': 'baseline_repeats'` | |
| `T/writers.py` | 222-239 | no code change needed: every key `revision_result` reads is kept (3.2) | |
| `T/readout.py` | 61, 153-158, 174-185, 228, 709-719 | section 3.4 | `GATE_NOISE_KEYS` |
| `T/reads.py` | 290, 334-347, 361, 436-458 | none: read units use bare labels and no `arm_of` [V] | |

## 3. Records and identity

### 3.1 Where the repeat index is (all through the label `<arm>#<r>`) [V]

- cell tag `sha256(bench \0 item_id \0 label)` (`T/units.py:253-254`); so `cells/<tag>.json`, `unsubmitted/<tag>.json`,
  `rerun/<tag>-<n>.json` (`units.py:341-352, 371-375, 301-321`), the call files `calls/<tag>.json` and
  `<tag>-selection.json` (`chain.py:1052-1054`), the ledger's pending entry `{'cell': tag, 'unit': unit}`
  (`units.py:159-163`), and the scorer position `{'benchmark', 'unit', 'cell': tag, 'scoring'}` (`mount.py:473-480`);
- the cell row: `arm` = label (`chain.py:234`, `units.py:367`), new `repeat` = r (None for a single-run cell),
  `mount.arm` = the mount arm as today.
- Resume returns a stored cell only for an equal tag (`units.py:350-352`); a done unit returns its own files only
  (`units.py:334-337`). No path can hand repeat r the result of repeat r'. The R repeats of one item run back to
  back in one worker, in the seeded order of `arm_order` (`units.py:257-262, 384-387`).

### 3.2 Changed and new records

- `s<k>/noise/noise.json`: `unit, bench, step, items, cells (= n*R), arms ['C0#1','C0#2','C0#3'], mount_arm 'C0',
  rule 'baseline_repeats', repeats, n, variance_sum (Q), mixed_items, runs_correct, se_points, tau_points,
  minimum_points, multiplier, scores ('binary' | 'fraction'), per_item {item_id: [S, sum of squares]}`.
  Gone: `minimum_pairs`, `flip_rate`, `mean_points`, `excluded_unknown`, `statistics`.
- `s<k>/<unit>/plan.json` (new, write-once): `unit, arm, repeats, items, labels, shared_from (null or {unit, arm}),
  identity_sha256, compared [{unit, arm, equal, differing_items}]`.
- Decision records (`card-r<j>/decision.json`, `noharm-<T>/decision.json`, the program decision): typed-v1 keys with
  unchanged meaning are kept (`kind, accepted | merge, reason, n, mean_points, tau_points, better, worse, tied, items,
  cells, excluded_unknown` (always 0), `fired_n`, `fired`, `whole`). New: `repeats, se_points, minimum_points,
  multiplier, difference_sum (D), variance_sum (Q), scores, baseline {unit, arm, shared_from}, candidate {unit, arm,
  shared_from}, per_item {item_id: [S_B, squares_B, S_K]}`, and for programs `fired_cells {item_id: count}`.
  `current_correct` / `candidate_correct` become `baseline_runs_correct` / `candidate_runs_correct` (0..n*R).
  Sums are JSON integers when binary, else strings `"p/q"`. `gates.recompute(record)` rebuilds every other field.
- `decisions.json` (`chain.py:917-930`): `limits` gains `gate_repeats`; new `gate {repeats, arms [{arm, unit,
  shared_from}]}`; `outcomes.gate`, `outcomes_with_card`, `program_gate_current` count runs and name their source
  unit; `tau_points` and `noise` are the C0 calibration.
- manifest: `tau_rule {minimum_points, se_multiplier, repeats, se}` (`T/prepare.py:283`).
- ledger and writer records: no shape change. Round 2 of the card writer gets `revision_result(decision)` with the
  same keys and types (`T/writers.py:222-239` [V] reads `better, worse, n, tied, excluded_unknown, mean_points,
  tau_points, accepted, reason` by name and ignores the rest), now holding the item-mean numbers and this
  decision's tau.

### 3.3 What changes and what stays byte-identical

- Unchanged: every request text and prompt pin. The label never reaches `mount` or `solve` (`chain.py:465` passes
  `arm_of(arm)`; `mount.py:161` and `:347-348` require a mount arm [V]); the writer templates are untouched (3.2).
  The `_route` refactor must leave `mount()` records equal (test 4.1.5).
- Changed: gate cell tags (new labels), cell counts of gate units, the record shapes of 3.2, the manifest's `tau_rule`.

### 3.4 Readout

- `_unit_summary` (`T/readout.py:219-242`): `by_arm` is keyed by `gates.arm_of_label(cell['arm'])`; each arm gains
  `repeats {r: {cells, correct, wrong, unknown}}` (line 228 keys on the raw label today).
- `_noise` (153-158) reads `GATE_NOISE_KEYS = ('rule', 'repeats', 'n', 'mixed_items', 'se_points', 'tau_points')`;
  `NOISE_KEYS` (61) stays for the read-side same-request noise (444-454), which still compares two single runs.
- `_decision_row` (174-185) adds `repeats, se_points, baseline`; the step table (709-719) prints them.

### 3.5 Ledger re-run set with repeats inside one unit

`Ledger.__init__` puts the tag of every pending send into `rerun_cells` (`T/units.py:116-124` [V]). Each repeat has its
own tag, so a recovered in-flight call re-runs exactly that repeat; the item's other repeats are kept. Unchanged from
typed-v1: the set holds bare tags, and a tag recurs across units (for example `cand_card#2` of one item in `card-r1`
and `card-r2`). Done units ignore the set (`units.py:334-337`) and only marked tags are removed (`chain.py:497`), so
the one side effect is that a later, unfinished unit holding a stored cell with the same tag runs it once more (a
fresh call under the same label). It never couples two repeats. No change planned.

## 4. Tests

### 4.1 New

1. `test_repeat_statistics_exact`: hand-computed cases for R = 3 (D, Q, SE, tau, better / worse); the boundary
   `D^2 * (R-1) == 8 * Q` accepts; floats never decide (a case where `gain == tau` only in exact arithmetic).
2. `test_repeat_statistics_fraction_scores`: non-binary scores, tolerance 1e-9 on item sums, same inequalities.
3. `test_gate_decisions_card_program_no_harm`: each reason; the fired subset; whole-slice non-regression.
4. `test_recompute_from_record`: `gates.recompute(decision)` equals the stored decision after a JSON round trip.
5. `test_mount_identity_matches_mount`: for every arm and fixture, `mount_identity` equals the fields of `mount()`,
   and `mount()` records equal a stored typed-v1 expectation (guards the `_route` split).
6. `test_repeats_are_fresh_cells`: one gate unit, fake client counting sends: `n * R` sends, `n * R` distinct tags,
   `row['repeat']` set, `mount.arm` bare; a resume re-runs only the missing repeat.
7. `test_shared_arms_per_case`: cases (a) to (f) of 1.6 on the fake chain: expected units, cell counts, `plan.json`,
   `shared_from`, and that an unshared F has other identities.
8. `test_gate_cells_unknown_pauses_and_recovers`: one scripted unknown repeat pauses `gate_cells_unknown`; after
   recovery only that cell re-runs (archived under `rerun/`); the decision then uses all `n * R` cells.
9. `test_baseline_after_accepted_card`: the program gate's baseline is the accepted round's runs and its tau comes
   from them; `outcomes-card` has learn cells only.
10. `test_ledger_recovery_reruns_one_repeat`: a pending entry of `C0#2` re-runs that tag only.
11. `test_readout_folds_repeat_labels`: `by_arm` has `C0`, not `C0#1`; decision rows show R and SE.
12. Fresh interpreter under `bind_machinery` (pattern `tests/test_typed_cli.py:80-105` [V]): import `typed.gates`,
    `typed.mount`, `typed.chain` bound to a stub snapshot; run `repeat_statistics`, `arm_of_label`, and one fake
    gate unit; assert `typed.GATE_REPEATS == 3` and that `gates.__file__` is under this tree.

### 4.2 Existing tests that must change

- `tests/test_typed_core.py:121-132` keeps (old functions stay); `:135-153` rewritten for the new decision signatures.
- `tests/test_typed_chain.py:196-200` (noise record, labels `C0a` / `C0b`, 6 cells), `:205` (`outcomes.gate` counts),
  `:361` (`minimum_pairs`), `:377-401` (`noise_uncalibrated` becomes the 1.7 pause), `:669` (`SMOKE_LIMITS`
  now has `gate_repeats`; the assertion itself stays), and every `done_units` / cell-count assertion of gate units.
- `tests/test_typed_e2e.py:216, 224` (noise keys, card `cells == 4` becomes 12), `:293`.
- `tests/test_typed_readout.py:87, 168, 172` (fixtures built with the old `card_decision(pairs, tau)`; noise keys).
- `tests/test_typed_chain.py:31-67` `FakeMount` [V]: gains a `mount_identity` consistent with its `mount` (line 35),
  wired as `identity_fn`.

## 5. Interfaces to other areas

- Card (D2): the card decision keeps the key `chars` where it is (`chain.py:784-785`); its definition is the card
  area's. A void round still has no gate unit. Round 2 gets the numbers of 3.2 through the unchanged `revision_result`.
- Engineer and reply (D3, D4): the gate takes `proposals[:max_program_candidates]` as today (`chain.py:871-872`); unit
  names stay `program-<i>-smoke` / `program-<i>-gate`; promotion inside the proposal unit does not reach the gate.
- Identity and version (D6): this area adds `GATE_REPEATS`, the `tau_rule` fields and `Services.identity_fn` (default
  `mount.mount_identity`; `smoke.fake_services` and the test `FakeMount` supply one). The version constants and the
  pin `found['version'] == 'typed-v1'` (`tests/test_typed_cli.py:99`) belong to that area.
- Schedule and lock (D8): gate units hold up to three times the cells under the per-cell `s.heavy(bench)` lock
  (`chain.py:469` [V]); the lock choice is theirs. `learn_first` does not touch gate units; reads never use gate cells.
- Shared files: this area rewrites `noise`, `no_harm`, `outcomes`, `card_decision`, `program_decision` and parts of
  `step`, `cards`, `programs`, `finalize` in `T/chain.py`; the card and engineer areas edit `cards` / `programs` too,
  so the gate area should be implemented after them.

## 6. Risks and open questions

1. tau per comparison or one tau per step? D5's formula uses the incumbent's own repeats, so the card gates after a
   merge and the program gates after a card get their own tau. Recommended: per comparison, as written here;
   `decisions.json['tau_points']` keeps the C0 value as the step's headline.
2. The accepted card's R runs become the program baseline. They were selected for being high, so the program gate is
   somewhat conservative. Recommended: accept (D5 orders the sharing); `shared_from` makes it visible offline. The
   alternative costs 3n fresh cells per accepted card.
3. "All n * R cells" pauses the chain on any unknown gate cell (1.7). If judge-unknown outcomes are more than rare,
   the chain pauses often. Recommended: keep the pause; before launch count `unknown` in typed-v1's gate units
   (readout `unknown_by_token`); if it is above about one per unit, ask the owner for one automatic in-process re-run.
4. "Fired" with R cells. Recommended: an item is fired when the candidate fired in any of its R cells;
   `fired_cells` records the count so a stricter reading can be recomputed.
5. Caps. Recommended: keep 150,000,000 / 170,000,000, and before `prepare` project typed-v2 learning from the real
   typed-v1 ledger (`per_unit`): noise and no-harm units times 1.5, card and program gate units times 3, minus the
   gate share of `outcomes` and `outcomes-card`. Fix another value only if a chain's projection passes 80 % of its cap.

Note [I]: with F6's 31 flips per 100 items between two runs, about 46 items are mixed over three runs, giving SE about
3.2 and tau about 6.4 points for G ZebraLogic (typed-v1: 11.18). This is an estimate, not a result.

## NOT DONE

- Length: this file is about 340 lines, over the 230-line target; nothing was cut because every part answers a
  required point. A shorter version needs the coordinator's choice of what to drop.
- Not opened: `T/reads.py:1-270` (the "no change" row rests on lines 290, 334-347, 361, 436-458) and the full bodies
  of `tests/test_typed_e2e.py` and `tests/test_typed_readout.py` (their rows in 4.2 come from the cited lines only).
- The real typed-v1 ledger was not read (no ssh in this task): the cap statement in 1.9 rests on the design estimate.
