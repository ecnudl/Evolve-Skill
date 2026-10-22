# PR-C31: the test read's canaries and the run-root scan (ticket C3-1, option (b); protocol fivebench-execskill-v1, route B)

PR-C31, 2026-10-22 12:4x-13:5x. Build tree `/data/execskill-dev` (mount `/Users/dulin/remote/dl`). Zero model calls,
zero network, no git command, no credential or test-pool file read, no frozen file edited. Throwaway dirs
`/tmp/PR-C31-*` (dl) and `/tmp/PR-C31-local` (Mac), deleted at the end.

Binding sources: registrar decisions 2026-10-22, row "C3-1 canaries" option (b) ("OfficeQA, LiveMath and
SpreadsheetBench canaries are made at the start of the pilot's test read under the owner's test-read consent, before
the first evaluation unit, as a second sealed record merged by load_canaries; then the whole run root ... is scanned
for all canaries before any score is unsealed; a hit pauses for the owner"); addendum 13:0x (pilot-readiness row,
built now, same single Codex round); addendum 13:2x (`shared/consent.json` by the owner only; the test read waits);
registration §8.1 (canaries: a few fixed texts per test set, never the text), Codex F16 (§20); tickets fixer-4,
fixer-8.

## Files changed

- `skillopt/execskill/evaluation.py` (1229 lines; mine):
  - :40-47 and :52-55 module docstring: the canaries bullet (two records, merged) and the unseal bullet (the run-root
    scan before the first unseal).
  - :66-77 imports `html`, `io`, `itertools`, `zipfile`, `zlib`; :83 `recovered`; :95-97 `RECORD_HASH`.
  - :103-106 `__all__` adds `make_read_canaries`, `root_scan`, `select_canaries`.
  - :117-131 constants `CANARY_BYTES`, `CANARIES_PER_BENCH` (5), `CANARY_TAG`, `READ_CANARIES`
    (`shared/test-read-canaries.json`), `READ_CANARY_UNIT` (`test-read/canaries`), `READ_CANARY_SOURCES`
    (livemath/officeqa `question`, spreadsheetbench `instruction`), `ROOT_SCAN` (`root-scan`), `ROOT_SCAN_SHOWN` (200),
    `DECODE_DEPTH` (3), `CACHE_MIN_CHARS` (256).
  - :394-513 `_canary_order`, `select_canaries`, `_checked`, `_canary_records`, `load_canaries`, `_benches`,
    `make_read_canaries`.
  - :516-560 `_utf8_width`, `_Windows` (the one matcher: windows of each canary length, sha256 prefixes, a text of at
    least 256 characters hashed once per scan by its blake2b digest; no text kept).
  - :563-575 `canary_scan` now uses `_Windows` (same files, same reading, same hits).
  - :593-669 `_document`, `_decoded`, `_root_texts`, `_where`, `root_scan`.
  - :967-1018 `run_unit_spec`: docstring; :1007-1008 makes the read record before the attempt; :1012 reads with the
    merged canaries.
  - :1096 `_marker(..., scan)`: the unseal marker gains `canary_scan` {"attempt", "record_sha256"}.
  - :1144-1189 `_scan_attempt`, `_root_scanned`.
  - :1192-1229 `unseal`: docstring; :1205 the scan runs before any unit is read.
- `tests/test_execskill_evaluation.py` (mine): :58-104 `S0_TEXTS`, `READ_TEXTS`, `ReadPanel`, `s0_canaries`,
  `register_canaries`; :277, :307, :325, :379 `register_canaries(root)` in the four tests that unseal (test_eval3 x2,
  the continuation check, isolation 12).
- NEW `tests/test_execskill_canaries.py` (297 lines, 8 functions, 10 tests).
- NEW tickets `tickets/PR-C31-1.md` (I1: `make_canaries` on `select_canaries`, `runcli.report` maps the scan's Pause
  to exit 3/5, usage text, `monitor`), `tickets/PR-C31-2.md` (I1, cc C7e: the e2e fixture patch, validated; mutation
  31), `tickets/PR-C31-3.md` (registrar: release of a coincidental hit, text kinds, scan cost, where the record is made).
- Not touched: `scripts/run_execskill.py`, `runcli.py`, `chain.py`, `readout.py`, `protocol.py`, the e2e and mutation
  tests, smoke files, frozen code.

## Public API (evaluation.py)

- `select_canaries(texts) -> (canaries, counts)`: per bench in name order, the distinct texts of at least
  `MIN_CANARY_CHARS` characters ordered by sha256(`CANARY_TAG` + bench + ":" + text), the first `CANARIES_PER_BENCH`;
  entries `canary(text)`. Refuses a bench with no eligible text. Same output as `run_execskill.make_canaries` (a test
  asserts it).
- `make_read_canaries(root, pinned, *, run, evidence, panel=data.test_panel) -> record`: `consent(root/"shared")`
  first (refused without it, before any panel is opened); requires the S0 record; under the lock
  `shared/test-read-canaries.lock` (wait): if absent, one `TestAccess("test-read/canaries")`, the three panels, the
  selection, the write-once record `test-read-canaries` {canaries, counts, per_bench, seed_tag, sources, unit, run,
  panels (panel hashes), consent_sha256, extends (the S0 record's hash)}; then checks run and consent. Prints nothing.
- `load_canaries(root, *, read=False) -> list`: the S0 record's canaries; with `read=True`, then the second record's
  (it must exist: "The test read's canaries are not made yet"). Both records are checked: entries exactly {chars,
  sha256_16}; counts per bench sum to the entries; the second extends this root's S0 record and covers exactly the
  three other benches.
- `root_scan(root, canaries) -> (files, hits)`: every regular file under the run root; a hit is {"where", "path",
  "canary"} (where = the first two folders, e.g. `D/s2-officeqa`, `shared/research`); refuses any symlink.
- `unseal(...)`: same signature. Before reading any unit of a chain not yet unsealed: a new attempt
  `<chain root>/root-scan/attempt-N` with `scan.json` (`root-canary-scan`: chain, files_scanned, hits, files_hit,
  canaries, canaries_sha256, by_where, by_bench, shown = the first 200 hits; never text). A hit writes `status.json`
  (kind `canary_hit`, scan_sha256) and raises `Pause("canary_hit", "<n> hits", "<chain>/root-scan")`; while that
  attempt has no owner `recovery.json`, every unseal raises `Pause("awaiting_owner_decision", "attempt-N", ...)`; after
  it, the next unseal scans again. An already unsealed chain re-verifies its marker's clean scan.

## Deviations, with reasons

1. The second record is made by the first `evaluate-unit` child (any bench, either chain) under a lock, after the
   consent check and before its attempt, not by a separate step before the children. No unit evaluates a test item
   before it exists. Reasons: the child already checks the consent and holds the manifest and the panel reader;
   `chain.evaluate` (not mine) would open three test panels in the chain parent. Registrar asked to confirm
   (PR-C31-3 §4).
2. `canary_scan` was refactored onto the shared `_Windows` matcher (one implementation, plus the repeated-text cache);
   reading and hits are unchanged and its tests pass unchanged.
3. The root scan reads `.json` as decoded strings (keys included; JSON documents inside strings up to 3 levels),
   `.jsonl` line by line, zip archives (workbooks) member by member with XML entities resolved, other files raw. An
   escaped quote, `\uXXXX` or `&amp;` would hide a raw match. Raw JSON text is not also hashed (cost).
4. A symlink in the run root is refused (a linked file or folder would go unread).
5. A hit never releases on its own. The owner's recovery only allows a rescan. Release semantics went to the registrar
   (PR-C31-3 §1).
6. The scan is per chain: each chain's first unseal scans the whole root (so twice per pilot). Cost went to the
   registrar (PR-C31-3 §3).

## Tests (dl, `/root/continual-alf-prep-20260928/env/bin/python -B -m pytest -q -p no:cacheprovider`)

- Own: `tests/test_execskill_canaries.py` + `tests/test_execskill_evaluation.py`: **26 passed** (6.3 s), shared tree.
- Directly affected: `tests/test_execskill_runcli.py`, `tests/test_execskill_cli.py`,
  `tests/test_execskill_readout.py`: **49 passed** (36.3 s), shared tree.
- `tests/test_execskill_e2e.py`: on the shared tree its fixture now errors at the unseal ("No registered test canaries
  in the run root"; seen on a copy, 1 error in 220.7 s) until ticket PR-C31-2 is applied. On a throwaway copy with that
  patch: **11 passed** (314.8 s; earlier recorded runs 321-330 s). With the optional scan assertion: 1 passed (194.4 s).
- What the canary tests cover: refused without the test-read consent (missing, `test_evaluation` false, an extra key;
  no panel opened); made once from three sets and merged after S0's (25; the second call opens nothing; another run
  refused; no text in the file; nothing printed); broken records refused; `run_unit_spec` makes the record before
  `evaluate` and passes the merged 25 (a completed unit opens nothing); the root scan's reading rules (escaped JSON,
  nested JSON, JSONL, non-ASCII log with bad bytes, XML-escaped workbook member, near miss, binary; symlink refused);
  a canary planted in a unit file, the research store and a generated workbook pauses the unseal, the next unseal
  awaits the owner, the owner's recovery rescans (still a hit), and after removal the unseal passes; a clean root
  passes and every file is read; no unseal before the read record exists.
- Mutations (throwaway copies): unseal without the scan, i.e. `scan = None` -> the planted-canary test fails 3 of 3
  (5 of the 10 canary tests fail); `make_read_canaries` without the consent check -> 2 fail; `run_unit_spec` without
  making the record -> 1 fails. The harness's evaluation.py sites 10 and 19 still occur once and still fail their
  named tests. Proposed harness entry 31: PR-C31-2.
- Not run: the whole suite, the mutation harness itself, `tests/test_execskill_smoke_rehearsal.py` (integrator).

## Cost of the root scan (measured, dl, one process, machine shared)

- A synthetic 25.5 MB tree (1440 files; 60 contexts of about 27 KB each, repeated 12 times) with 25 canaries of 25
  lengths: 105 s, 0 hits.
- Microbenchmark: about 1.5 M sha256 windows per second. A C-level `map` pipeline was not faster (1.34 M/s), so pure
  Python offers no constant-factor gain.
- The cost is (distinct text) x (distinct canary lengths). For comparison, v3's run root `/data/coevo5-20261017-run`
  is 1.5 GB in 143K files (only `du` and `find` were run on it). PR-C31-3 §3 lists the options.

## What is not done

- The e2e fixture patch and mutation entry (PR-C31-2), the CLI changes (PR-C31-1), the registrar's four points
  (PR-C31-3).
- Not decoded by the root scan: base64-embedded payloads inside JSON (e.g. a workbook stored as base64 text), gzip
  or other non-zip archives. A canary inside one would be missed.
- No real panel was opened (zero test-pool reads). The field names come from the frozen loaders' public fields
  (`continual_eval/datasets.py:31-34`). Whether real train and test items share verbatim canary texts is unknown
  (PR-C31-3 §1).
