# Ticket fixer-7 → main agent / owner: the sandbox policy hash changed (pre-launch)

From the fixer (2026-10-22). Isolation review finding 9.

To close the second half of finding 9 (a procedure can open other workbooks through pandas), `policy.POLICY` now
also forbids the attributes `ExcelFile`, `ExcelWriter` and `HDFStore`. The first half is fixed in
`sandbox/client.py`: the input mount must hold exactly one regular, non-symlink `input.xlsx`.

The fixer regenerated `skillopt/execskill/sandbox/policy.json` on dl with `policy.write_policy_json()`. Its sha256
(`policy.policy_sha256()`, the manifest's `sandbox.policy_sha256`) changed:
- old: `d19cbe494f0c098f583af6c7a40a8ccd1f0a17f6c026885643ae4d8f5132fc7d`
- new: `b21d2f0337f98eee814834a67de7965f0af6489104ea3b7a746cc07686a8c926`

The worker reads the host's `policy.py`, which is mounted read-only at `/runner/policy.py`. The image therefore
needs no rebuild; a worker built from the old file refuses `load` with `policy_mismatch`.

`write_policy_json` says that "a changed policy needs a new protocol version". The fixer treated this change as a
pre-launch build fix, because no `fivebench-execskill-v1` manifest has been sealed for a run. Requests:
1. Main agent: confirm that no sealed manifest or S0 record pins the old hash. Notes `A3.md:9` and
   `integration-B2 sandbox and shell.md:188` quote it as historical build notes; add an erratum line there if you
   want.
2. Owner: confirm that the change belongs to v1 and needs no new version.
