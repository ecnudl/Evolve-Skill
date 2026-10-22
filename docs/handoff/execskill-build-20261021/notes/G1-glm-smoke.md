# G1 progress note: chain-G (GLM-5.3) smoke for fivebench-execskill-v1

Worktree: /data/execskill-dev-g, branch research/exec-skill-glm-smoke (from a6f49d3).
Brief: registrar addendum 2026-10-23 02:3x ("smoke solver chain"). Zero paid calls; fakes only.

## Status
- worktree created; code read (smoke, smoke_roles, step, manifest, chain, units, budgets, routes, run_execskill,
  frozen GLM client receipts, mutation suite, rehearsal tests, runbooks).
- baseline at a6f49d3: 1393 tests collected (tests/test_execskill_*.py + tests/test_weak_solver_probe.py),
  112 mutation entries.
- finding: no main-run code needs stages/S1.json (read_estimate_record needs smoke-result + SE6 only; routes.pin and
  check_clients accept branch N longest 256 with no S1 record). Operator runbook steps (smoke §5 pins builder,
  main §2 go-check, §3.2) do read S1.json -> covered by the new runbook sections.

## Design (implemented)
- protocol: SMOKE_SOLVER_CHAINS = ("D", "G"); SNAPSHOT_ROOT -> source-c.
- smoke.make(..., solver_chain="D"): D spec byte-identical; G spec: solver block with "chain": "G", glm-5.3,
  M 65,536, read timeout 2,400, echo ["glm-5.3"], null elucid fields, probe_root null, no control cells, stages
  without S1.
- smoke.solver_of(spec) -> chain/model/echo; used by _endpoint, _confirmed, _confirm, _unit, _backends, run_stage S2
  bound, _s4/own_run (SmokeStep.model), manifest._solver_chain/_smoke_pools.
- run_probe and CLI probe refuse a G spec; receipt_classes demands s1e == [True] only when S1 is a stage.
- real G smoke credentials: --env-path and --roles-repo both = the manifest G block env_path (the GLM repo).

## Done (10/23 03:1x dl time)
- code (protocol, smoke, smoke_roles, step, manifest, scripts/run_execskill.py); chain-D spec verified identical to
  a6f49d3's (every field but the code map and record hash, default and named probe root).
- tests/test_execskill_glm_smoke.py: 12 tests; the 11 fast ones pass (2 s); the chain-G CLI rehearsal passes
  (191 s): smoke-result required S0 S2 S3 SE6, S1/S4/SN1 not_required, passed; rows S0 14, S2 7, S3 6, SE6 159,
  all pass. Related existing files (smoke, manifest, protocol, step tests): 104 passed.
- mutation entries 112-122 (sitecheck: 123 entries, every site found once).
- runbooks: "Chain-G smoke (registrar addendum 10/23 02:3x): this run" sections in smoke-runbook.md and
  main-runbook.md.

- mutation entries 112-122 run on their own: 11 passed in 86 s (each new guard's mutation makes its named test fail).
- full suite (tests/test_execskill_*.py + tests/test_weak_solver_probe.py, 1416 collected; 1393 at a6f49d3) started
  03:16:59 and was stopped on the registrar's instruction at 03:30 (SIGTERM, exit 143): 322 of 1416 tests had run
  (about 22 %), all passed, no failure or error seen. Registrar: S0's pytest row on snapshot c runs the same full
  collection and serves as the full-suite gate (the two runs must not overlap on /tmp inodes). This run's pytest
  temporary directories (/tmp/pytest-of-root/pytest-110..113) were removed.
- no code changed after the registrar's Codex review of the working tree (03:18).

- committed as 344ddcc (report sent).

## G2 (registrar addendum 2026-10-23 05:3x), on top of 344ddcc
- research.USER_AGENT gains CONTACT (https://github.com/ecnudl/Evolve-Skill); nothing else in the research client.
- protocol.SMOKE_WAIVER, WAIVABLE_SMOKE_ROWS = {S2.format}; smoke.waiver(root, result), fail closed;
  chain.read_estimate_record accepts a passed smoke or a valid waiver and records "waiver"; CLI smoke-waiver --spec.
- SNAPSHOT_ROOT -> source-d; runbook sections (archive c, re-smoke on d, go-check with the waiver, owner-only file).
- tests: tests/test_execskill_smoke_waiver.py (20), 2 UA tests in test_execskill_research.py, the estimate print in
  test_execskill_cli.py; mutation entries 123-135 and entry 46 moved to the new gate text.

- affected files (research 16, smoke 26, chain 35, manifest 21, cli 37, glm_smoke 12, smoke_waiver 20, protocol 36):
  203 passed in 26:51; mutation entries 46 and 123-135: 14 passed in 80.6 s. Collection: 1451 (1416 at 344ddcc).
  The whole suite is S0's pytest row of the re-smoke on snapshot d (registrar).

## Next
- commit on research/exec-skill-glm-smoke; /data/execskill-dev-g-G2.patch; report.
