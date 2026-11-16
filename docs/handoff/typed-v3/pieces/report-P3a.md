# Report of piece P3a (gate arithmetic), as returned by its builder 2026-11-15 ~02:2x

Worktree <repo-root> (branch research/typed-skills-v3-gate, base d25619c).
Changed: skillopt/execskill/typed/gatestats.py (+248 / -5). New: tests/test_typed3_gatestats.py (25 tests).
The module still imports only __future__, math, fractions and collections.abc.

## (a) Functions added or changed

New constants: EVOLUTION_CARD_REASONS = ('accepted', 'gain_below_tau', 'not_more_better_than_worse', 'harm');
SCREEN_REASONS = ('passed', 'screen_never_fired', 'screen_below_baseline'); ITEM_CLASSES = ('real', 'attack',
'guard', 'calibration'); EVOLUTION_CLASSES = ('real', 'attack') (E = R + A).

1. `evolution_statistics(stats, items) -> block`: `stats` = repeat_statistics over J without a subset (or a stored
   decision holding it), re-validated from its own per_item. `items` = ids of E, list/tuple, in J's order,
   non-empty, unique, each in J (else ValueError; set/str/None -> TypeError). Built from J's own per_item rows with
   `_derive` on E's rows: E treated as the slice (own n_E, D_E, Q_E from the baseline's repeats on E, counts,
   tau_E = max(min, mult x se_E), reaches(D_E, n_E) with n = m = n_E and Q = Q_E). Block: {'item_ids', 'n',
   'difference_sum', 'variance_sum', 'gain_points', 'se_points', 'tau_points', 'better', 'worse', 'tied', 'reaches'}.
2. `card_decision_evolution(stats, evolution) -> {'kind': 'card', 'accepted', 'reason', <J's whole-list statistics
   exactly as card_decision>, 'evolution': block}`; re-derives the block from stats' per_item and
   evolution['item_ids'] and requires equality. Reasons in order: gain_below_tau, not_more_better_than_worse
   (better_E <= worse_E), harm (not no_regress on J, the flag no_harm_decision uses), accepted. With E = J the
   verdict and reason equal card_decision's on every input (reaches needs D >= 0, one of no_regress's alternatives).
3. `screen_decision(b, c, *, repeats, items, fired=None)` -> {'kind': 'screen', 'b', 'c', 'repeats', 'items',
   'fired', 'baseline_pass_points', 'candidate_pass_points', 'passed', 'reason'}; passes iff R*c >= b and, when
   fired is not None, fired >= 1; both failing -> screen_never_fired first. R int >= 2, items int >= 1, b in
   0..R*items, c in 0..items, fired None (card) or 0..items; bools refused. Docstring: screen cells never gate runs.
4. `screen_counts(baseline_cells, candidate_cells, *, items, baseline_arm, candidate_label, repeats) -> (b, c)`:
   baseline through arm_runs (all `<arm>#1..#R` present and decided per item); candidate one cell per item at
   `candidate_label` (bare arm name or `<arm>#<r>`); missing cell / infrastructure or configuration unknown ->
   UndecidableRuns; model-side unknown scores 0; non-binary correct -> ValueError.
5. `class_gains(per_item, classes, repeats)` -> {'real': row, 'attack': row, 'guard': row, 'calibration': row,
   'parity': {'calibration_pass_points', 'real_pass_points', 'parity_points'}}; row = {'n', 'difference_sum',
   'gain_points' (None when n = 0), 'baseline_runs_correct', 'candidate_runs_correct'}; parity from the baseline
   column only; `classes` must map exactly the items of per_item to ITEM_CLASSES.
6. `recompute` (changed): new kind 'screen' (rebuilt by screen_decision); a card record with `evolution` rebuilt
   from per_item + evolution.item_ids (shared types: member checks and shared_verdict as before); an `evolution`
   block on another kind raises; every typed-v2 record recomputes exactly as before.

## (b) Tests (Python 3.13.12)
- `TMPDIR=/tmp/typed3-gate-neutral python3 -m pytest tests/test_typed3_gatestats.py -q -p no:cacheprovider`: 25 passed.
- `tests/test_typed*.py`: 899 passed (874 + 25), 120 s. Python 3.10 (conda env `skill`): new file + test_typed_gate_stats.py 43 passed.
- Beyond the brief: Fraction property test (3,000 random cases), an exact tie on E that floats get wrong, an evolution
  card of a shared type, the reason order. Scratch (not in suite): 22 injected bugs all caught; 104,433 small-case
  decisions over every possible E match an exact Fraction calculation.

## (c) Departures
1. The record stores the ids of E (not a count and a hash): the purity test forbids hashlib; recompute needs them.
2. Screen record key 'repeats' (not 'R'); adds 'kind': 'screen' and two informational floats.
3. The E = J reduction holds unconditionally.
4. The evolution card keeps kind 'card'.
5. E out of J's order is refused; the class map must cover exactly J's items.
6. `screen_counts` returns (b, c); the caller computes `fired`.

## (d) What P3b must do
1. Re-export from gates.py: EVOLUTION_CARD_REASONS, SCREEN_REASONS, ITEM_CLASSES, EVOLUTION_CLASSES,
   evolution_statistics, card_decision_evolution, screen_decision, screen_counts, class_gains.
2. chain.compare('card') under 'evolution' on a step with made items: E = [i for i in J if classes[i] in
   EVOLUTION_CLASSES]; `card_decision_evolution(stats, evolution_statistics(stats, E))`. Without made items: today's
   card_decision (records byte-identical).
3. Check `evolution.item_ids` equals R + A from the sealed items.json (recompute only checks the block against
   per_item and the stored ids).
4. writers.revision_result and readout._decision_row read J's numbers and the old rule text; under 'evolution' the
   deciding numbers are in record['evolution'] and the reason can be 'harm'. The ids in evolution.item_ids must never
   reach a writer.
5. Screen counts: `screen_counts(entry['cells'], screen_cells, items=A+G in J's order, baseline_arm=entry['run_arm'],
   candidate_label=..., repeats=R)`; entry = the gate entry of the arm the candidate is compared with (shared arm:
   `_gate_entry` exposes the source's cells and run arm). Map UndecidableRuns to Paused, as chain.arm_runs does.
6. Screen decision: fired=None for a card (fired=0 would refuse it); program/package: fired = number of screen items
   whose cell's `fired` list holds its procedure id(s).
7. A decision refused at the screen has no per_item: recompute / recompute_decision raise on it. Route it, e.g. check
   `recompute(record['screen']) == record['screen']` and passed is False.
8. by_class = class_gains(decision['per_item'], the class map of J, R). For B's own parity pass rows [[i, S, S]] built
   from the noise record.

## (e) Open risks
1. E's membership is only self-consistent within the record (see d.3).
2. unknown_final covers J only, not split by E.
3. In a screen record, recompute cannot see a change of fired between positive values, nor of items/repeats when
   b = c = 0; re-derive from the cells if that matters.
4. The screen is a coarse filter: in a simulation with 60 % pass rate, a no-effect candidate passes about 51 %; a real
   +5-point gain is screened out about 14 % of the time on 140 items and 26 % on 40 items. A screen refusal is not
   evidence of no effect.
5. Not run on Python 3.11 itself (the 3.11 grammar check in the purity test passes).
