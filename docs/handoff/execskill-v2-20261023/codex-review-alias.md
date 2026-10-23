# Codex review (one round): elucid echo alias + snapshot-f launch scripts — 2026-10-23 19:4x

Reviewer: codexdl `exec -m gpt-6-astra -c model_reasoning_effort="ultra" -s read-only` on a mirror of the dev tree
(no `data/`) with the alias diff (`git diff a1e47d8 -- skillopt scripts tests`, sha256 17370f34…f93ef) and the ops
scripts `/data/execskill-20261021-ops/main2f-*.sh`, `main2f_delta.py`, `elucid-alias-check.py`.

Verdict: **NOT ACCEPTABLE** (2 BLOCKER, 1 MAJOR), all in the launch scripts. The alias handling itself was judged
consistent: request id, credential check and slot/ledger keys unchanged; 432 in-memory comparisons matched for receipt
classification, reasoning check, over-nominal accounting, settlement and resend behaviour.

| # | Severity | Finding | Fix (no second round; the zero-call scripts are the smoke) |
|---|---|---|---|
| 1 | BLOCKER | `manifest.load(..., verify=False)` still runs `check_clients`, which re-derives the clients block with the loading code: under f it refuses the smoke manifest's (e's) client hash and chain D echo set before the delta checks run (go, pins, manifest scripts). | `main2f_delta.smoke_manifest()` loads the smoke manifest with snapshot e's own code (subprocess, `manifest.load(verify=False)`) and hands the checked value to the f scripts. |
| 2 | BLOCKER | `make-manifest` revalidates the sheet scorer's qualification from the checkout; the qualification pins its source files by absolute path, so q23-e (source-e paths) fails under source-f although the bytes are equal (`replay_sheet_v6.py:133`). | `main2f-q23.sh` builds q23-f and `sheet-runtime-f.json` from source-f (zero model calls, as `s2b-q23-e.sh`); `sheet_delta` requires q23-f's qualification and protocol to equal q23-e's once f's paths read as e's (record/protocol hashes excepted); the runtime block may differ only at `spreadsheetbench.recalculation.{qualification_path, qualification_sha256, qualification_hash}` (`runtime_delta`). |
| 3 | MAJOR | The delta checks constrained the changed file names, not the edits: a commit with the alias plus, e.g., a disabled reasoning check in client.py would pass. | `git_delta` also requires `sha256(git diff a1e47d8 f -- skillopt scripts tests)` = the reviewed patch's 17370f34…f93ef. |

Dry run on the dev tree (21:2x, before the commit): the smoke manifest loads under e; clients differ exactly at
`solver.{G,D}.client_source_sha`, `routes.D.B.client_source_sha`, `solver.D.response_model_ids`; the code map differs
only at `skillopt/execskill/client.py`; echo sets e = [1017], f = [alias, 1017], request id 1017.
