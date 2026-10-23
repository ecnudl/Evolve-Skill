# Codex review of route B v2.1 (one round, 2026-10-24 03:0x)

Reviewer: `codexdl exec -m gpt-6-astra -c model_reasoning_effort="ultra" -s read-only` over a mirror of the dev tree
(`skillopt/`, `scripts/`, `tests/`, `docs/handoff/`, the `main21*` launch scripts; no data, no `.env`), brief
`BRIEF-v21.md` (six priorities: the v2.1 configuration's equality with main-v2, the pool fix, the type guards, the
redaction, the counterfactual, the launch scripts; in this folder). The full output is kept outside the tree:
`/root/ops2-20261022/logs/v21/codex-review-v21.out`.

**Verdict: NOT ACCEPTABLE -- 4 MAJOR, no BLOCKER.** The reviewer confirmed offline: older configurations' constants,
namespaces, record hashes, caps and prompts unchanged; all 18 pricing-equivalence checks; the pool simulation; 910
malformed-value mutations; the counterfactual catching a p-livemath-3-1-style predicate while generic guidance and
option counting pass. It could not run pytest (read-only sandbox) and saw the mirror's git at d8260f1 (ancestry
reviewed statically).

| # | Finding | Fix (snapshot g) |
|---|---------|------------------|
| 1 MAJOR | `research.py:201`: the chain's Wikipedia client still had httpx's default 100-connection cap through the same gateway (offline: 100 ConnectTimeouts, then PoolTimeout) | `research.Wikipedia` builds its client with `client.POOL_LIMITS` (timeout, headers, redirects unchanged); test `test_the_research_wikipedia_client_has_no_connection_limit_either` (stalling proxy: 4 × ConnectTimeout, no PoolTimeout) |
| 2 MAJOR | `generators/sheet.py:192`: a written edit such as `A1048577` passed validation and raised openpyxl's ValueError, which `sheet.apply`/`generators.generate` (catching only `Drop`) let through, leaving the output folder | `_edits` refuses a target outside A1:XFD1048576 (`edit_target_invalid`) and a formula with a character a worksheet cannot store (`format`, openpyxl's `ILLEGAL_CHARACTERS_RE`; it raised IllegalCharacterError) before any file is written; parametrized test with `A1048577`, `XFE1` and a control character |
| 3 MAJOR | `engineer.py:564`: redaction bypassed through the shown trajectories -- `shell.faults[*].message` and `shell.notes[*].dropped[*].detail` carry the screens' matched phrases into the proposal and analyst calls | with `Context.echo` False (main-v2-1 train mode) `_shown_view` passes the shell through `_unechoed`: the message of a `note_lexicon`/`note_meta_option` fault and the detail of a field dropped for `lexicon`/`meta_option` become null, kinds/fields/reasons kept; every other configuration unchanged (echo True). Tests: unit (`_shown_view` on and off) and end to end (a training round's analyst and proposal payloads, echo on/off) |
| 4 MAJOR | `main21_delta.py:21`: `V21_PATCH_SHA256` was None, so `git_delta` always aborted -- after `main21-snapshot.sh` had created snapshot g and its write-once files | `main21-snapshot.sh` runs `git_delta` right after the clean-tree check, before any artifact; `V21_PATCH_SHA256` is the sha256 of `git diff d44966d <g> -- skillopt scripts tests` of the committed g, recorded below; `V21_CODE` also lists `research.py` and `generators/sheet.py` |

Also changed while fixing: mutation 30 (`tests/test_execskill_mutations.py`, "glm-solver-client-adds-a-route") names
the frozen construction inside `unpooled` (its old site moved with v2.1's change 1; the registered selection before
the review had this as its only failure). Verification after the fixes: targeted tests 187 passed; zero-call
validation on main-v2's real LiveMath records (spec-v21.md, "Codex review and zero-call validation"): the adopted
shortcut is flagged on 65/65 meta-present items, generic and counting controls 0/119; the registered selection was
run again before the commit (launch record in the registrar).

No second Codex round (registrar rule since 10/17: one round per item; a second only if the smoke fails). The smoke of
record is not re-run: main-v2-1 is priced exactly as main-v2 (`main21_delta.priced_as_main_v2`), the configuration
the smoke's S-E6 projected.
