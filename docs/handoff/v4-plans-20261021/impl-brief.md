# Implementer brief for protocol v4 (fivebench-coevolution-v4) — read fully before touching any file

SCRATCH = /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad
Spec (ground rules, items B1-B17 / P1-P7, decisions): SCRATCH/v4/spec.md  (read §0 and §3 fully, then your group's items)
Plans (final, critic-revised, one per group): SCRATCH/v4/plans/G1.md .. G6.md
Working trees (full copies of the repository WITHOUT .git/data/outputs): SCRATCH/v4/trees/<name>
Patches: SCRATCH/v4/patches/<group>.patch      Implementer reports: SCRATCH/v4/impl/<group>.md

## Hard rules
1. Edit ONLY inside the working tree named in your task. NEVER edit the real repository
   /Users/dulin/Documents/Paper/SkillOpt (other agents are reading it) and NEVER edit anything under docs/ (the main
   session writes the registration delta and living docs). Do not run git commands that change state anywhere.
2. Never read test pools (paths containing TestAccess, test_panel, evaluation/, shared/test/, or names with
   final|test|holdout|held_out|verifier_calibration|reserve). Never print .env files, API keys, tokens or proxy
   credentials. No network calls; tests use the fakes in tests/coevo5_fakes.py only.
3. Implement every item of your group whose plan status is `planned`. Items the plan marks `needs_decision` are NOT
   implemented (list them with the question). `not_applicable` items are skipped with the plan's reason.
4. Before replacing a "current code" excerpt, verify it exists at the named place. If the real code differs from the
   plan (the plan may be stale or wrong), adapt the change to the real code, keep the plan's semantics, and record the
   deviation in your report. If a plan step would break a registered semantic the spec does not list, do not do it;
   record it as a deviation with the reason.
5. Style: dense module/function docstrings citing the registration ("v3 §9"); v4 changes cite "v4 B1"/"v4 P4" etc.
   No new third-party dependencies. Keep frozen v3 behaviour for everything the spec does not list.
6. Tests: every item gets at least one new or changed unit test using the existing fakes. Run the suite from the
   working-tree root (its own package is imported because tests/__init__.py makes the tree root the import root):
       cd <tree> && python3 -m pytest tests/test_coevo5_*.py -q -x -p no:cacheprovider
   Baseline on the pristine tree: 704 passed, 1 skipped (39 s). The suite must pass when you finish. If you also
   touched skillopt/continual_eval/backends.py, additionally run tests/test_continual_eval*.py and any test file that
   imports backends (grep). Do not weaken or delete existing assertions to make tests pass unless the plan says the
   registered behaviour changed (then say so in the report).
7. Produce the patch exactly as instructed in your task (diff -ruN between the named base tree and your tree, excluding
   __pycache__ / *.pyc / .pytest_cache), and write the report SCRATCH/v4/impl/<group>.md (English, concise):
   per item: status implemented | needs_decision | not_applicable | deviated; files and functions touched; tests added
   (names); deviations from the plan with reasons; the registration-delta sentences for the main session; open
   questions; the final pytest tail (counts).
8. Return (as your final text) the same content as the report in compact form. Do not ask questions; decide and record.
