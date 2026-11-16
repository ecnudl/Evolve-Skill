# Review rb-resume (lens: interruption, resume, paid calls) of `git diff 8375ecb`

Read-only reviewer notes, 2026-11-12. Fakes only; nothing paid, no network. Scratch probes under
`/tmp/typed2-neutral/rb-resume/` (`killsim.py`, `probe2.py`, `probe_sigint.py`).

## What was checked and holds

- Simulated SIGKILL (directory snapshot taken inside the in-flight call, i.e. ledger reservation and calls file already
  persisted; process aborted; snapshot restored; owner recovery; resume), learning width 1, on 11 points:
  `s1/noise` B#3, `s1/card-r1` cand_card#2, the card writer, a card describer, the program writer, an `outcomes-card`
  learn cell, and the D16 units `s2/member-searchqa-base`, `s2/card-r1-member-searchqa`,
  `s2/program-2-member-searchqa`, `s2/member-searchqa-outcomes-card`, the `s2/program-2` describer.
  In every case: the run completes; exactly the interrupted call is sent twice, every other (unit, tag, purpose) once;
  every `plan.json` is byte-identical; the decision's `reruns` counts the interrupted gate cell (candidate 1; a
  program member check that uses the card's member runs as baseline inherits baseline 1).
- Rerun entries keyed (unit, tag): the same cell tag `cand_card#2` of `searchqa-g1` occurs in `s1/card-r1` and in
  `s2/card-r1-member-searchqa`; neither re-draws the other.
- Arm registration order on resume (typing `register_stored`, card rounds re-running `card_member_checks`, stored
  program decisions re-registering gate + member arms) reproduces the original `compared` lists.
- Home-rejected candidates run no member cell after a resume (the home rule is recomputed zero-call from done cells).
- Programs unit: `_keep_earlier_sends` keeps the interrupted send (receipt null) in the calls file; per attempt <= 5.
- Baseline: `tests/test_typed2_gate.py tests/test_typed2_shared.py tests/test_typed_chain.py tests/test_typed_units.py`
  76 passed.

## Findings (all minor)

1. SIGINT on the main thread during a unit's first (serial) cell: the CallRecorder settles the call in `finally`
   (no pending entry), the cell has no record, so the resume sends it again (R+1 requests for that item and label)
   while the decision / noise record says `reruns` 0. Probe: `probe_sigint.py` (s1/card-r1 and s1/noise).
2. Card writer and describer: a resumed unit builds a new recorder on the same calls file and overwrites it; the
   interrupted send (and any completed earlier attempt of the round / of the describer after
   `describer_unavailable`) disappears from the unit's calls file (the ledger keeps only `recovered` / by_unit
   counts). Pre-existing from typed-v1; DESIGN 3.3 fixes this for `s<k>/programs` only.
3. Unlocked mutation of `ledger.rerun_cells` (`mark_infrastructure_reruns` add, `difference_update` in `_read` /
   `cells` finally) while another read-unit thread iterates the set in `run_unit` (new in typed-v2: the set is now
   iterated) -> `RuntimeError: Set changed size during iteration` -> spurious pause of a resumed read event.
4. `run_typed.py smoke` has no `--resume`; a paused real smoke cannot be resumed and must be redone on a new root.

## Missing tests

- Chain-level pending-ledger-entry (SIGKILL) resume inside a gate unit and inside a D16 member arm, asserting R+1 sends
  and `reruns` 1 (only the units-level test exists).
- KeyboardInterrupt in the main thread during a gate unit's first cell (would expose finding 1).
- Calls-file content after an interrupted card writer / describer.
- Concurrent resume of several read units holding infrastructure reruns.
