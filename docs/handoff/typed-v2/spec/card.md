# typed-v2 spec: CARD LENGTH (decision D2, facts F1, F6)

2026-11-12, design-team member "card". Documents only; no code was edited and no test was run. Paths are relative
to this tree. `T/` = `skillopt/execskill/typed/`, `X/` = `skillopt/execskill/`. `[V]` = I opened and read the cited
lines, `[V grep]` = verified by a grep over the named files only, `[I]` = inferred.

## 0. Blockers

No blockers. D2 can be met with edits in `T/`, `tests/` and `docs/` only, and no later consumer rejects or
truncates a card of 4,500 content characters (table in 1.3). The first-attempt request stays byte-identical to
typed-v1 for equal inputs (3.2). A card above 3,000 characters cannot become a v2.25 card `Procedure`
(`X/package.py:196` [V]), but the typed run never builds one (section 6, item 5).

## 1. Behaviour

### 1.1 Screen and count

1. The reply becomes the card text through the bound `texts.instruction_text`, as today: stripped content plus
   exactly one `"\n"` (`skillopt/coevo5/texts.py` `instruction_text` [V]). The stored text keeps that newline.
2. Content characters = `len(text.strip())` (Python code points). For every `instruction_text` output this equals
   `len(text) - 1`. No text (no reply, blank reply) counts 0.
3. Typed length verdict: `'length'` iff there is no text, or content characters > 4,500, or bullet lines > 12.
   A bullet line is a line of `text.splitlines()` matching the regex of `X/v225_cards.py:167` [V]. Hence content
   3,000 passes (typed-v1 rejected it as 3,001: `len(text) > MAX_CARD_CHARS`, `X/v225_cards.py:166` [V]); 3,001 and
   4,500 pass; 4,501 is `length`; 12 bullets pass; 13 are `length`. Every typed-v1 card text of F6 (content 2,349
   to 3,499) is below 4,500.
4. A text that passes 3 goes, as stored, through the four content screens in the v2.25 order (`format_markers`,
   `item_identity`, `references`, `copied_examples`): a verbatim copy of `X/v225_cards.py:169-201` [V] that calls
   the bound helpers. The first failing key is the violation. Nothing about content is relaxed: a 3,400-character
   card containing `<answer>` or a practice id is rejected.
5. The frozen `v225_cards.card_violation` leaves the run path. Its only typed call is `T/writers.py:271-272` [V],
   whose only caller is `T/writers.py:288` [V grep over `T/`, `scripts/`, `tests/`].
6. The writer is told 3,000 characters and 12 bullets exactly as in typed-v1: system prompts
   `CARD_WRITE_SYSTEM` / `CARD_REVISE_SYSTEM` (`X/v225_cards.py:24-49` [V]) and `card_rules.max_chars = 3000`,
   `max_bullets = 12` (`T/writers.py:260` [V]). No text sent to the writer ever names 4,500.
7. Attempts stay 2 (`CARD_ATTEMPTS`, `T/writers.py:34` [V], out of scope). The second request is the first user
   message + `"\n\n"` + the retry text, as today (`T/writers.py:284-285` [V]).

### 1.2 Retry text (typed-level constants, exact wording)

```python
RETRY_FRAME = ('Your reply could not be used as the card: {reason}. Reply again with only the card text, '
               'following every rule of the system message.')
REASON_TOO_LONG = 'it has {chars} characters, but a card may have at most {target}; cut at least {cut} characters'
REASON_TOO_MANY_BULLETS = ('it has {bullets} bullet points, but a card may have at most {max_bullets}; '
                           'merge or remove at least {extra}')
REASON_NO_TEXT = ('it was empty or was cut off before its end, so no card text was received; keep the card '
                  'within {target} characters and {max_bullets} bullet points')
REASON_JOIN = '; in addition, '
RETRY_SHORT = {'length': 'it is empty, longer than 3,000 characters or has more than 12 bullet points',
               'format_markers': 'it contains an answer, action or calc tag or a code fence',
               'item_identity': 'it contains a task identifier or a file path',
               'references': 'it contains a reference answer or a value from one',
               'copied_examples': 'it copies text from an example'}
```

8. Values: `chars` = content characters, `target` = 3,000, `cut` = `chars - 3,000` (at least 1,501 whenever the
   sentence fires), written with thousands separators (`format(n, ',')`) to match "3,000" in the system prompt.
   `bullets` = counted bullet lines, `max_bullets` = 12, `extra` = `bullets - 12`, plain integers.
9. Reason chosen: no text -> `REASON_NO_TEXT`; too long only -> `REASON_TOO_LONG`; too many bullets only ->
   `REASON_TOO_MANY_BULLETS`; both -> the two joined by `REASON_JOIN`, length first; a content key ->
   `RETRY_SHORT[key]`. Example (213 characters, measured): `Your reply could not be used as the card: it has 4,501
   characters, but a card may have at most 3,000; cut at least 1,501 characters. Reply again with only the card
   text, following every rule of the system message.`
10. `RETRY_FRAME` and `RETRY_SHORT` are typed copies equal to the bound `CARD_RETRY` / `RETRY_REASONS`
    (`X/v225_cards.py:50-58` [V]); a test asserts equality. So a retry after a content violation is byte-identical
    to typed-v1; only the `length` retry is new text.
11. Room rule. `_fit_examples` (`T/writers.py:241-251` [V]) is NOT edited: it reserves 2 + 199 characters for the
    retry (199 = the longest v2.25 retry; measured). The detailed sentences are longer (measured: 207 to 256 for
    one cause, 311 or more for both). The retry uses the detailed sentence when `len(message) + 2 + len(sentence)
    <= v225_cards.CARD_WRITER_INPUT_CHARS` (120,000), else `RETRY_FRAME.format(reason=RETRY_SHORT['length'])`,
    which always fits. So the ceiling asserted at `T/writers.py:249` holds for both attempts, and the fitting of
    examples (hence the first request) is untouched.

### 1.3 Every later consumer of a 4,500-content-character card (stored length 4,501)

| Consumer | Evidence | Verdict |
|---|---|---|
| `T/library.py:74` `make_skill`, `:161-180` `save` / `load` | card rule is `str` and non-blank; record hash and version only [V] | accepts |
| `T/library.py:189-195` `description_request`, `T/writers.py:543-568` `describe` | whole card in `skill_content`; only the examples (6,000) and the reply (`library.py:198-203`) are capped [V] | accepts |
| `T/writers.py:254-266` `card_request` (revise round) | only `isinstance(current_text, str)`; `current_card` / `previous_card` copied whole; `_fit_examples` drops examples until the request fits 120,000 [V] | accepts; the two card fields can be about 3,000 characters longer than in typed-v1, so an example may be dropped earlier |
| `T/chain.py:752-789` | text used as is; `make_skill('card', ..., {'text': text}, ...)` [V] | accepts |
| `T/mount.py:66-69` `system_card`, `:241-254` `_check_candidate`, `:209-219`, `:347-368` `solve`, `:433-440` `_stored_mount` | type and non-blank checks only; the text is stored per cell [V] | accepts (disk only) |
| bound `X/solver.py:641-660` `solve` -> `X/v225_cards.py:128-133` `compose` -> `X/package.py:322-326` `card_for` | typed packages hold programs only (`T/mount.py:92-98`, `:354` [V]); `card_for` is None, `compose` returns the base card unchanged [V] | accepts |
| bound `X/solver.py:147-166` `_system`, `:819-820` ALFWorld | plain concatenation, no limit [V] | accepts |
| bound `X/package.py:193-200` | the 3,000 limit applies only to a `Procedure` with the v2.25 card policy; `T/` and `scripts/run_typed.py` contain no `make_card` / `card_source` [V grep] | not on the path |
| frozen `card_violation` | other callers are `X/v225_writer.py`, `X/v225_smoke.py` only [V grep]; `T/` imports neither `v225_smoke` nor `v225_phase` / `v225_read` [V grep] | not on the path |
| `T/units.py:143-164` `Ledger.before_send`, `:201-240` `CallRecorder` | reservation from the actual request bytes (`skillopt/coevo5/ledger.py:26-27` [V]); no input ceiling [V] | accepts, costs tokens |
| role limit `X/profiles.py:1632`, `X/v225_limits.py:12` (120,000 input characters) | no `input_chars` in `T/` or `scripts/run_typed.py` [V grep]; only `_fit_examples` reads the ceiling | not enforced on a card |
| client and backends | no request-size check found in `X/client.py`, `scripts/weak_solver_probe.py`, `skillopt/continual_eval/backends.py`, `X/manifest.py` [V grep, not a full read] | accepts [I] |
| truncation flag `X/solver.py:497-501` | completion tokens only [V] | unaffected |
| `T/smoke.py:33-35`, `:307`; `T/readout.py:58-59`, `T/reads.py`, `T/prepare.py`, `T/tasktypes.py`, `T/gates.py` | short fake card with the real writers; text keys dropped; no length check; nothing reads `chars` or `attempts` [V grep] | accepts |

## 2. Change list

| # | File, function / lines today | Change |
|---|---|---|
| C1 | `T/cards.py` NEW (name free in `T/` [V ls]; typed-only, so loaded from this tree under F1) | constants and functions below |
| C2 | `T/writers.py:30` `from . import library, units` [V] | becomes `from . import cards, library, units` |
| C3 | `T/writers.py:269-272` `screen_card` [V] | body becomes `return cards.card_screen(text, bench=..., ...)['violation']`; name, signature, return type unchanged |
| C4 | `T/writers.py:275-295` `write_card` [V]; docstrings `:1-3`, `:276-277` | one `cards.card_screen` call per attempt (replaces `:288-290`); retry text (`:284-285`) = `cards.retry_text(seen, room=v225_cards.CARD_WRITER_INPUT_CHARS - len(message) - 2)` instead of `v225_cards.CARD_RETRY`; attempt record (`:291-292`) takes `chars` and the new `bullets` from the screen result; result gains `'card_limits': cards.LIMITS_RECORD`; signature unchanged |
| C5 | `T/chain.py:784` `'chars': len(text)` [V]; `:54` `from . import gates, library as library_, tasktypes, units` [V] | `'chars': cards.content_chars(text)`; add `cards` to the import at `:54` |
| C6 | `tests/test_typed_cards.py` NEW | section 4 |
| C7 | `tests/test_typed_writers.py:136-151`, `:154-173`, `:176-182`; `tests/test_typed_chain.py:102` | section 4 |
| C8 | typed-v2 `DESIGN.md` (to be written; typed-v1 `DESIGN.md:278` [V] is frozen, F3) | `write_card` contract with the new attempt shape; definition of `chars`; "told 3,000, enforced 4,500" |

Not edited: `T/writers.py:241-251` `_fit_examples`, `:254-266` `card_request`, `:34` `CARD_ATTEMPTS`;
`T/__init__.py`, `T/library.py`, `T/mount.py`, `T/smoke.py`, `T/readout.py`, `T/reads.py`; everything under `X/`
outside `T/` and all of `skillopt/coevo5/` (F1, D1).

`T/cards.py` (about 90 lines):

```python
from skillopt.coevo5 import leakage                      # bound (snapshot)
from skillopt.continual_eval.core import require         # bound
from skillopt.execskill import v225_cards                # bound; read and called, never edited

CARD_TOLD_CHARS, CARD_HARD_CHARS, CARD_MAX_BULLETS = 3000, 4500, 12
require(CARD_TOLD_CHARS == v225_cards.MAX_CARD_CHARS and CARD_MAX_BULLETS == v225_cards.MAX_CARD_BULLETS,
        'The told card limits are the limits the bound v2.25 prompts state')
BULLET = re.compile(r'^\s*(?:[-*+•]|\d+[.)])\s+')        # copied from X/v225_cards.py:167
COPIED_SOURCE_SHA256 = '<sha256 of inspect.getsource(v225_cards.card_violation); fixed at implementation>'
LIMITS_RECORD = {'told_chars': 3000, 'hard_chars': 4500, 'max_bullets': 12,
                 'count': 'content characters without the final newline'}
# plus the six retry constants of section 1.2

def content_chars(text) -> int      # len(text.strip()) for a str, else 0
def bullet_count(text) -> int       # lines of text.splitlines() matching BULLET; 0 when not a str
def content_violation(text, *, bench, corpus, shown, task_card, format_block, practice_ids) -> str | None
    # verbatim copy of X/v225_cards.py:169-201; PATH_LIKE and _reference_values are read from v225_cards,
    # absent_findings is imported inside the function from skillopt.execskill.engineer (as the original, :178)
def card_screen(text, *, bench, corpus, shown, task_card, format_block, practice_ids) -> dict
    # {'violation': None | 'length' | a content key, 'chars': int, 'bullets': int}; length rule first (1.1 item 3)
def retry_text(seen, *, room) -> str    # seen = card_screen's dict; 1.2 items 8, 9 and 11
def pins() -> dict                  # sha256 per retry constant, LIMITS_RECORD, COPIED_SOURCE_SHA256
```

The helpers the copy calls exist in the bound code, because the bound function itself uses them at
`X/v225_cards.py:171-200` [V]: `PATH_LIKE` (`:161`), `_reference_values` (`:140-157`), the `leakage` functions
(`skillopt/coevo5/leakage.py:93-209`), `engineer.absent_findings(text, corpus, public)` (`X/engineer.py:1707`).

## 3. Records and identity

3.1 Changed or new fields. Attempt record in typed-v2: `{'request_sha256', 'violation', 'chars', 'bullets',
'no_reply'}`; typed-v1 has the same keys without `bullets` (`T/writers.py:291-292` [V]).

| Record | Field | typed-v1 | typed-v2 |
|---|---|---|---|
| `s<k>/card-r<j>/writer.json` and `decisions.json` `cards[j].attempts[i]` | `chars` | `len(text)` with the newline, 0 without text (`T/writers.py:291` [V]) | content characters (0 without text) |
| same | `bullets` | absent | counted bullet lines (0 without text) |
| same | `violation` | five v2.25 keys or null | same five keys or null; `length` now means no text, over 4,500, or over 12 bullets (cause recomputable from `chars`, `bullets`, `no_reply`) |
| `writer.json` | `card_limits` | absent | `cards.LIMITS_RECORD` |
| `decisions.json` `cards[j]` | `chars` | `len(text)` with the newline (`T/chain.py:784` [V]) | content characters (`len(text) - 1`) |
| manifest (owned by the version area) | card pins | none: `T/` records no prompt pins today [V grep] | `cards.pins()` |

Unchanged in shape: `text` (with its newline), `text_sha256` (`T/chain.py:784`), library `body.text` and skill
`sha256 = canonical_sha256(body)` (`T/library.py:80` [V]), mount `card_text`, `system_card`, `system_card_sha256`
(`T/mount.py:176` [V]), `previous_card` / `current_card` in the revise request, unit names `s<k>/card-r<j>` and
`-learn`, the reason `writer_screens_failed` (`T/chain.py:778-779` [V]). Readout and ledger records: no field
changes; nothing there reads `chars` [V grep].

3.2 Request texts.

- First attempt, both rounds: byte-identical to typed-v1 for equal inputs. How I know: the system prompts are the
  bound constants; `card_request`, `_fit_examples` and `_json` are not edited, and the reserve still comes from the
  bound v2.25 sentences (201). Inputs can differ for reasons outside this area: `EXAMPLE_TAG` (`T/writers.py:36`),
  and a `current_card` / `previous_card` longer than 3,001 characters, which only typed-v2 can hold.
- Second attempt after a content violation: byte-identical to typed-v1 (1.2 item 10). After `length`: new text
  and a new `request_sha256` (`T/writers.py:57-59` [V]). This is the only request text this area changes.
- Solver, describer, selection requests: no code change; texts differ only where a longer card is mounted.
  Route-B pins (`v225_cards.prompt_pins`, `:221-226` [V]) are untouched; `T/` does not call them [V grep].

## 4. Tests

New, in `tests/test_typed_cards.py`:

| Name | Proves |
|---|---|
| `test_content_chars_and_length_boundaries` | for plain, fenced and padded replies `content_chars(instruction_text(r)) == len(instruction_text(r)) - 1`; content 3,000 / 3,001 / 4,500 pass, 4,501 is `length`; 12 bullets pass, 13 are `length`; `''`, `None`, blank are `length`; `chars` and `bullets` values, with and without the final newline |
| `test_content_screens_match_the_bound_function_on_the_fixed_corpus` | drift guard: for every corpus text with `len(text) <= 3000`, `card_screen(...)['violation'] == v225_cards.card_violation(...)`, and both equal the key written in the corpus |
| `test_copied_source_and_sentences_are_pinned` | `sha256(inspect.getsource(v225_cards.card_violation)) == COPIED_SOURCE_SHA256`; `RETRY_FRAME == CARD_RETRY`; `RETRY_SHORT == RETRY_REASONS`; told limits equal the bound ones; `BULLET.pattern` occurs in the bound source |
| `test_long_cards_still_fail_content_screens` | a 3,400-character card with `<answer>`, with a practice id, with a reference value, with copied example text returns its content key (the 3,001 to 4,500 band is no loophole) |
| `test_retry_text_and_room_rule` | exact strings for 4,501 ("4,501", "3,000", "1,501") and 5,212; 15 bullets ("15", "12", "3"); both causes joined; no text; no retry text contains "4,500" or "4500"; room 199 gives the short sentence, a large room the detailed one; each short sentence is at most 199 characters; the `_fit_examples` reserve is still 201 |
| `test_later_consumers_accept_a_4500_character_card` | `make_skill` + `Library.save/load`; `description_request` holds the whole text; `mount.system_card`; `v225_cards.compose(bench, system_card, typed_package) == system_card`; `solver._system` output contains the whole card; a revise `card_request` with a 4,501-character previous card fits the ceiling |
| `test_card_path_under_bound_machinery_in_a_fresh_interpreter` | below |

Fixed drift corpus (inline constant `DRIFT_CORPUS`, each text also with one final newline): the 14 content cases of
`tests/test_execskill_v225_cards.py:50-56` and the reference cases of `:68-74` [V]; the four content cases of
`tests/test_typed_writers.py:156-159` with that file's examples and corpus [V]; clean cards (one line; exactly 12
bullets; 2,999 content characters; the public workbook names of `:61-63`). The three length cases (`''`, 13
bullets, `'x' * 3001`) are asserted separately: the first two are `length` on both sides, the third is the one
documented difference (bound `length`, typed None).

Fresh interpreter under `bind_machinery` (pattern `tests/test_typed_cli.py:80-105` [V]: `subprocess.run([sys.executable,
'-I', '-c', code])`, `run_typed.bind_machinery(snapshot, TREE)` before any `skillopt` import). The snapshot must be
real machinery, not the two marker files of that test: copy this tree's `skillopt/` without `execskill/typed`
into `tmp_path` (F2: byte-identical to the dl snapshot). The child asserts: `cards.__file__` and `writers.__file__`
are under this tree's `T/`; `cards.v225_cards.__file__`, `texts.__file__`, `leakage.__file__` are under the
snapshot; the drift corpus and the pin test hold there; a scripted `write_card` accepts a 3,400-character clean card
on attempt 1 with `chars == 3400` while the bound `card_violation` says `length` for the same text; a 4,501-character
first reply produces the retry sentence with 4,501 / 3,000 / 1,501; the first user message equals
`writers._json(v225_writer.build_request(...)[0])`.

Existing tests that must change:

- `tests/test_typed_writers.py:155` `('length', 'x' * 3001)`: 3,001 now passes. Use `'x' * 4501`; at `:168` the
  expected retry for `length` is the typed sentence. The four content rows keep the assertion against
  `v225_cards.CARD_RETRY` unchanged: that is the proof of 1.2 item 10.
- `tests/test_typed_writers.py:176-182` (no reply): still true (`length`, `chars == 0`); add `bullets == 0` and
  the `REASON_NO_TEXT` retry.
- `tests/test_typed_writers.py:136-151`: passes unchanged; add `user == writers._json(expected)` (today only the
  parsed JSON is compared, `:147`) so it is the byte-identity proof of the first attempt.
- `tests/test_typed_chain.py:102` (fake `write_card`): record content `chars` and `bullets` for consistency; no
  chain test reads them [V grep]. Add one assertion that decision `chars == len(text) - 1` for an accepted card.
- Not changed: `tests/test_execskill_v225_cards.py`, `tests/test_execskill_v225_writer.py` (route-B tests of the
  frozen module). `tests/test_typed_cli.py:99` (`'typed-v1'`) belongs to the version area.

## 5. Interfaces to other areas

- Offered: `cards.CARD_TOLD_CHARS`, `CARD_HARD_CHARS`, `CARD_MAX_BULLETS`, `content_chars`, `card_screen`,
  `retry_text`, `pins()`, `LIMITS_RECORD`; attempt fields `chars` (content) and `bullets`; decision field `chars`.
- Unchanged for others: `write_card` signature and result keys `text`, `attempts`, `request`, `dropped` (the fake
  at `tests/test_typed_chain.py:94` stays valid); `screen_card` signature; `CARD_ATTEMPTS`; unit names and labels;
  `writer_screens_failed`; `revision_result` (`T/writers.py:222-239`, edited by the gate area, not by this one).
- Needed from the version area (D6): where `cards.pins()` is stored and checked at run start; the fate of
  `EXAMPLE_TAG`. From the machinery-guard area (D1): one shared helper that builds a real-machinery snapshot copy
  for fresh-interpreter tests; `T/cards.py` is a typed file and must not appear in `machinery-main-v10.sha256`.
- For the gate / caps area (D5, D6): a mounted card may be 1,500 characters longer than typed-v1's limit; the
  reservation grows by that many bytes per attempt of every card-mounted solver call (`T/units.py:143-164`).
- Shared files: `T/writers.py` (this area: `:30`, `:269-295`, docstrings), `T/chain.py` (`:54`, `:784`),
  `tests/test_typed_writers.py`, `tests/test_typed_chain.py`: implement the areas one after another.

## 6. Risks and open questions for the coordinator

1. Should the retry name the enforced limit of 4,500? Recommended: no. It states the actual length, 3,000 and the
   amount to cut (D2). Naming 4,500 would make it the limit the writer aims at.
2. Keep `_fit_examples` untouched and use the room rule (1.2 item 11), or raise the reserve to the longest typed
   sentence? Recommended: room rule. Raising the reserve can drop one more example and break the byte identity of
   the first request near the ceiling; the fallback sentence is the v2.25 one.
3. Keep the five v2.25 violation keys, or add keys such as `too_long` / `no_reply`? Recommended: keep the five;
   `chars`, `bullets` and `no_reply` give the cause, and no reader or test vocabulary changes.
4. Where do the card pins live? `T/` has no prompt-pin record today. Recommended: the version area writes
   `cards.pins()` into the prepare manifest and the run-start check compares it.
5. Told 3,000, enforced 4,500. Risks: reports must give content lengths and say both numbers (`card_limits` is in
   `writer.json`); solver, describer and revise requests grow by up to 1,500 characters per card (ALFWorld: every
   step call); a card above 3,000 cannot be packed as a v2.25 card `Procedure` (`X/package.py:196`) for the skill
   archive or a route-B implant. Recommended: accept; archive typed cards as typed skill records, and let the
   caps area include the longer card in its arithmetic.

## NOT DONE

- `COPIED_SOURCE_SHA256` is not computed (implementation step).
- Client and backend modules were checked for request-size limits by grep, not by a full read ([I] in 1.3).
- No test was run (rule of this phase). Measured from the constants instead: the lengths 199 / 201 / 207 to 256 /
  311, and that `RETRY_FRAME` / `RETRY_SHORT` equal the bound `CARD_RETRY` / `RETRY_REASONS` (AST read).
- This file has about 255 lines against the suggested 230; it was not trimmed further.
