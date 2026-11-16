# rp-core-review: review of the pure core of T/readplan.py

Reviewer: rp-core-review, 2026-11-12. I was read-only on the worktree; this file is my only write there. Probes and
mutation runs live under /tmp/typed2-rpcore/probes and /tmp/typed2-rpcore/mut. `git status` still shows only
RPCORE-REPORT.md, readplan.py and test_typed_readplan_core.py, plus this file.

Tests: `44 passed` on Python 3.13.12, and also on 3.10.20.

Checked against spec/read-plan.md. I found no defect in:
- R8 to R15, R28 to R31, R91, RP3 and RP8: the identity and list hashes match R9 and R28 exactly. Type id, source,
  unknown reason, card skill and offered ids are not hashed. The first-request rule is per event. Fallback is its
  own class, the representative is the latest event, and classes are idempotent. Both base values and ZebraLogic
  work.
- R32 and 3.2 to 3.4: all keys are present.
- R39 and R47 core.
- R78, R80 and R81.
- Concurrency of `write_once`: 30 trials of 8 processes, half writing A and half writing B. Exactly the 4 writers of
  the stored value succeed, the other 4 get `WriteOnceMismatch`, and no `.part` file is left.
- Canonical bytes: dict order, floats and Unicode give equal bytes; there is no dependence on the hash seed.
- No open string leaks an id.

Every finding below is minor.

## F1 (minor). A wrong-arm identity is accepted, so two different request sets can alias

- **Where.** `item_components` (about line 484) and `event_entry`.
- **Problem.** The capture-mounted record carries `mounted['arm']`, but the core drops it. Nothing ties an event's
  records to `arm_of(event)`.
- **Reproduction.** Probe `/tmp/typed2-rpcore/probes/p5_arm.py` computes C0's records through the arm F path, under
  base `historical`.
  - officeqa becomes the single class `{C0, C, S1..S5} > S5`; counts are fresh 5, alias 30.
  - The plan verifies.
  - The replay reproduces it, because it uses the same pass code.
  - R41 checks only S5's cells, and they match.
  - Result: the no-skill row C0 is shown as "same requests as S5". This is the false dash that K-A warns about.
- **Fix.** Give `item_components` a required `arm=` and raise `identity_disagreement` unless
  `mounted.get('arm') == arm`. The integrator passes `arm_of(event)`. The 3.3 schema does not change.
- **Optional.** Also accept the (step, library_file_sha256, typemap_file_sha256) that each entry was computed
  under, and require it to equal `frozen[event]` in `build_plan`. An off-by-one frozen state would otherwise go
  unseen in the same way.

## F2 (minor). `record_from_bytes` can raise a raw exception instead of `ReadPlanError`

- **Where.** About lines 329 to 340. `canonical_bytes(value)` runs outside the `try`.
- **What escapes** (probe `/tmp/typed2-rpcore/probes/p1_bytes.py`):

  | Bytes | Exception raised |
  |---|---|
  | `{"a": 1e999}` | ValueError (out-of-range float) |
  | `{"a": "\ud800"}` | UnicodeEncodeError |
  | 200,000 nested brackets | RecursionError |

  The `verify_*` functions also do not catch RecursionError.
- **Affected.** `plan_from_bytes`, `sealed_from_bytes` and `alias_from_bytes`, and the `load_*` functions.
- **Failure scenario.** An alias record is read without a bound file hash. Such a corrupted record reaches R44 or
  R46 as `exception:ValueError` instead of `read_alias_invalid`. The R44 (b) archive-and-re-settle recovery then
  never applies, and every resume fails again.
- **Fix.**
  - Move the canonical comparison inside the `try`.
  - Catch `(UnicodeError, ValueError, RecursionError)` and map it to `ReadPlanError(code)`.
  - Add RecursionError to the `except` tuples of the `verify_*` functions.

## F3 (minor). Spec-mandated checks with no test: 7 single-rule mutations survive the full suite

Method: a scratch pytest plugin (`/tmp/typed2-rpcore/mut/mutplug*.py`) replaces one rule at a time. All 44 tests
still pass for each of these:

- M1: `post_read_check` ignores the first request. This is R41/RP3, the direct proof for members without programs.
  `test_post_read_check_counts` only uses items with programs, so the expected first request is always None.
- M4: no agreement check on offered ids in `item_components` (R16).
- M6: `_check_entry` ignores the stored view hashes.
- M7: `_check_identities` ignores `inputs` (the `inputs_sha256`, id, chain and bench binding).
- M10: a stored ok entry that breaks RP3 is accepted.
- M19: ALFWorld stored views are not bound to `view_sha256`.
- M20: frozen steps are not checked.

Probe `/tmp/typed2-rpcore/probes/p6_checks.py` shows all seven checks do work today, so these are test gaps only.

Fix: add one test per item. Also add T8 (a): two items swap their identities, so the lists differ.

## F4 (minor). `ReadPlanError` with a detail cannot be pickled or deep-copied

- **Problem.** `super().__init__(code + ': ' + detail)` makes `args` the composite text. Reconstructing the error
  raises `ValueError('Unregistered read-plan code')`. Probe: `/tmp/typed2-rpcore/probes/p3_pickle.py`.
- **Failure scenario.** Most raised errors carry a detail, for example `identity_exception: mount record`. If the
  integration ever runs the per-bench identity loop in a process pool, which is plausible given R18's machine-time
  cost, every per-item identity error breaks the pool instead of becoming a fallback.
- **Fix.** Use `super().__init__(code, detail)` with a `__str__`, or define `__reduce__`.
