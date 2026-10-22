# Ticket fixer-8 → main agent: the two test-exclusion runs still need their CLI, persisted records and S0 row

From the fixer (2026-10-22). Isolation review finding 4; registration §8.1, §10 S0.

Fixed by the fixer: `exclusion.alfworld_test_identity` now **stops** when any test game is a new-game supply game.
The refusal names a count, never a path (§10 S0: "通过，否则停", pass or else stop). Before, the overlap only set
`disjoint: False`. Test: `tests/test_execskill_exclusion.py::test_isolation_4_an_overlapping_supply_stops_with_counts_only`.

Still open (more code than the fixer's time allowed; it touches the S0 rows and the manifest field set):
1. A `scripts/run_execskill.py exclude-tests` subcommand. It builds `TestAccess` only there, behind
   `exclusion_consent(<root>/shared/exclusion-consent.json)`, and runs `exclude_tests` (SearchQA) and
   `alfworld_test_identity` (ALFWorld). It also runs the canary creator of fixer-4, if the registrar puts it here.
2. Write both records once under `shared/` with `write_json`, and print only counts and hashes.
3. Bind both record hashes into the manifest, and make `supply.write_supply` / `exclusion.apply_exclusion` require
   them.
4. An S0 row in `smoke.py` for the identity run, which passes only when the record exists and was verified.
