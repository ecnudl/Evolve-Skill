# Ticket fixer-5 → owner / registrar: one ledger halts both chains (cross-chain halt scope)

From the fixer (2026-10-22). Safety review finding 1; registration §4.1, §9.3, §14 (REG 39, 353, 417, 843-844,
915-916, 1007-1008); `budgets.py:85-104`, `chain.py:247`; frozen `coevo5/budget.py:276-297`.

There is one ledger per run root (`<root>/shared/ledger`), and `budgets.caps()` declares both chains and one
`overall` cap in it. The frozen ledger's halt counter is global. So a completion above B, or a leaked reasoning
reply, in either chain refuses every open attempt of **both** chains at their next reservation. That includes the
other chain's GLM role calls and a test read in progress. A frozen-ledger quarantine reaches just as far. The
registration says that each chain pauses on its own; it never says that a halt crosses chains.

The fixer did not change this, because both remedies change registered behaviour:
- (a) one ledger root per chain (`<root>/<chain>/ledger`), each with its own `overall`. The registered single overall
  cap then has to become two caps, or be checked by a separate supervisor; or
- (b) keep one ledger, and state in §4.1, §9.3 and §14 (and the owner-facing text) that a halt in either chain stops
  both. Add the recovery steps for the chain that did not cause the halt.

Either way, add a test: a breach under `D:` scopes refuses a `G:` attempt (b), or does not refuse it (a).
Note: ALFWorld branch E has B = 2,048, and REG itself says that a typical reasoning leak triggers the halt there.
