# Brief P3r: typed-v3 read rows (no C0 anchor, a fresh five-panel read after every step)

You implement ONE piece of the next version of a research codebase: the READ side of piece P3 (section C of
`<scratch>/typed-v3-design/build/brief-P3-gate-and-reads.md`). Work in the git
worktree `<repo-root>` (branch `research/typed-skills-v3-reads`, at commit
bd421da = P1 + P2a + P3a merged) and ONLY there: other builders change other trees at the same time (the main tree:
P1's review fixes in chain.py's program code; another worktree: the item stage in chain.py, prepare.py and
run_typed.py). Your branch will be merged with theirs, so keep changes to the read modules and to the smallest
needed lines elsewhere. Do not commit, do not push. No network, no paid model calls: tests use the in-memory fakes of
the existing suite. TMPDIR must be a directory whose name has no word like "test" (use /tmp/typed3-reads-neutral).

## Read first

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md` T2 (reads, owner-approved: schedule `interleaved`, read plan `full`,
   rows C and S1..S5, NO C0; differences S<k> - C and S<k> - S<k-1>, own-run, same items) and the P3 brief's section C.
2. `skillopt/execskill/typed/readplan.py` (as far as the `'full'` plan and the `'interleaved'` schedule need it),
   `reads.py`, `readout.py` (how rows C0, C, S1..S5 are tabulated, the contrasts, the 5x5 block, the
   continual-learning metrics), `chain.py` (the read events, the schedule handling, `read_anchors` / `read_step` /
   `reads`), `prepare.py` (sealed options and their readers), `scripts/run_typed.py`, and the consent validation the
   reads use (find it: `reads.consent` or similar). Also the tests of readplan, reads, readout, schedule and chain.

## What to build

1. A sealed manifest option `read_anchors`: `('C0', 'C')` (default: today's behaviour and bytes) or `('C',)`. Under
   `('C',)` the event C0 is never read, never planned, never required for completion, and the readout tabulates rows
   C, S1..S5 with contrasts S<k> - C and S<k> - S<k-1> only (and the continual-learning metrics that need no C0;
   say which ones are dropped). Every place that reads a C0 mirror must tolerate its absence under this option and
   only under it. Prepare seals it (a CLI flag in the style of the existing ones, e.g. `--read-anchors C` vs the
   default); a run reads it back only from the manifest.
2. The combination schedule `'interleaved'` + read plan `'full'` must run and resume in this tree: after step k the
   frozen state S<k> is read fresh on all five test panels before step k+1 learns. It was typed-v1's order; typed-v2
   used `'learn_first'` + `'economy'`, and later changes may have broken it. Exercise it with the fakes end to end
   (both chains, five steps, `('C',)`), find what is broken, fix it, with tests.
3. The consent record of the real run will list the arms `C`, `S1`..`S5`; make sure the consent check accepts exactly
   that list under `('C',)` and still refuses a consent that does not cover the planned events (do not weaken it).

## Rules that are not negotiable

- Default options: every existing test passes unchanged; records byte-identical.
- Write-once, resume-safe: a kill in the middle of a read event and a resume give the same final records as an
  uninterrupted run, with no repeated paid call whose record exists.
- The test panels are read only through the existing consent-gated read code; nothing else may open them.
- No path with a forbidden word inside run roots beyond what the existing read code already uses under its own guard;
  deterministic records; do not weaken any `require` or guard.

## Tests (fakes only; expected values computed independently)

At least: the default is unchanged; `read_anchors = ('C',)` with `'interleaved'` + `'full'` completes both chains
with read events C, S1..S5 (none for C0), each S<k> read after step k and before step k+1's first learning unit;
the readout holds no C0 row and gives S<k> - C and S<k> - S<k-1>; a kill in the middle of a read event (and between a
read event and the next step) resumes to the same records; the consent with arms C, S1..S5 is accepted and one
missing an arm is refused.

## Report back

Plain text: (a) files changed and created; (b) exact test commands with counts (new tests and the whole typed
selection `tests/test_typed*.py`); (c) existing tests edited and why; (d) what you could not do or did differently,
and why; (e) open risks; (f) the prepare flags for `('C',)`, `'interleaved'` and `'full'`. Never report a part as done
that has failing or missing tests. Keep a short progress note at
`<claude-job-tmp>/build-P3r-progress.md` and continue from it if it exists.
