# rc-readout: read-only review, lens = readout and the owner's 5x5

Scope: `git diff de7346c` (this batch) in the context of `git diff 8375ecb`.
Reviewer edits nothing in the tree except this file. Scratch: /tmp/typed2-neutral/rc-readout/.

## Plan (checklist)

- [x] Read binding docs on the readout: ADDENDUM (D16, D17, RP1-RP15), DESIGN readout part, spec/read-plan.md readout sections
- [x] Read T/readout.py diff (whole new readout code) and T/readplan.py readout helpers
- [x] Check: no by-construction difference printed as a measured number
- [x] Check: aliases show the representative, marked
- [x] Check: macro means (RP4) and max metrics (RP5)
- [x] Check: C0 = no-skill row, C = start (D17)
- [x] Check: related gain (D16)
- [x] Check: generalization view (home / same type / other type)
- [x] Check: in-run replicates print 0
- [x] Check: full-mode readout unchanged versus 8375ecb
- [x] Build a synthetic economy chain dir and render the markdown; read it as the owner would
- [x] Run the readout tests (3.11 and 3.13 if available)
- [x] Write findings

## Progress notes

- Synthetic economy chain: T20 fixture of tests/test_typed_readout.py rebuilt under /tmp/typed2-neutral/rc-readout/econ1
  (build_econ.py); open markdown read in full. Variant with noisy in-run replicates: econ2 (variant_noise.py).
- Full mode: de7346c vs now on make_root (full_cmp.py): documents equal in both modes; markdown differs only by the
  schedule/phase line of Step 6 (S10); status gains schedule/phase/current_unit/read_plan (R73, S10). Intended.

## Findings (final; details in the structured output of rc-readout)

1. must-fix, readout.py:1302-1318 `_bench_metrics_economy` (and the header "S0 := C0", docstring :18-26): under
   base `historical` (D17: C is the start of learning) forward_transfer = acc(S_{k_b-1}) - acc(C0) and plasticity at
   k_b = 1 = acc(S1) - acc(C0) carry C's own hand-card gain over C0. Fixture econ1: officeqa forward transfer +25.0
   although S1 sends exactly C's requests on officeqa (class {C, S1, S2}); searchqa plasticity +50.0 while gain vs C
   is +25.0 and the generalization view (S0 = C) says +33.3. In a run that learns NOTHING, every non-ZebraLogic
   forward transfer and SearchQA's plasticity would print C's own advantage over C0 (the D17 reason puts what C
   gives at 11 to 20 points on three bench-chain pairs) as learned transfer, and the macro rows average it. Fix:
   S0 := the base event (BASE_EVENTS[base_card]) in the economy CL terms, header (:2039), definitions (:1364) and
   docstring; full mode untouched.
2. must-fix, readout.py:1245-1299 `_term` / `_rp4`, :1985-1993 alias rows of the 5x5: a contrast between two fresh
   units with identical requests (fallback class, re-read of a voided alias, void plan) is labelled "noise sample,
   not an effect" in the contrast tables, but the CL terms print it as a measured effect, the RP4 maximum takes it,
   the macro means average it, and 5x5 alias rows print it without the label. econ2: spreadsheetbench forgetting
   +25.0 / backward transfer -25.0, alfworld forgetting +25.0; econ3 (C a fallback with C's requests = S1..S5):
   alfworld "gain vs C +25.0" (macro (b) +25.0, n = 4 of 4) and 5x5 S<k> - C rows 1-4 "=S5 +25.0" while row 5 says
   "+25.0 noise sample".
3. must-fix (labels only), readout.py:1368-1399 `_bench_types` / `_generalization`: the relation comes from sources
   only, so a bench not learned yet is always "other", even when its test items are routed into the home type
   (same signature: OfficeQA vs SearchQA's type at S1, D16 e) and its requests changed; an earlier bench routed into
   the type (RP15) is "other" too. The cells carry `mount.type`, so the share routed into the home type is known.
4. minor, readout.py:1224-1229 / :1985-1990: a 5x5 alias row dereferences only the representative's VALUE: a pair
   inside one class prints "=S3 —" (looks missing) instead of "-", a split pair prints "—" instead of "split".
5. minor, readout.py:1274-1299 `_rp4`: an earlier event that is pending / invalid is dropped silently
   (`missing_terms` is never printed); econ1 zebralogic forgetting "-25.0" although S4 shares S5's planned class.
6. minor, readout.py:1675-1688 `_md_related` (batch 2): "home gain pts" of a program row is the fired-items gain,
   printed beside each member's whole-slice related gain.
7. minor (ops display), scripts/run_typed.py:241-258 `read_counts` vs readout.read_counts: the terminal and
   `status` print different fallbacks / void_aliases / fresh_planned for one state (econ1: 1 / 4 / None vs 2 / 5 / 18).

Checked and found sound: same-class dash rule in contrast tables, 5x5 representative rows and generalization view;
alias marks with u/i/c in grid, panels, CL level columns and closed mode; R68 baselines through class
representatives; RP5 split rule (reference block, `mixed`, `split only`); in-run replicates printed beside every
contrast, 0 when no identical-request pair exists; R71 fresh-only tokens; R72 planned rows; R74 refusal; full mode
document byte-equal to de7346c in both modes (markdown adds only the S10 schedule line); D16 related-gain table keys
match the chain's member records (bench, n, repeats, gain/se/tau, b/w/t, no_regress, baseline, baseline_selected).

## Tests

`TMPDIR=/tmp/typed2-neutral <python> -m pytest -q -p no:cacheprovider tests/test_typed_readout.py`
-> `21 passed` (Python 3.13; no 3.11 on this Mac). Scratch scripts: /tmp/typed2-neutral/rc-readout/*.py.

Done
