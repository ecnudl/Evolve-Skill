# C6b progress (resume file)

Started 2026-10-22. Row: A3-1, constants (A10-1/C1-1/A9-3), C5-2, C5-4, C3-2 item 1, C5-5.

- [x] 1 A3-1 notes (stems + verbatim exemption via notes.Screened), LEXICON_MATCH/SUFFIXES/VERBATIM; hash pinned in
      tests/test_execskill_notes.py (protocol may not carry a LEXICON*SHA256: test_execskill_integration_b1.py:301)
- [x] 2 constants into protocol.py + twin test (test_execskill_protocol.py)
- [x] 3 C5-2 precheck names (execskill-sbx-[tag-]uuid) + sandbox.cleanup retries; solver passes worker.tag
- [x] 4 C5-4 shell record "sandbox" (solver.solve re-seals after close); cell record "sandbox" (cells._sandbox)
- [x] 5 C3-2 item 1: exclusion.persisted/apply_exclusion(supply, root) -> sealed searchqa-kept; supply.slices(kept=)
- [x] 6 C5-5 rounds.balance removed (+ tests)
- [x] whole suite once: 6 failed, 956 passed in 555.46s (3 = C7a fixtures mid-edit, pass on re-run; 3 = ticket C6b-4)
- [x] own files + mutation suite after the suite: 202 passed in 53.12s
- [x] tickets C6b-1 (import switches, MDE wiring, prompt hashes), C6b-2 (notes.screen call sites, fake tag=),
      C6b-3 (SearchQA tail wiring), C6b-4 (fixture word "answered" -> "solved" in test_execskill_integration_b4.py:61)
- [x] throwaway-copy check of C6b-4 on dl (/tmp/c6b-check, removed): b4 + step + e2e + describer with only
      "answered" -> "solved": 23 passed in 402.89s (0:06:42)
- [x] note notes/C6b.md written; handback sent. DONE.
