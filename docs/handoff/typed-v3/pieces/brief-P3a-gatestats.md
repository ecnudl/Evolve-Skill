# Brief P3a: typed-v3 decision arithmetic (card rule on E, the screen's pass rule, per-class gains) in gatestats

You implement ONE pure, self-contained part of the next version of a research codebase: the arithmetic of the
typed-v3 decisions. The chain wiring (which units run, where the records go, the screen unit itself, reads, the
CLI preset) is a later piece (P3b) that will call what you build. Other pieces are being built at the same time in
other working trees; you must not depend on them.

## Where to work

- Git worktree `<repo-root>` (branch `research/typed-skills-v3-gate`, from
  commit `d25619c`). Work ONLY there. Do not commit, do not push, do not touch any other tree or repository.
- Files you may change: `skillopt/execskill/typed/gatestats.py` (ADD functions and constants; change an existing
  function only where `recompute` must learn the new record kinds, and then every existing record must recompute
  exactly as before). New tests: `tests/test_typed3_gatestats.py`. Nothing else (P3b will re-export names from
  `gates.py` and wire the chain).
- No network, no model call. Tests need TMPDIR to be a directory whose name contains no word like "test": use
  `/tmp/typed3-gate-neutral` (create it). Run `TMPDIR=/tmp/typed3-gate-neutral python3 -m pytest tests/test_typed3_gatestats.py -q -p no:cacheprovider`
  and at the end the whole typed selection `tests/test_typed*.py` (874 passed before your change; it must stay green).

## Read first

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md` T7 (the rules, owner-approved) and
   `<scratch>/typed-v3-design/build/brief-P3-gate-and-reads.md` sections A and B
   (you implement their ARITHMETIC only: A's card rule under `'evolution'` and B's pass rule; the units, records on
   disk, resume and the CLI are P3b's).
2. `skillopt/execskill/typed/gatestats.py` completely: the module docstring (statistics and their exact integer
   forms), `repeat_statistics`, `_derive`, `_subset`, `_reaches`, `_no_regress`, `card_decision`,
   `no_harm_decision`, `program_decision`, `member_decision`, `shared_verdict`, `recompute`; and its tests
   (`ls tests | grep -i gatestat`, plus the chain tests that call it).

## What to build

### 1. The card rule under `'evolution'`

`card_decision_evolution(stats_J, stats_E)` (name it in the module's style) where `stats_J` is today's
`repeat_statistics` over the whole gate list J and `stats_E` is `repeat_statistics` of the same two arms restricted
to the items of E = R + A (the real gate items and the judging-side attack items), computed as if E were the slice:
its own n, D, better/worse/tied, and its OWN Q from the BASELINE's repeats on the items of E (so tau_E =
max(minimum, multiplier x se_E) with se_E from Q_E and n_E). Accepted iff (1) `reaches(D_E, n_E)` with Q_E, (2)
better_E > worse_E, (3) `no_regress(D_J)` on J exactly as `no_harm_decision` defines it over all items of J. Reasons
in this order: `gain_below_tau`, `not_more_better_than_worse`, `harm`, `accepted`. Exact integer arithmetic as the
module does it; no float decides anything.

Provide a helper that builds `stats_E` from the per-item data of J and the list of E's ids, so the caller cannot
pass an E computed from other runs (an id of E that is not in J is an error; E must be non-empty; E in J's order).
The decision record keeps the whole-list statistics exactly as today plus an `evolution` block (the ids of E or
their count and a hash of the id list, n, D, gain points, se, tau on E, better / worse / tied on E) from which
`recompute` reproduces the decision from the stored record alone. When E = J (a step without made items) the rule
must give exactly today's `card_decision` verdict and reason on the same data, except that today's card rule has
no harm clause: check what today's card decision does about harm (the brief says "reduces exactly to today's
rules"; if today's card rule has no no_regress clause, then under `'evolution'` with E = J the harm clause is the
only addition: state this precisely in a docstring and test it; P3b will use today's function when a step has no
made items, so the reduction must be exact in verdict and reason whenever no_regress holds).

### 2. The screen's pass rule (P3 brief B)

A pure function for the screen: inputs the baseline's right-run count b over the screen items (A + G; R runs each,
from the arm the candidate is compared with), the candidate's right count c over the same items in its ONE run, R,
the number of screen items, and for a program or archive package the number of screen items on which it fired.
Passes iff R * c >= b, and for a program/package additionally iff fired >= 1. Record `{b, c, R, items, fired,
passed, reason}` with reasons `screen_below_baseline`, `screen_never_fired`, `passed` (choose and document the
order when both fail). Also a helper that computes b and c from the per-item cells of the two arms (exact
integers; the baseline's R runs per item must all be present, the candidate's one run per item must be present;
otherwise raise, as the module's undecidable rule does). Docstring: the screen's cells are never used as gate runs,
because a candidate that passed by luck would carry that luck into the gate.

### 3. Per-class gains (informational, decide nothing)

`class_gains(per_item, classes, repeats)` : for the per-item rows of a decision over J and a map item -> class
(`real`, `attack`, `guard`, `calibration`), the gain in points on each class (100 * D_class / (R * n_class)) as
floats for reporting plus the exact D and n; classes absent from the map are reported with n = 0. And the parity of
the baseline on calibration items against real items (pass rate on K minus on R, points), informational.

### 4. `recompute`

`recompute(record)` must reproduce every new decision (the evolution card decision, the screen record) from the
stored record alone, and every existing record kind exactly as before. Add the new kinds to whatever the module
uses to verify stored decisions.

## Tests (expected values computed independently, by hand where the numbers are small)

At least: default rules unchanged (existing tests untouched and green); a card with a gain on E above tau_E and no
regression on J is accepted; the same card with a regression on guard items beyond tau_J is refused with `harm`; a
card whose gain sits only on calibration items is refused (gain on E below tau_E); tau_E is computed from the
baseline's repeats on E, not on J (a hand-computed case with unequal variance on E and on J, where using Q_J would
flip the verdict); E = J gives today's verdict and reason when no_regress holds; better/worse is counted on E; the
screen passes exactly at R * c == b and fails at R * c == b - 1; a program that never fires on A + G fails the
screen; the b and c helper refuses missing cells; `recompute` reproduces each new record and refuses a tampered one
(change one stored number); `class_gains` on a hand-made case.

## Report back

Plain text for the engineer who reviews your diff and wires it into the chain: (a) the functions added or changed,
with signatures and the record shapes; (b) exact test commands and pass/fail counts (new and the whole typed
selection); (c) anything decided differently from this brief and why; (d) what P3b must do to use it; (e) open
risks. Never report a part as done that has failing or missing tests.

Keep a short progress note at `<claude-job-tmp>/build-P3a-progress.md`; if it exists when you
start, continue from it (the network may cut your session).
