# Adapted public coding tasks for the validator pilot

This directory supports a small local research pilot, **not a canonical
SkillEvolBench reproduction or a new public benchmark score**.

## Provenance and permissions

- Upstream: <https://github.com/AIoT-MLSys-Lab/SkillEvolBench>.
- Pinned commit: `9e3daa339987c3cfa624121e1be442593a53d43c`.
- `upstream/` contains 91 original text snapshots for nine named tasks, acquired
  read-only and preserved for provenance. Every task manifest records content
  hashes and exact upstream URLs.
- The inspected upstream tree supplied **no root LICENSE file**. Publicly
  readable does not imply permission to redistribute. These snapshots are for
  the user's local research; review upstream licensing/permission before any
  public commit, package distribution, or release containing them.
- Original author README fixture plans sometimes explicitly describe hidden
  tests. Those README plans are **not supplied to solver or judge prompts**.
  The adapter uses independently written behavioral fixtures, not the upstream
  hidden verifier scripts. All requirements tested are stated in the adapted
  contract or preserved visible source behavior.

## Scope and units of analysis

| Split | Original family | Distinct task IDs |
|---|---|---|
| train | E1-LS4 multi-file bug fixing | T1, T3, T6 |
| dev | E1-LS5 merge conflict resolution | T2, T4, T6 |
| holdout | E1-LS3 safe refactoring | T5, T6, T4 |

There are **nine task identities and only three original latent-family
clusters**. Multiple behavioral checks or model draws are not additional
independent tasks/projects. There are no synthetic identifier/profile variants.
Our split intentionally differs from the upstream learning/deployment split;
original roles remain recorded. Three families cannot support population-level
claims about all coding tasks, cross-domain transfer, or statistical safety.

Original Python components are flattened into one executable module. Local
imports are removed; safe standard-library imports remain. All source file
snapshots stay unchanged. The adapted prompt explicitly states additional
single-module contracts and limitations. Original Docker, filesystem edits,
coverage-tool use, docs/version updates, filesystem plugin discovery and most
process-quality checks are excluded. Plugin registration is explicit and file
output is disabled. Thus adaptations preserve meaningful executable dependency,
precision, merge and regression problems, but **do not preserve the full original
agent workflow or original difficulty**.

## Oracle and controlled stress fixtures

`tasks.py` materializes requirements, public cases, private cases and reference
code before target calls. Candidate processes receive code and fixture inputs,
never expected answers. Host-side comparison records requested and preserved
behavior separately; public observations and private diagnostics are distinct.
Exceptions required by the contract are valid outcomes. Schema/syntax/import
contract violations are observed failures, not excluded missing data.

Reference outputs are checked against manually specified fixtures and a separate
statistics calculator. Statistics float comparisons use small tolerances;
monetary strings are exact or numerically checked with Decimal according to the
declared contract. This is a finite behavioral oracle, not a proof that all
possible inputs or every refactoring-quality requirement is correct.

Each task has three separately labeled controlled artifacts: starter,
reference, and a deliberately damaged reference. All nine damaged references
pass visible examples and fail private checks. Four are specifically named
`preservation_mutant`: all requested checks pass but preservation checks fail.
The other five are `generic_mutant`, because they also fail a requested check.
**These are controlled stress examples, not observed natural model errors or a
natural negative-transfer prevalence estimate.**

## Execution isolation

Candidate code runs only under macOS `sandbox-exec` with deny-default policy,
read access to the exact Python environment and necessary system libraries,
literal ancestor directory metadata, no workspace/private-home-subtree reads,
no writes/network, and process execution restricted to the current interpreter.
Environment contains only PATH; isolated Python startup disables user site paths.
An AST contract and limited standard-library proxies add defense in depth.
SQLite is in-memory only, ATTACH/DETACH are denied and extension loading or
authorizer replacement is forbidden.

Limits: 5 CPU seconds, 12 wall seconds, 250000 output characters, and a parent
watchdog checking RSS against 384 MiB every 50 ms. macOS on this host rejected
finite RLIMIT_DATA/RLIMIT_AS: RSS monitoring is **not a hard allocation barrier**
and can briefly overshoot. Unsupported sandboxes fail closed; there is no
unsandboxed fallback. Run `sandbox_probe()` before any target experiment.

`conftest.py` prevents pytest from collecting intentional upstream broken task
fixtures as repository tests. Local adapter tests live in
`tests/test_validator_pilot_tasks.py`.
