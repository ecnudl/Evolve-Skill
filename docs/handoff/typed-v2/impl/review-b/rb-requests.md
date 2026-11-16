# Review rb-requests: requests sent to models (typed-v2 Steps 1 to 5, `git diff 8375ecb`)

Read-only reviewer, 2026-11-12. No tree file edited apart from this note; scratch under `/tmp/typed2-neutral/rb-requests/`.

## Method

1. Read the whole request path in `git diff 8375ecb -- skillopt scripts` (mount, writers, cards, replies, engineer
   prompt hooks, chain builder / gate arms / member units, reads, units, smoke).
2. Recomputed the 55-case mount golden table of `tests/test_typed_mount_identity.py` with the 8375ecb `T/mount.py`
   (loaded from `git show` as a module of the current typed package): old == new (default base) == new with
   `base_card='format'` == pinned, 55 of 55 (`check_mount_golden.py`). B cases: the 8375ecb C0 payload with arm 'B'.
3. Ran the fake chain (smoke fakes, REAL mount / writers / reads, exact axis embedder; `drive_run.py`, a copy of the
   helpers of `tests/test_typed2_base.py` / `test_typed2_shared.py`) on this tree and on a `git archive` copy of
   cdf85b6 (its counts reproduce `GOLDEN_RUNS_CDF85B6`: 235/191 and 264/196), and compared the DISTINCT request
   contents (purpose, sha256(system NUL user)) per purpose (`compare_runs.py`):
   - one bench per type (OfficeQA opens its own type), base 'format': solver, selection, describer, first call,
     card writer and engineer requests are the same set as cdf85b6's (smoke: 97 distinct, digest
     `323f1e33...9569`; default limits: 103 distinct excluding `s1/card-r2`, digest `856d435d...7b91`). The one
     difference is `s1/card-r2`'s `result` (`mean_gain_points` -66.66666666666667 vs ...66), DESIGN 4.2 (2).
   - OfficeQA in SearchQA's type (D16), base 'format': the smoke scenario differs ONLY in the step-2 card writer
     and engineer requests, each by the single key `members` (system texts equal, home part equal); every solver,
     selection and describer request content is cdf85b6's. In the default scenario the step-2 member gate rejects
     both rounds (`member_harm`), so later libraries and requests differ as a consequence of D16 (b).
   - 'historical' vs 'format' on this tree: differences only in learned-side solver system texts and S<k> reads of
     the four non-ZebraLogic benches, and the base block of card writer / engineer proposal requests; ZebraLogic,
     C0 / C reads, selection and describer requests equal.
4. Ran `tests/test_typed2_base.py tests/test_typed2_shared.py tests/test_typed_mount_identity.py
   tests/test_typed_writers.py tests/test_typed_cards.py`: 193 passed (Python 3.13).

## Findings

F1 (must-fix, test evidence; no data affected today). `tests/test_typed2_base.py::
test_format_base_sends_every_request_and_cell_of_cdf85b6` and its module docstring claim that under 'format' every
request is cdf85b6's, but the test compares with `GOLDEN_RUNS`, which 5w and then 5x re-pinned to the output of the
tree under test (`GOLDEN_RUNS_CDF85B6` and `GOLDEN_RUNS_5W` are unused history). `GOLDEN_SINGLE` of
`tests/test_typed2_shared.py` is pinned to the 5w tree, which was never committed and cannot be reproduced. After
the D5 wiring no test anchors the chain-level requests (solver, selection, describer, writers) under 'format' to
cdf85b6 / 8375ecb: an edit that changes one of them would be absorbed by the next re-pin, exactly as the two re-pins
were done. The contents ARE identical today (method 3). Fix: compare distinct request contents, which R repeats do
not change, with the old code: run the cdf85b6 typed package (git blobs, as `test_typed_writers.py` does for the
typed-v1 writer) on the one-bench scenarios, or pin the cdf85b6 digests above, and assert equality (excluding only
the round-2 card request's `result`).

F2 (minor, affects the engineer request). `W.program_payload` fits member trajectories with `_message_bytes(payload)`
measured BEFORE `fit` adds the key `trajectories_omitted` (27 bytes), so when the member loop ends within 27 bytes
of `ROLE_INPUT_BYTES`, `fit` drops a trajectory of the CURRENT bench although member trajectories remain. Reproduced
(`fitedge.py`, fixtures HOME / MEMBER of `tests/test_typed2_shared.py`, bound = size after one member drop + 5):
home trajectories 2 -> 1, member trajectories 1 left. D16 (a) and the docstring promise the current bench's part is
unchanged whenever the members can make room. Fix: measure `{**payload, 'trajectories_omitted': 0}` in the loop (or
set the key before it).

## Checked, no defect

- mount / mount_identity split: records and selection requests byte-identical to 8375ecb for every arm (55 cases);
  B under 'format' = C0 except the recorded arm; `solve` does not read the arm; C0 / C ignore `base_card`.
- First-attempt card request and every content-violation retry: `tests/test_typed_writers.py` compares with the
  typed-v1 writer blob 646346d (= 8375ecb) executed live, not with the new code; `RETRY_FRAME` / `RETRY_SHORT` equal
  the bound texts; `cards.content_violation` matches the bound function line for line (tuple corpora already
  handled there).
- Proposal user payload under 'format' without members: unchanged keys and construction (only the system text,
  fix request and format retry change, as DESIGN 3.2 / 3.3 say); `_json` sorts keys, so key insertion order is
  irrelevant.
- D16 (d): with an empty member list no `members` key, member unit, `shared_with` field or screen change; a member
  block holds learn-slice examples only (`member_examples` filters label 'F' learn cells; gate repeats are 'F#r').
- D17: `base_card_block` is None under 'format' and on ZebraLogic; fix and format-retry requests carry no block;
  reads take the manifest's base in the services form. Noted, not a finding: under 'historical' the card screen's
  public text adds C (`_screen_public`, 5b Choice 7), which can only remove content findings for text of C.
- Cell tags: only gate labels `<arm>#<r>` (and B#r for the noise) are new; read, learn, smoke and
  `card-r<j>-learn` labels unchanged; unit names unchanged apart from member units (D16) and slot-numbered program
  units (DESIGN 3.2).
- Widths, lock, container scope: enter no request.
