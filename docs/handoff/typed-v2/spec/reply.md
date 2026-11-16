# typed-v2 spec: REPLY READING (decision D4; facts F1, F6)

Written 2026-11-12 by the reply-reading area. Marks: [V] = I opened and read the code, [I] = inferred. Short names:
`R:` = `X/engineer_reader.py` (frozen), `W:` = `T/writers.py`, `C:` = `T/chain.py`. No code was executed for this spec
(read-only rule); traces are by reading.

## 0. Blockers

No blockers. D4 can be met inside `T/`, `tests/`, `docs/`: every frozen helper the design needs is a public name
(`R:21, 23, 26, 49, 141, 234, 299` [V]) and typed touches the frozen reader only at `W:363, 455, 485` [V]. Note on a
map, not on DECISIONS: a new keyword on the frozen `engineer_reader.read` (`R:397` [V]) cannot work under F1 (the bound
run loads the snapshot's `read`); that route is not used.

## 1. Behaviour

### 1.1 Route: a typed-owned reader that reuses frozen public helpers

1. Engineer proposal replies and fix replies are read by one new module `T/replies.py`. It does not call the frozen
   `engineer_reader.read`; afterwards `W` uses `engineer_reader` only for `defined_hooks` (`W:363`).
2. Why not "typed pre-pass, then the frozen `read`" (from reading `R`): (a) any non-blank inline `source` wins and its
   fence gets no owner (`R:316`, `R:387-388` [V]); there is no notion of "real code", so the pre-pass would have to
   pick the source itself and delete the inline text, and the frozen reader would read a rewritten text instead of the
   recorded reply. (b) In a fix, a blank inline source with no fence silently inherits the failed source
   (`R:391-393` [V]); a pre-pass can only detect that afterwards (`R:610`). (c) Top-level `change` is dropped as an
   unknown key and the fix then fails (`R:561`, `R:574-575` [V]); a fix reply with only a code fence is refused
   (`R:556-557` [V]); repairing both means writing the manifest logic of `R:534-559` a second time. (d) `Unusable` is
   free text (`R:26-27` [V]); D4 needs a typed problem. (e) Typed admits only kind `new` (`W:495-498` [V]), so the
   private fence-ownership search (`R:307-382`) is not needed; no private frozen name is used.
3. Frozen helpers used, all public [V]: `engineer_reader.FENCE`, `MAX_REPLY_BYTES`, `Unusable`, `tolerant_json`,
   `schema`, `normalize`, `defined_hooks` (`R:23, 21, 26, 49, 141, 234, 299`); `profiles.HOOKS`, `profiles.MAX_CHANGES`
   (`X/protocol.py:222, 427`, re-exported at `X/profiles.py:10`); `engineer.EDIT_KINDS` (imported so at `R:531`).
4. Regression guard: for every well-formed reply the typed reader returns the same `entry` and `source` as the frozen
   `read`; a parity test proves it, also in a fresh interpreter under `bind_machinery` (§4).

### 1.2 Reading rules (general tolerance, no field patches)

5. Size: a reply above `MAX_REPLY_BYTES` (1,048,576 bytes) → problem `oversize`; nothing else is read.
6. Blocks: found with the frozen `FENCE`. A JSON candidate is a block tagged json/jsonc/json5, or untagged with text
   starting with `{` or `[`. All other blocks are code blocks.
7. Manifest, tried in order. (a) JSON candidates are parsed with `tolerant_json` (duplicate keys, non-finite numbers,
   depth above 64 stay errors, `R:22, 60-66` [V]); exactly one → the manifest. (b) Several: the single one with a
   `changes` or `change` key (repair `extra_json_blocks_ignored`, as `R:553`); else problem `several_manifests`.
   (c) No JSON candidate: the text outside the fences when it parses as a whole to an object or list (with no fence
   at all this is the frozen rule, `R:539-540`); else exactly one balanced top-level `{...}` in that text that parses
   (repair `manifest_outside_fence`). (d) Fix only: still none, and at least one code block → the entry of the change
   under repair is reused (repair `manifest_absent_inherited`; same idea as the frozen field inheritance, `R:616`).
   (e) Else problem `no_manifest`; `manifest_json` (with the parser message) when a JSON candidate, or outside text
   starting with `{` or `[`, existed but did not parse.
8. Envelope → changes. `changes` → its value; `change` instead → its value (repair `alias_change`); both: equal → one,
   different → problem `ambiguous_envelope`. A single object where a list is expected is wrapped
   (`single_change_wrapped`). An object with neither key but with `source`, `code` or a field name of `schema('new')`
   is the one change (`bare_change`); a top-level list of objects is the list (`bare_list`). Else problem
   `no_changes_key`, naming the top-level keys found. A non-object element → change problem `change_not_object`. An
   explicit empty list is a readable "no proposal": no problem, no retry.
9. Counts (strict): more than `profiles.MAX_CHANGES` (3) changes → problem `too_many_changes`, no truncation (as
   `R:572-573`). A fix reply must contain exactly one change, else `fix_change_count` (as `R:574-575`).
10. Kind: as the frozen reader (`R:593-603` [V]): missing → `new` unless the id is in `parent_ids`; a revision of an
    unknown id is `new` (`unknown_revision_is_new`); a word outside `EDIT_KINDS` → change problem `unknown_kind`.
    Other kinds are returned without source and dropped by `W` as `kind_not_new`, as today. In a fix the kind is that
    of the change under repair; a different stated kind is ignored (`fix_kind_ignored`; frozen refuses, `R:604-607`).
11. "Real code", one definition, used only to choose between candidates: `is_program(text)` iff
    `engineer_reader.defined_hooks(text)` is non-empty: the text parses as a Python module AND defines at module level
    at least one function named in `profiles.HOOKS` (`R:299-304` [V]). The required entry point is "at least one
    registered hook" because the bound package rule does not demand `applies` (`X/package.py:133, 145-146` [V]; a
    missing `applies` mounts as `default_true`, `T/mount.py:120` [V]).
12. Block ownership. `E` = the `new` changes in order; `B` = the code blocks in order, reduced to the program blocks
    when any block is a program. (A1) `len(B) == len(E)` → by position. (A2) else `len(B)` equals the number of
    entries whose inline source is not a program → by position among those. (A3) else `len(E) == 1` → every block is
    a candidate of that change. (A4) else each entry without a program inline source gets change problem
    `blocks_not_assignable` (both counts stated).
13. Source of a `new` change. Candidates: the inline value (`source`, alias `code`; a fenced inline value is unfenced,
    as `R:405-435`) and the owned block(s). (S1) Keep the program candidates; equal texts count once. In a fix, a
    program candidate equal to the failed source is an echo and is dropped when another program candidate remains
    (`echo_source_dropped`). One left → the source; two or more different left → change problem `ambiguous_source`
    (never guess). (S2) No program candidate: a single owned block, else the non-blank inline text, is returned with
    `is_program = false`, so the unchanged screen names the fault and the fix call gets evidence (a program with a
    syntax error must reach the screen). (S3) No text, or several non-program blocks → change problem `no_source`.
    Never inherited from the failed change or the parent (unlike `R:391-393`); never altered (byte-exact apart from
    removing fence lines).
14. Entry fields: the entry without `source`/`code` goes through the frozen public `normalize(entry, schema('new',
    train=False, source=source, entry=entry), inherited=(fix_entry or {}, {}), repairs=log,
    configuration=MACHINERY)`, the call of `R:616-618` for mode `single` (`W:453, 483` [V]). A frozen `Unusable` there
    → change problem `entry_field` with its message. Replay tests are not read (`W:366` ignores them).
15. Recorded about the choice, per record: `read = {source_from: 'fence' | 'inline' | 'inline_and_fence_equal' | None,
    is_program, hooks_defined, ignored: [{from, chars, sha256, why}], reply_sha256, reader}` and `repairs` rows in
    the frozen row shape `{'rule', 'path', ...}` (`R:258, 270` [V]).
16. Strict: the reader only parses (`ast.parse` inside `defined_hooks`, restricted literals inside `tolerant_json`);
    it never executes, imports or compiles reply text and never calls or replaces the screen. Every returned source
    goes unchanged into `build_procedure` → `policy.check(source, version=POLICY_VERSION)` + `Procedure` validation
    (`W:396-415` [V]), then the sandbox smoke unit; source size is judged only there. Tolerance decides WHICH text is
    screened, never WHETHER; the text not chosen is recorded (length + sha256).
17. The readers never raise for reply content (`RecursionError` / `MemoryError` → problem `resources`); `ValueError`
    only for caller mistakes.

### 1.3 The one format retry per unit

18. Trigger: a reply was delivered (`reply_of` not None, `W:62-67` [V]) and nothing readable came back: a whole-reply
    problem, or every change has a problem (fix: its one change has a problem). NOT a trigger: `no_reply`, an empty
    `changes` list, at least one readable record, a readable source that fails the screen (the fix call's job).
19. Budget: `FORMAT_RETRIES_PER_UNIT = 1` per `s<k>/programs` unit. The proposal call and all fix calls of a step
    share that unit and one call recorder (`C:854-865` [V]); the first unreadable reply in processing order takes the
    retry. A later one is recorded with `format_retry = {'skipped': 'budget_spent', ...}` and handled as in typed-v1.
20. Request: a new small request; the proposal payload is NOT re-sent (that would be a second proposal sample, not a
    format repair). system = `FORMAT_RETRY_SYSTEM`; user = canonical JSON `{"request": "format_retry", "purpose":
    "propose" | "fix", "bench", "problems": [{"code", "change", "detail"}], "expected_format": REPLY_FORMAT[purpose],
    "previous_reply": <verbatim>}`. No retry when the previous reply exceeds `RETRY_PREVIOUS_REPLY_BYTES = 200_000`
    (`'skipped': 'reply_too_large'`).
21. `FORMAT_RETRY_SYSTEM` (pinned): "Your previous reply could not be read. `problems` states exactly what was
    unreadable. Send the same content again in the format given in `expected_format`. Do not change what the program
    does; repair only the format. Give each program exactly once, inside one fenced python block, and put no program
    text inside the JSON." Each `detail` is one sentence from a fixed template per code, e.g. `no_changes_key`: "The
    JSON object has the top-level keys ['plan', 'notes']; none of them is `changes`."; `ambiguous_source`: "Change 1
    gives two different programs: inline `source` (1,204 characters) and fenced block 1 (1,377 characters). Send
    exactly one."; `no_manifest`: "No JSON object was found (fenced code blocks: 0; other text: 412 characters)."
22. The retry reply is read by the same function with the same arguments. Readable → the unit continues with it and
    lineage `engineer_call` is the sha of the retry call (the call whose reply supplied the source). Unreadable or no
    reply → recorded, handled as unreadable; no second retry.
23. Cost: the retry uses the unit's `role_call('program_writer', unit, 'writer', WRITER_TOKENS)` (`C:860-865`) and is
    reserved like any call: at most `4 x (request bytes + 512 + 32,768)` tokens (`T/units.py` `before_send`;
    `coevo5/protocol.py:278-279` [V]), about 0.95M worst case until settled. No cap change is requested.

## 2. Change list

| File | Today | Change |
| --- | --- | --- |
| `T/replies.py` (NEW, about 300 lines) | does not exist | The reader of §1. Constants `READER = 'typed-reply-reader-1'`, `FORMAT_RETRIES_PER_UNIT = 1`, `RETRY_PREVIOUS_REPLY_BYTES = 200_000`, `PROBLEM_CODES`, `REPAIR_RULES`, `REPLY_FORMAT`, `FORMAT_RETRY_SYSTEM`, `PROBLEM_SENTENCES`, `MACHINERY_SYMBOLS`; functions and class of §5. Imports from X only `engineer`, `engineer_reader`, `profiles`; from `T/__init__` only `MACHINERY`. |
| `W:30` | `from . import library, units` | add `replies`. The `engineer_reader` import (`W:23`) stays for `W:363`. |
| `W:436-439` `_row` | eight keys | two new keyword arguments and keys `read=None`, `format_retry=None`. |
| `W:442-466` `_fix_once` | `W:452-461` build `engineer.Change` and `ctx`, call `engineer_reader.read(reply, ctx, fix_change=change)[0]`, catch `Unusable` | `W:452-461` replaced by `replies.read_with_retry(reply, sha, purpose='fix', bench=bench, send=lambda s, u: _send(call, s, u), budget=budget, read=lambda text: replies.read_fix(text, change={'entry': entry, 'source': source}))`. New keyword argument `budget`. The fix record (`W:448, 462`) gains `read`, `format_retry`, `problem`; `reason` becomes `('unparseable: %s: %s' % (code, detail))[:MAX_DETAIL_CHARS]` (prefix kept). `W:463-464`: `engineer_call` = the outcome's `request_sha256`. |
| `W:469-515` `propose_programs` | `W:483-487` build `ctx`, call `engineer_reader.read(reply, ctx)`, `Unusable` → one row | `budget = replies.RetryBudget()` after `W:480`; `W:483-487` replaced by `read_with_retry(..., purpose='propose', read=lambda text: replies.read_proposals(text, parent_ids=tuple(parent.order)))` (`parent.order` as at `W:488` [V]). Whole-reply problem → one row as today with the reason form above. Per record: `problem` → the error row of `W:491-494`. `budget` is passed to `_fix_once`. Rows carry `read` and `format_retry`. Loop order, `kind_not_new` (`W:495-498`), ids (`W:503-504`) and `build_procedure` are not changed by this area; `W:499-502` (candidate limit, promotion) belongs to the engineer area. |
| `W:310-315` `engineer_system` | purposes `propose`, `fix` | none by this area; the engineer area's new prompt embeds `replies.REPLY_FORMAT[purpose]` (§5). |
| `T/smoke.py:36-41, 180` | one scripted `DEFAULT_PROGRAM` reply | recommended: one scripted programs unit whose first reply is unreadable text and whose retry reply is `DEFAULT_PROGRAM`, so the smoke exercises the retry once. Shared file; order fixed in IMPLEMENTATION-ORDER. |
| `T/chain.py` | `C:854-892` | none by this area: the chain reads only `screen.passed` / `screen.reason` of a row (`C:871-892` [V]). |
| `tests/test_typed_replies.py` (NEW), `tests/test_typed_writers.py` | | §4. |
| `X/*`, `skillopt/coevo5/*` | | no edit (F1, D1). |

## 3. Records and identity

- `s<k>/programs/proposals.json` rows (`W:436-439`). NEW `read` (item 15; None without a reply) and `format_retry`:
  None, `{'first_request_sha256', 'request_sha256', 'problems', 'no_reply', 'readable', 'problems_after'}`, or
  `{'skipped': 'budget_spent' | 'reply_too_large', 'problems'}`. CHANGED: a row's `request_sha256` is the call whose
  reply produced the row (the retry call when the retry was used). `repairs` keeps the frozen row shape; new rule
  names: `alias_change`, `single_change_wrapped`, `bare_change`, `bare_list`, `manifest_outside_fence`,
  `manifest_absent_inherited`, `inline_not_program_ignored`, `fence_not_program_ignored`, `echo_source_dropped`,
  `fix_kind_ignored`. `screen.reason` of an unreadable reply: `'unparseable: <code>: <detail>'` (typed-v1:
  `'unparseable: ' + frozen message`, `W:487`).
- The `fix` record in a row (`W:448, 462`): NEW `read`, `format_retry`, `problem`; the other keys keep their meaning.
- Calls file `s<k>/programs/calls/writer-program_writer.json` (`C:1052-1054` [V]): at most one more send per unit;
  the unreadable reply and the retry reply are both stored in full, so any reading can be redone offline.
- `s<k>/program-<i>/decision.json`: same fields; `reason = 'screen:' + row reason` (`C:891-892` [V]) shows the new
  text. Lineage `engineer_call`: same field, one more possible origin (the retry call).
- Ledger: no new field, at most one more call key per programs unit. Manifest: no field from this area; it offers
  `replies.READER` and `replies.MACHINERY_SYMBOLS` to the identity area. Readout: no change (`T/readout.py` reads
  none of `proposals`, `repairs`, `fix`, `unparseable`; grep [V]).
- NEW pinned texts: `FORMAT_RETRY_SYSTEM`, `REPLY_FORMAT['propose' | 'fix']`, `PROBLEM_SENTENCES`; their sha256 go
  into the typed-v2 prompt-pin fixture. The retry request is a new request kind (`"request": "format_retry"`) with
  its own sha; it cannot collide with a proposal or fix request.
- NOT changed by this area: `request_sha256(system, user)` (`W:57-59`), the proposal request (built at `W:477-480`,
  before any reading), the fix request builder (`W:445-446`). How I know: the reader runs only after `_send` returned;
  the only reader outputs entering a later request are `entry` and `source` of a readable record (`W:446`), and the
  parity test shows them equal to the frozen reader's wherever the frozen reader could read. Where it could not,
  typed-v1 sent no fix request, so no typed-v1 text exists to differ from. (D3 and D6 change request texts; this
  area adds nothing to that.)

## 4. Tests

New file `tests/test_typed_replies.py` (literal strings, no network). `HOOKED` = a small legal program defining
`applies` and `before_call`. Each table row is one case of the parametrised `test_fixture_table`:

| Id | Reply | Mode | Expected |
| --- | --- | --- | --- |
| F1 (typed-v1 loss) | json fence `{"change": {"id": "p1", "description": "..."}}` + python fence `HOOKED` | fix | one record, source from the fence, repairs `alias_change` + `single_change_wrapped`, no problem |
| F2 (typed-v1 loss) | json fence `{"changes": [{"id": "p1", "source": "PLACEHOLDER"}]}` + python fence `HOOKED` | fix | `source == HOOKED`, `read.source_from == 'fence'`, `read.ignored == [{'from': 'inline', 'chars': 11, 'why': 'not_program', 'sha256': ...}]` |
| F3 ambiguous | inline `source` = program A, python fence = program B, A != B, neither equals the failed source | fix | change problem `ambiguous_source`, detail states both lengths, `readable()` is false |
| F3b echo | inline `source` = the failed source, python fence = a new program B | fix | `source == B`, repair `echo_source_dropped` |
| F4 unreadable | `I could not find a safe change, sorry.` (no JSON, no fence) | both | whole-reply problem `no_manifest`, detail states the length |
| F5 canonical | `smoke.DEFAULT_PROGRAM`; the `two_fence` shape of `tests/test_typed_writers.py` | propose | no tolerance repair; `entry` (without `replay_tests`) and `source` equal the frozen `engineer_reader.read` result |
| F6 single / bare | `{"changes": {...}}`; a bare change object; a bare list of two objects with two python fences | propose | records read; repairs `single_change_wrapped` / `bare_change` / `bare_list`; blocks by position (A1) |
| F7 code only | one python fence `HOOKED`, no JSON | both | fix: one record with the entry under repair, repair `manifest_absent_inherited`; propose: problem `no_manifest` |
| F8 broken program | manifest + python fence with a syntax error | fix | record returned with `read.is_program is False`, `source_from == 'fence'` (the screen, not the reader, rejects it) |
| F9 too many | four changes, four python fences | propose | problem `too_many_changes` (4 > 3), no record |
| F10 nothing new | `{"changes": [{"id": "p1", "source": ""}]}`, no fence | fix | change problem `no_source`; the failed source is NOT returned |
| F11 unassignable | three `new` changes without inline source, two python fences | propose | three change problems `blocks_not_assignable` (3 changes, 2 blocks) |
| F12 abstain | `{"changes": []}` | propose | no record, no problem, `readable()` is true |

Further new tests:
- `test_parity_with_frozen_reader`: F5 shapes plus an untagged JSON fence, an inline-only source, and two changes
  with two fences; typed result equals the frozen `read` result (the guard of item 4).
- `test_reader_never_raises` (random text, 100 nested brackets, duplicate keys, a 2 MB reply → problems only) and
  `test_reader_does_not_execute` (a fenced program with a module-level `open(path, 'w')`; no file after reading).
- `test_tolerance_does_not_weaken_screen`: an F2-shaped reply whose fenced program has `import os`;
  `writers.build_procedure` rejects it with the same reason as the same source sent in canonical form.
- `test_retry_request_text` (per problem code: the exact sentence, the previous reply verbatim, `REPLY_FORMAT[purpose]`;
  above 200,000 bytes → `None`) and `test_reply_pins` (sha256 of the pinned texts equal the fixture).
- In `tests/test_typed_writers.py`: `test_format_retry_once_per_unit` (unreadable proposal, readable retry → rows from
  the retry, 2 calls, lineage sha = the retry call); `test_retry_budget_shared_with_fix` (screen-failing proposal,
  unreadable fix reply, readable retry → 3 calls; a second unreadable fix → `skipped: budget_spent`, no further call);
  `test_no_retry_on_no_reply`; `test_retry_still_unreadable` (2 calls, reason starts with `unparseable`).

Existing tests that must change:
- `tests/test_typed_writers.py:307-308`: `propose(Script(['no fences here, just prose']))` expects exactly one call.
  The reply now triggers the retry and `Script` (`:33-42`) raises `IndexError` on a second call: give it a second
  reply, assert 2 calls and the `format_retry` record. `:310` (`no_reply`) stays.
- `tests/test_typed_writers.py:271-294`: assertions on the fix record must allow the new keys `read`, `format_retry`,
  `problem` (the request key set `{'request', 'bench', 'change', 'failed'}` is the engineer area's to change).
- Unchanged, now regression checks of the new reader: `tests/test_typed_writers.py:223-237`,
  `tests/test_typed_e2e.py:123`. `tests/test_typed_chain.py:105-113` (fake writer) needs no change for this area.

Fresh interpreter under `bind_machinery` (pattern `tests/test_typed_cli.py:80-105`): `test_replies_under_bound_machinery`.
The existing test uses a fake snapshot of marker modules, which cannot run a reader, so this test copies this tree's
`skillopt/` WITHOUT `execskill/typed/` to `tmp_path` as the snapshot, starts `python -I -c` without `PYTHONPATH`, calls
`bind_machinery` (`scripts/run_typed.py:35-54` [V]) and asserts: `skillopt.execskill.engineer_reader.__file__` lies in
the snapshot; `skillopt.execskill.typed.replies.__file__` lies in this tree; every name in
`replies.MACHINERY_SYMBOLS` resolves; F1, F2, F3, F4, F5 give the table results; the F5 parity holds against the
snapshot's `read`.

## 5. Interfaces to other areas

Offered to the engineer area (D3), all in `T/replies.py`:

```python
is_program(text) -> bool
read_proposals(reply, *, parent_ids=()) -> result
read_fix(reply, *, change) -> result   # change = {'entry': dict, 'source': str}; one record or a problem
readable(result) -> bool               # no whole-reply problem and (no records or >= 1 record without problem)
retry_request(purpose, bench, problems, previous_reply) -> (system, user) | None
class RetryBudget: take() -> bool      # one instance per programs unit; True exactly FORMAT_RETRIES_PER_UNIT times
read_with_retry(reply, sha, *, purpose, bench, send, budget, read) -> outcome
```

- result = `{'records': [record], 'problem': None | problem, 'repairs': [...], 'reply_sha256', 'reader'}`;
  record = `{'n', 'kind', 'entry': dict | None, 'source': str | None, 'problem': None | problem, 'repairs', 'read'}`;
  problem = `{'code': one of PROBLEM_CODES, 'detail': sentence, 'change': int | None}`;
  outcome = `{'result', 'request_sha256': the call whose reply is in result, 'format_retry': None | dict}`.
- `send(system, user) -> (reply | None, sha)` is passed in (`lambda s, u: writers._send(call, s, u)`), so `replies`
  never imports `writers`.
- `PROBLEM_CODES`: the closed tuple of the 15 codes named in items 5-17 (`oversize` ... `resources`).
- Errors: none for reply content; `ValueError` for caller mistakes (unknown purpose, `change` without `entry` and
  `source`); `units.Stop` from the ledger passes through `send` untouched.

Needed from other areas:
- Engineer area: (a) its prompt embeds `replies.REPLY_FORMAT[purpose]` (owned here; a test checks the prompt contains
  it), so prompt, retry and reader cannot drift apart. (b) Promotion: a record with a `problem` is dropped without a
  fix call (nothing to fix) and the next proposal takes its place, like a screen failure. (c) Every fix call passes
  the unit's `budget`. (d) Recommended: the fix request stops sending the failed program as inline `change.source`
  (`W:446`), the shape the two lost typed-v1 replies mirrored; a separate `failed_source` field avoids the echo. The
  reader does not depend on this.
- Identity area (D1/D6): the pins of §3; `MACHINERY_SYMBOLS` joins the run-start check of bound symbols.
- Card, gate and schedule areas: no interface.

## 6. Risks and open questions for the coordinator

1. Budget scope. D4 says one retry per unit; the programs unit holds the proposal reply and up to three fix replies,
   so a second unreadable reply in one step gets no retry. Recommended: keep one per unit as decided; the raw reply
   stays in the calls file and the constant is one line if practice shows otherwise.
2. Two different real programs in one change. Recommended: never guess; treat as unreadable (retry if the budget
   allows), with the one exception of the echo rule (a candidate identical to the failed source is dropped).
3. A module without any hook function can pass the frozen screen as an inert procedure (`X/package.py:145-146` [V];
   whole path [I]) and would then cost a gate; the reader only marks it (`is_program = false`). Recommended: the
   engineer area adds a typed check in `build_procedure` (reason `no_hook_function`), a screen-stage failure with
   evidence for the fix call.
4. Retry request style. Recommended: the small "repair the format" request of item 20, not a re-send of the proposal
   payload: cheap, cannot change the proposal's content sample, and states exactly what was unreadable.
5. Interruption. `proposals.json` is written once, after all calls of the unit (`C:316-323, 860-865` [V]); an
   interruption repeats the proposal, fix and retry calls. Not new; one more call at risk. Recommended: accept for
   typed-v2 and do not split the unit (unit names are fixed by D3).

Nothing in this area is left undone. Not verified by execution (no code runs allowed): the parity claim of item 4 and
the `normalize` behaviour for a fix entry ([I]); the tests of §4 cover both and must pass before the area closes.
