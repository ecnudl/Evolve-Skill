# Ticket fixer-4 → main agent / registrar: the registered test canaries have no creator

From the fixer (2026-10-22). Isolation review finding 10 (the creator part); Codex F16; registration §8.1.

Fixed by the fixer: the scan now covers the whole unit root, `shared/host_only/diagnostics` and `shared/test`. It
runs before the first call of every attempt and on every exit, pause and exception included (`evaluation._scanned`,
`unit_scan`). Paused attempts record their scan.

Still open: `evaluation.load_canaries` reads `shared/test-canaries.json`, a sealed `test-canaries` record of
{length, sha256 prefix} entries. No code writes that record. Making it needs test texts, so it must run under a
`TestAccess` and behind the exclusion consent, like `exclusion.exclude_tests`.

Requests (registrar to confirm, main agent to build):
1. Which texts become canaries: e.g. per bench, k test items' reference answers or question texts of at least
   `MIN_CANARY_CHARS` characters, chosen by a seeded order.
2. Where the creator runs: S0, inside the same consented test-exclusion unit (see fixer-8). It writes the record
   once, with `write_json`, and prints only counts.
3. `evaluate(...)` is called with `canaries=load_canaries(root)` by the `evaluate-unit` adapter (A13-1).
