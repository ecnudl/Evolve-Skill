# Step rp-ro: the economy read plan's readout (spec/read-plan.md 1.F, T20)

Implementer report (step id rp-ro, batch 3). 2026-11-12. Sources: spec/read-plan.md 1.F (R63 to R74, R89, R90),
sections 3 and 4 (T20); addendum D10 d, RP1 to RP12, D16 (related gain), D17 (base card C; C0 stays the no-skill row).
`T/` = `skillopt/execskill/typed/`. Starting point: commit de7346c plus the uncommitted Step 6 (6s) work; agent rp-int
edits `T/readplan.py`, `T/chain.py`, `T/prepare.py`, `T/smoke.py`, `scripts/run_typed.py` and their tests at the same
time (none of them touched here). Files of this step: `T/readout.py`, `tests/test_typed_readout.py`, this report.
No earlier attempt existed.

## Plan

- [x] Read 1.F, 3, 4 (T20), RP1-RP12, D16, D17, the current `T/readout.py`, `T/readplan.py` record shapes.
- [x] Resolver `_resolve(root, chain)` from the state, checked against the plan (self-hash) and alias records (R63).
- [x] Loading: fresh units only under their own event; `of` = the alias map; consumers get nothing for aliases (R64).
- [x] Closed mode: `_aliases(chain_dir)`, alias pairs as `same requests as <event>` with u/i/c (R65).
- [x] Marks `=X v u/i/c` in tables, export objects `{value, source, of, independent, kind}`, legend (R66).
- [x] Deltas: dash rule inside one class, identical-request labels on first inputs, reference block for split
      phase with time ranges and splitting recoveries (R67, R89, R90).
- [x] Baselines from class representatives (R68); `in-run replicates: n` beside every contrast; practice-side gate
      noise beside the read tables (R69, RP7).
- [x] Macro: two columns (a) structural zeros as 0 with k, (b) measured mean with n; `mixed:` rule; RP4 max rule
      for `forgetting` / `forgetting_after_home` (R70).
- [x] Costs over fresh units, economy line (R71); mount checks over fresh units, alias planned columns (R72).
- [x] Classes block and status read counts (R73); refusals (R74).
- [x] Generalization view: per step k and bench b, S<k> minus the previous state, home / same-type / other-type.
- [x] `full` roots render as today (unchanged tests plus an equality test).
- [x] Tests `tests/test_typed_readout.py`: T20 with synthetic chain directories, UNPATCHED typed-v1 cases.
- [x] Final full run of `tests/test_typed_*.py tests/test_typed2_*.py`; failures in rp-int's files named (none).

## Done

`T/readout.py` (all typed-v1 functions unchanged; a new section "economy read plan" plus small hooks):
- `read_plan_mode(state)`: `economy` iff `state['read_plan']['mode'] == 'economy'`, else `full` (typed-v1 states too).
- `_resolve(root, chain)` / `_resolve_chain(chain_dir, state)` (R63): per pair `{source: fresh | alias | void_alias |
  pending | invalid, of, class, independent}` from the STATE. Bound plan through `rp.load_plan(file_sha256,
  plan_sha256)`; alias records through `_aliases` = `rp.load_alias` with the representative's mirror
  `aggregate_sha256` and u/i/c counts (R44 a). An alias stands only when its record verifies, names the state's
  `alias_of` and `alias_sha256`, and the representative is a complete fresh unit (R46 fresh rule); else `invalid`
  with a fixed reason. A record without an alias state entry is `stale_alias_record` (reported, never shown). A void
  plan: every pair its own class. Full: every pair `fresh` (R6). `read_counts` (R71, R73): `{settled, of: 35,
  fresh_done, fresh_planned, alias, fallbacks, void_aliases, pending, invalid}`.
- Closed mode (R65): `read_plan`, `resolver`, `aliases` (own block), `stale_alias_records`, `classes` (R73: members,
  representative, plan status / reason, how each member is settled, check counts, representative u/i/c, the bench's
  post-read mismatch), `economy` counts, `planned_mount`; the mirror table and `_closed_mount_check` stay over
  fresh mirrors, the aliases' plan counts are listed as `planned`. Markdown: alias table with `same requests as X`,
  u/i/c (zeros included), check and verification; economy line `a pairs aliased, f fallbacks, v voided aliases`.
- Open mode (`_open_economy`): only `fresh` pairs are loaded (`_load_fresh_unit`, `_project_economy` = typed-v1
  `_project` + returned model ids + first inputs, ids and hashes only), unit time ranges per R90 (killed attempts
  from cell file times); `_Phases` (R89: model-id sets, recoveries with pause or crash bound, owner `same_phase`,
  24 h). Per bench: marks of all seven events, fresh summaries under their own event, the typed-v1 contrast names
  resolved by `_contrast` (same class: `delta` null, `-`; two classes: from the representatives with the requests
  label `identical | different (d of n items) | unverified` on first inputs; split: reference only), in-run
  replicates (distinct representative pairs with identical requests), same-request noise on fresh C0/C only.
  5x5 objects (`diff_points_vs_C0`, new `diff_points_vs_C`, `accuracy_L/H`) per R66; CL terms through the
  resolver (structural 0 inside a class, split = reference), RP4 maxima with the split rule, macro columns (a)/(b)
  or `mixed: k same-phase, m split, no mean`; reference block grouped by representative pair with every contrast
  name, both time ranges and the splitting recovery numbers or `model ids differ`; the generalization view; gate
  noise per step (RP7); mount check over fresh units with planned alias rows (R72); `read_tokens` fresh only. A plan
  that fails (R74): `read_plan_error` only, and the markdown prints the error and no read table in both modes.
- `status` (R73): every chain gains `read_plan: {mode, plan_sha256 (short)}`; economy chains also `error`, `void`
  and `reads` counts. `_md_state` (economy only): the read-plan line and the R71 economy line.
- Markdown of an economy chain: event grid (alias cells `=X v u/i/c`), panel tables, contrast tables with the
  in-run replicates column, reference block, 5x5 with marks, CL tables with both macro rows, generalization view
  (`+3.0 (home)`, `- (same)`, `+0.0 noise sample (other)`), classes block, stale records, units not loaded.

`tests/test_typed_readout.py` (+11 tests; the 10 earlier ones untouched): an economy fixture built with the real
`readplan` core (plan, alias records, state entries `rp.alias_state_entry`): fresh, alias, void-alias (post-read
mismatch on SpreadsheetBench, S4 re-read), fallback (ALFWorld S2), stale record (ZebraLogic S4), officeqa = the
layout example's B1. Cases: resolver and counts; the UNPATCHED typed-v1 `_open` (one assertion per consumer) and a
git check that these consumers are byte-equal to 8375ecb; open economy readout (marks, dash rule, objects, RP4 B1,
macro (a)/(b), replicates, u/i/c, gate noise, no text, every alias marked once in the grid); closed mode (no sealed
open, alias listing once each, all_present, planned rows, status); verification (edited record, rebuilt mirror,
tampered plan: no read table in either mode); split phase (recovery without `same_phase`, model ids differ,
reference block, `mixed`, RP4 `split only`, then `same_phase: true` with a 2 h pause does not split); crash bound
(10 min with `same_phase`: no split; without: split; no earlier file: split; killed attempt range from cells);
generalization view; a `full` state equals a state without a read plan; projected cells hold ids and hashes only.

## Tests

Command: `mkdir -p /tmp/typed2-neutral && cd <repo-root> && TMPDIR=/tmp/typed2-neutral
<python> -m pytest -q -p no:cacheprovider tests/test_typed_*.py tests/test_typed2_*.py`.
Last line: `647 passed in 43.26s` (Python 3.13). No failure, so none in rp-int's files. `tests/test_typed_readout.py`
alone: `21 passed` on Python 3.13 and on Python 3.10 (`<python-env>`); no Python 3.11 exists on
this Mac (the Linux run is ops').

## Choices

- `full` is untouched: no new key in the document and the same markdown (tested by equality with a state without a
  read-plan entry); the typed-v1 consumers keep their source byte for byte, which is what makes T20's "UNPATCHED
  `_open`" case testable in-tree. Only `status` gains `read_plan.mode` for every chain (R73).
- A fresh state entry is the unit's counts-only mirror, whose own `kind` is `'read-status'` (T/chain.py `reads`), so
  `kind` absent, `fresh` or `read-status` means fresh; `alias` and `void_alias` as in 3.6.
- Alias cells print the representative's reading again, marked: `=S5 75.0 u/i/c 1/1/0` (D10 d and the ACCEPT
  sentence "aliases show the representative's reading marked with its event"); the JSON keeps `value: null`,
  `of: S5` (R66), so a consumer dereferences on purpose. 5x5 difference rows of an alias likewise print `=X v`.
- Contrasts keep typed-v1's names (S<k>-C0, S<k>-C, S<k>-S<k-1>); a contrast between two classes shows its number
  from the representatives with `of` (the representative pair); `independent` only when neither side was
  dereferenced. In-run replicates per bench = distinct representative pairs with a measured identical-requests
  contrast (R69), chain total beside.
- Same phase: window = earlier start to later finish; a recovery without a readable `at` and a unit without a time
  range split (fail-safe). The crash bound scans `cells/*.json`, `done.json`, `done-stopped-*.json` under the chain
  and the plan files (`read-plan.json`, closed names in the sealed plan directory and `read-alias/`).
- RP4 with only split other-class terms prints `split only` (R70) even when by-construction terms exist, instead of
  the structural `-`, so a possibly positive forgetting is never shown as 0.
- Level macros (final, C0, C): one mean through the representatives, labelled with how many benches were read via
  a representative; difference macros as R70.
- No `latest` block under economy (S5 is read first on all five panels, R36).
- Generalization view: S0 = the base row (C under `historical`, C0 under `format`, D17); relation from
  `s<k>/typemap.json` through the manifest's pool pins (`tasktypes.source_id`), `type unknown` when the home bench
  has no type; a cell with identical requests says `noise sample`.
- R74 suppresses the closed mirror table too (the error only).

## Disagreements

- Spec layout example vs D10 d / ACCEPT: the example prints `=S2 0/0/0` without the value; D10 d (higher precedence)
  and the step's ACCEPT ask that the representative's reading is shown, marked. Followed D10 d (JSON stays null).
- None otherwise.

## Left for later steps

- rp-int / `scripts/run_typed.py state_summary` (R73): add the read counts with `readout.read_counts(
  readout._resolve_chain(chain_dir, state), state)`; the smoke's 4.3 S2 (b) readout assertions (`=X`, fallback,
  classes block) can use `readout.markdown`.
- The resolver relies on the 3.6 state shapes: alias entries from `rp.alias_state_entry`, `void_alias` entries, a
  fresh re-read overwriting the entry with the mirror, `state['read_plan']` keys `mode`, `plan_sha256`,
  `file_sha256`, `void`, `void_reason`, `fallbacks`, `failures`, `replay`. If rp-int changes them, the resolver
  must follow.
- Step 7: `T/readout.py` now imports `T/readplan.py` (pure) and `tasktypes.source_id`; no new machinery symbol.
- Ops: the Linux 3.11 suite run alone.
