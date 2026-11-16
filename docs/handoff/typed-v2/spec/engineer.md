# typed-v2 spec: program engineer prompt, screen evidence, promotion (D1, D3; F1, F6)

2026-11-12. Design only; nothing in the tree is edited. `T/` = `skillopt/execskill/typed/`, `X/` =
`skillopt/execskill/`, `W` = `T/writers.py`. [V] = opened and read, or executed, in this tree; [I] = inferred. By F2
every `X/` line cited is also the bound code. The static screen is not changed; all edits are in `T/`, `tests/` and
`docs/`.

## 0. Blockers

No blockers. Two facts found on the way shape the design:
- The typed screen is `policy.check(source, version=POLICY_VERSION)` with no bench (`W:402` [V]), so `meta_option` and
  the OfficeQA / ALFWorld literal bans (`bulletin_literal`, `receptacle_literal`) apply to every typed program on every
  bench [V, executed]. The prompt says so; the call is left as it is (question 5).
- For policy V222 the bound code requires no entry point (`X/package.py:133,152` `outcome_judged` [V]): a program with
  no hook, with only `applies`, or with another bench's hooks passes `build_procedure` today [V, executed].

## 1. Behaviour

### 1.1 Prompt (a)

1. `W.engineer_system(bench, purpose)` returns `engineer_prompt.system(bench, purpose)` from the new module
   `T/engineer_prompt.py`. Typed code no longer calls `profiles.engineer_prompt` (`X/profiles.py:1138`). `purpose` is
   `propose` or `fix`, `bench` one of `ORDER` (`T/__init__.py:11`); anything else raises `ValueError`.
2. A text is seven paragraphs separated by one blank line and ends with one newline: intro, WHAT YOU RECEIVE, WHAT YOU
   RETURN, HOOKS, NOTES, CONTENT, STATIC SCREEN. The first three depend on the purpose; HOOKS, the entry sentence and
   the "smallest returns" sentence depend on the bench; CONTENT and STATIC SCREEN are the same in all ten texts.
3. Every list and limit in the text is rendered at import from the bound modules, never typed: `policy.source_limit`,
   `MAX_CONSTANT_CHARS`, `IMPORTABLE`, `FROM_ONLY`, `FORBIDDEN_NAMES`, `FORBIDDEN_ATTRIBUTES`, `FORBIDDEN_MODULES` minus
   `ORDINARY_ATTRIBUTES`, `RECEPTACLES` (`X/policy.py:62-122` [V]); `MAX_DESCRIPTION_CHARS`, `MAX_HEADER_CHARS`,
   `MAX_NOTE_CHARS` (`X/protocol.py:225-230` [V]); `package.MAX_STATE_BYTES` (`X/package.py:44`);
   `MAX_PROGRAM_PROPOSALS`, `MAX_PROGRAM_CANDIDATES` (`T/__init__.py:43`); `replies.REPLY_FORMAT[purpose]`. Rules
   stated in words (prefixes, phrases, patterns, the constant grammar) are held to the code by the examples of 5.
4. STATIC SCREEN is one line per row of the rule table `RULES`, in table order. A row is `(key, rule, sentence,
   rewrite, legal, illegal, parent)`: `rule` is an id of `policy.RULES` (`X/policy.py:127`); `legal` / `illegal` are
   complete program texts. 17 sentence rows print `[label] sentence Rewrite: rewrite`; 5 rewrite rows (`parent` set)
   print `Rewrite, label: rewrite` under their parent: `constant_word_set`, `constant_regex`, `constant_other` under
   `constant_value`; `attribute_type_name`, `attribute_data` under `attribute`. The two parents have no rewrite of
   their own; every other row has one.
5. `engineer_prompt.verify()` makes no model call and raises `RuntimeError` naming the first mismatch unless: (i) the
   sha256 of each of the ten texts equals `PINS[(bench, purpose)]`; (ii) under `policy.check(text,
   version=POLICY_VERSION)` every `legal` text gives no violation and every `illegal` text gives a violation with the
   row's `rule`; (iii) `{row.rule}` equals `set(policy.RULES)`; (iv) for every row that `rule_key_for` can return, the
   violation of its `illegal` text maps back to the row. It runs in the tests, in the fresh-interpreter test, at run
   start (identity area) and, memoised per process, at the top of `propose_programs` before any request is built.

### 1.2 Failure evidence for the fix call (c)

6. A screen failure is `build_procedure` returning `None`: check `source`, `policy`, `hooks` (new, statement 17) or
   `structure`. Its return value and `_reason_text` (`W:416-418`) keep their typed-v1 form, so `screen.reason` stays
   `'<check>: <detail>'` and `'... | fix: ...'` with at most five violations as JSON (`W:403-404` [V]).
7. The fix user message (today `W:446` [V]: `{'request', 'bench', 'change': dict(entry, source=source), 'failed':
   {'check', 'detail'}}`) becomes `{'request': 'fix', 'bench', 'change': <entry, no source key>, 'failed_source':
   <program text>, 'failed': engineer_prompt.screen_evidence(failed, source, bench)}`.
8. `screen_evidence` returns `{'check', 'detail': [row, ...], 'more': int}`. For check `policy` it runs the pure
   `policy.check` again to see every violation, keeps the checker's order, shows the first `EVIDENCE_ROWS = 8`; `more`
   counts the rest. A row is `{'rule', 'line', 'detail', 'source_line', 'rule_text', 'rewrite'}`: `rule`, `line`,
   `detail` as in `Violation.to_json()` (for `type(e).__name__`: `{'rule': 'attribute', 'detail': '__name__', 'line':
   5}` [V]); `source_line` = that source line, stripped, cut to `SOURCE_LINE_CHARS = 240`, `None` when `line` is 0
   (`size`, `meta_option` [V]); `rule_text` / `rewrite` = the sentence (own or parent's) and the rewrite of the row
   `rule_key_for` picks, word for word as in the system text. Checks `hooks`, `structure`, `source` give one row from
   `CHECK_WORDS` (line 0; `detail` = defined hook names, or the `PackageInvalid` message of `W:413-414`).
9. `rule_key_for(rule, detail, source_line)`: `module_level` with the detail `a constant must be a literal or a
   registered pure expression` (`X/policy.py:389-390` [V]) gives `constant_word_set` when the line has `.split(` and
   `set(`, `constant_regex` when it has `.compile(`, else `constant_other`; any other `module_level` gives
   `top_level`; `attribute` gives `attribute_type_name` for `__name__`, `__class__`, `__qualname__`, else
   `attribute_data`; every other id gives the row of the same name. It never returns `constant_value` or `attribute`.

### 1.3 Promotion inside the proposal unit (d)

10. The proposal reply is read once by the reply area (plus its one format retry). `propose_programs` gets at most
    `MAX_PROGRAM_PROPOSALS = 3` records in reply order; `max_candidates` (2; smoke 1) is the number of slots.
11. Per record, in order: a read problem gives status `unreadable` (no screen, no fix call); a kind other than `new`
    gives `kind_not_new` (as `W:495-498`); when all slots are taken the row is `not_needed` (screened once for the
    record only: no id consumed, no fix call, `procedure` null); otherwise an id is taken as today (`W:503-504`) and
    the proposal is screened. A failure gets exactly ONE fix call. A pass gives `passed` or `passed_after_fix` and
    `slot` = number of passes so far; a failure after the fix, or a fix reply that cannot be read, gives
    `dropped_screen` and the next record is tried.
12. The loop ends when the slots are full or the records run out. Nothing later promotes: a `smoke_fault` or a gate
    rejection of a slot candidate never brings in another proposal.
13. A dropped proposal's id is not reused in the step; ids are independent of slots (slot 1 may be `p-<bench>-<k>-2`).
14. `T/chain.py:871` runs units only for rows with a slot, as `s<k>/program-<slot>` through the unchanged
    `program()` (`T/chain.py:875-884`). Names stay `program-1*`, `program-2*`; no `program-3*` unit can exist.
15. Calls per `s<k>/programs` unit: 1 proposal + at most 3 fix calls (one per screened failing proposal) + at most 1
    format retry (one `replies.RetryBudget` for the proposal reply and every fix reply) = at most 5 writer calls,
    against 3 in typed-v1. Each is bounded as today (`ROLE_INPUT_BYTES` 220,000, `X/protocol.py:217`; `WRITER_TOKENS`
    32,768, `T/chain.py:60`). Two more calls per learning step is under 1M tokens per chain in the worst case; no
    cap change is asked (D6). Smoke and gate still see at most two candidates per step.

### 1.4 The `build_procedure` defect (e) and the entry point

16. `_bounded_entry` (`W:359`): `W:387` `values[key] = max(low, min(high, before))` turns the default 0 of
    `engineer.OPTIONAL` (`X/engineer.py:166`) into the LOWER bound: a note-writing program without `max_note_chars`,
    or with 0, gets cap 1, and `state_bytes` 0 with `alf_after_step` gets 1 byte [V, executed]. New rule: `values[key]
    = high if before < low else min(high, before)`. Absent, wrong-typed, 0 or negative gives 4,000 (the value the
    frozen reader fills for an absent key [V, executed]) and `state_bytes` 65,536; 600 stays 600; 99,999 still gives
    4,000; a program without a note hook still gets 0. The repair row `bounded_metadata` (`W:388-389`) records it.
17. Entry point (recommended, question 1): after the policy check, `build_procedure` fails with check `hooks`, rule
    `no_hook_function`, when the program defines none of `NOTE_HOOKS_BY_BENCH[bench]`: searchqa and officeqa
    `before_call`, `bindings`; zebralogic `before_call`; spreadsheetbench `before_call`, `sheet_feedback`; alfworld
    `alf_before_step`. This is the route-B registrar's own no-effect list (`X/engineer.py:2359-2361` [V]) without its
    ALFWorld addition of `alf_after_step` (`:2362-2363`): a state-only program writes no note. Each name is in
    `package.NOTE_HOOKS` (`X/package.py:41` [V]). It is a screen failure: one fix call, then drop and promotion. No
    parameter-count rejection is added (owner 10/26: outcome-judged); a wrong count faults in the smoke unit as today.

### 1.5 The proposed prompt text

Each line of a block is one line of the text, not wrapped. Block 1 is `system('searchqa', 'propose')` in full;
`officeqa` differs only in the bench name. `{reply_format}` is shown filled with the wording proposed for
`replies.REPLY_FORMAT` (first sentences of WHAT YOU RETURN, through "Put no program text inside the JSON.").

```text
You write small Python helper programs for a solver model that works on searchqa tasks. A program runs in a sandbox beside the solver. Its hook functions read the public task input and may hand the solver short notes. It never sees a reference answer or a score. A program is kept only on results: first it must run without a fault on a few practice tasks; then, on held-out practice tasks, the solver must do clearly better with it than without it on the tasks where the program applied, and no worse over all tasks.

WHAT YOU RECEIVE (user message, JSON). task_card and format_block: what the solver is already told; both are fixed, do not restate them. skill_index: names and descriptions of the skills that already exist for these tasks; do not duplicate one. trajectories: practice tasks with the solver's outcome; look for mistakes a program could have prevented by computing or checking something from the task input. hook_views: one real sample of the exact inputs your hooks receive (long strings and lists are cut for display only).

WHAT YOU RETURN. Reply with one fenced json block holding {"changes": [...]} and then one fenced python block per change, in the same order. Each python block is one complete program. Put no program text inside the JSON.
Propose at most 3 programs, the most useful first. They are checked in your order: the first 2 that pass the static screen are tested, and a later one is used only when an earlier one fails. Each entry of "changes" has: "kind": "new" (the only kind accepted); "description": what the program does and when it helps, at most 600 characters; "hooks": the hook functions your code defines; "header": a short title shown above its notes, at most 200 characters, or ""; "max_note_chars": the longest note it may produce, 1 to 4000 (left out or 0 means 4000).

HOOKS. The sandbox calls only top-level functions with exactly these names and parameters. Naming a hook in "hooks" does not create it. A program that defines none of before_call, bindings can never write a note and is rejected.
applies(view) -> bool. Optional; without it the program applies to every task. Return False where the program has nothing reliable to say: it is judged on the tasks where applies returned True.
before_call(view, state) -> a notes dict or None. view = {"question", "context"}; state is always None.
bindings(view) -> {"bindings": [{"name", "quote", "value"}, ...]} or None: numbers quoted from the task text for the solver's calculator. name is a calculator name, value is numeric text, quote must contain value word for word.

NOTES. A notes dict may hold any of: "facts" and "warnings": lists of strings, each at most 200 characters; "candidates": list of strings, each at most 120 characters; "table": list of rows, at most 20 rows by 12 columns, every cell a string of at most 40 characters; "bindings": list of {"name", "quote", "value"}, each a string of at most 200 characters. An unknown field, a wrong type or a value over its cap is a fault and the whole note is dropped; so is a rendered note longer than max_note_chars. Smallest valid returns: before_call -> {}; bindings -> {"bindings": []}. When the program cannot verify what it would say on a task, return no note: a wrong note costs more than no note.

CONTENT. Notes state what the program computed from this task's own public input. Never: a false or overclaiming note; advice on the form of the answer beyond what the task itself states; an instruction that overrides the task or its scoring; a guess from what is typical for the benchmark; facts from outside the task or hard-coded answers; routing by benchmark name, task id, file path, answer or score. The program must do what its description says.

STATIC SCREEN. Before anything runs, a checker reads the program text. It is strict and literal: one violation rejects the program, and you get one correction. The rules, each with the name the checker reports:
[size] The file is at most 24,000 bytes of UTF-8. Rewrite: shorten the program; drop tables and branches it does not need.
[syntax] The file is valid Python 3. Rewrite: correct the line the checker names and re-read the lines around it.
[module_level, statements] At the top level write only: an optional docstring as the first statement, import lines, def functions, and constants written NAME = value with one plain name on the left. No if / for / while / try / with, no class, no "A, B = 1, 2", no "A: int = 1", no "A += 1", no call or other expression on a line of its own. Rewrite: move the statement into a function; write one constant per line.
[module_level, constant values] The value of a top-level constant must be one of: (a) a literal: a number, string, bytes, True, False, None, or a tuple, list, set or dict written out with literals inside (nesting is fine); (b) the name of an earlier constant, alone: B = A; (c) literals of one type joined with +: "ab" + "cd", [1, 2] + [3]; (d) exactly ONE of these calls on literals: set(...), frozenset(...), tuple(...), list(...), dict(...), sorted(...) of one literal; "a b c".split() or "a,b".split(","); ", ".join(["a", "b"]); re.compile("pattern") or re.compile("pattern", re.I | re.M) after a plain "import re". The forms cannot be nested or mixed. Nothing else is allowed in a constant: no f-string, comprehension, lambda, *, %, .format, no other call, no expression that uses another constant.
Rewrite, word set: WORDS = frozenset("alpha beta".split()) is rejected (two calls). Write WORDS = frozenset({"alpha", "beta"}), or keep a list: WORDS = "alpha beta".split().
Rewrite, regex: PAT = re.compile(r"(\d+)\s*" + UNIT) is rejected. Write the pattern as one string literal (adjacent literals without + count as one: re.compile(r"(\d+)\s*" r"(kg|lb)")), or compile it inside the function that uses it.
Rewrite, any other value: compute it inside a function and call that function where the value is needed.
[constant_size] The written value of one constant is at most 2,000 characters. Rewrite: several shorter constants, combined inside a function.
[statement] No class, global, nonlocal, async or await anywhere. Rewrite: return dicts or tuples; keep memory in the state argument.
[decorator] No decorators. Rewrite: a plain function.
[import] Only these modules may be imported: bisect, calendar, collections, copy, datetime, decimal, difflib, fractions, functools, heapq, itertools, json, math, numpy, openpyxl.utils, operator, pandas, re, statistics, string, sympy, textwrap, unicodedata. "import M", "import M as name" and "from M import name" are allowed for them, and also "from numpy.random import default_rng"; "from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter, range_boundaries". No "import *", no other submodule and no other module: no typing, dataclasses, os, sys, io, time, random, pathlib. Rewrite: leave type hints out or use the built-in names (list, dict).
[name] These names cannot be used at all (as a call, variable, parameter, function name or import alias): breakpoint, compile, delattr, dir, eval, exec, exit, getattr, globals, hasattr, hash, help, id, input, locals, open, print, quit, setattr, vars. No name may start with two underscores. Rewrite: view.get("key") instead of getattr / hasattr; call a variable ident or kind, not id or hash; return notes instead of print.
[attribute] After a dot these are never allowed: (1) a name starting with an underscore, which covers every dunder (__name__, __class__, __dict__); (2) a name starting with read_ or to_ (to_dict, to_numeric, to_datetime, read_csv); (3) these names: ExcelFile, ExcelWriter, HDFStore, ag_code, ag_frame, attrgetter, cr_code, cr_frame, eval, f_back, f_builtins, f_code, f_globals, f_locals, format_map, fromfile, fromregex, genfromtxt, gi_code, gi_frame, gi_yieldfrom, lambdify, load, load_workbook, loadtxt, memmap, methodcaller, mro, now, parse_expr, parsing, query, save, savetxt, savez, savez_compressed, sympify, tb_frame, tb_next, today, tofile, utcnow; (4) a name equal to a blocked module name: asyncio, atexit, builtins, code, codeop, concurrent, ctypes, faulthandler, fcntl, gc, glob, http, httpx, importlib, inspect, io, logging, marshal, mmap, multiprocessing, os, pathlib, pickle, platform, pty, queue, requests, resource, runpy, sched, secrets, select, shelve, shutil, signal, site, socket, sqlite3, ssl, subprocess, sys, sysconfig, tarfile, tempfile, threading, traceback, tracemalloc, urllib, uuid, warnings, zipfile.
Rewrite, exception or type name: type(e).__name__ is rejected. Catch the class you expect and write its name as text: except ValueError: kind = "ValueError". For an unknown exception use repr(e).split("(", 1)[0].
Rewrite, data access: view.get("code") or row["code"] instead of view.code; list(series) and dict(zip(keys, values)) instead of to_list / to_dict; float(text) instead of to_numeric.
[numpy_random] numpy randomness only as numpy.random.default_rng(seed) with one fixed integer seed. Rewrite: rng = numpy.random.default_rng(7).
[clock] No current time: besides .now / .today / .utcnow, no "now" or "today" text given to Timestamp, Period or datetime64. Rewrite: take dates from the task text.
[sympify] No sympy parsing of text: no S("..."), sympify, parse_expr or lambdify. Rewrite: build expressions from sympy.Symbol and numbers.
[dunder_string] No string literal may contain a word wrapped in double underscores, such as "__main__". Rewrite: drop the text or write it without the underscores.
[meta_option] The file, comments included, must not contain "stronger result", "stronger statement" or any four consecutive words of "one of the remaining options is correct but a stronger result can be proven". Rewrite: delete the sentence; describe what the program computes instead.
[bulletin_literal] On every bench, no string literal (docstrings included) may contain: a page reference with a number ("page 12", "pp. 3"); a month name or abbreviation followed by a year 1800-2099 ("March 1985"; the word "may" counts); "treasury bulletin" followed by a digit. Rewrite: read such values from the task input at run time; in a pattern write \d+.
[receptacle_literal] On every bench, no string literal may contain one of these words followed by a number ("cabinet 1", "drawer 3"): armchair, bathtub, bathtubbasin, bed, bowl, box, cabinet, cart, coffeemachine, coffeetable, countertop, cup, desk, diningtable, drawer, dresser, fridge, garbagecan, handtowelholder, laundryhamper, microwave, mug, ottoman, paintinghanger, pan, plate, pot, safe, shelf, sidetable, sinkbasin, sofa, stoveburner, toaster, toilet, toiletpaperhanger, towelholder, tvstand. Rewrite: take object names from the observation or the admissible commands at run time.
```

Block 2, the bench-dependent parts of the other three benches:

```text
[zebralogic] "none of" list: before_call. Smallest returns: before_call -> {}. Hook lines after "applies":
before_call(view, state) -> a notes dict or None. view = {"question", "columns"}; state is always None. Read the puzzle's own clues and compute constraints the solver can use.
[spreadsheetbench] "none of" list: before_call, sheet_feedback. Smallest returns: before_call -> {}; sheet_feedback -> {"fields": {}, "request_repair": False}. Added to the entry sentence: "requests_second_call": true only if sheet_feedback may ask for a repair. Hook lines after "applies":
The view is {"instruction", "workbook_preview", "input_path", "required_output_path", "required_answer_position"}.
before_call(view, state) -> a notes dict or None; state is always None.
sheet_feedback(view, run_report, state) -> {"fields": notes dict, "request_repair": bool}. run_report = {"status", "exc_type", "message", "answer_cells"} comes from one run of the solver's code on the public input workbook; it holds no reference workbook and no grading result, and the program never sees the solver's code. request_repair asks for at most one repair attempt by the solver and counts only when the entry declares "requests_second_call": true.
[alfworld] "none of" list: alf_before_step. Smallest returns: alf_before_step -> {"fields": {}, "discourage": []}. Added to the entry sentence: "state_bytes": the largest state alf_after_step returns, 1 to 65536 bytes of JSON (left out or 0 means 65536). Hook lines after "applies":
applies reads view = {"initial_observation", "admissible_commands_at_reset", "task_text"}.
alf_before_step(view, state) -> {"fields": notes dict, "discourage": [admissible commands to advise against]}. view = {"initial_observation", "observation", "admissible_commands", "recent_history"}.
alf_after_step(event, state) -> the new state (plain JSON data). event = {"step", "action", "observation", "admissible_commands"}. state is None until alf_after_step first returns a value. Module globals are reset between calls: keep memory in state only. On this bench the notes of one step are limited to 1500 characters in all; a longer note is skipped. The first fault switches the program off for the rest of the episode.
```

Block 3, purpose `fix`: the first three paragraphs become these; HOOKS, NOTES, CONTENT and STATIC SCREEN are unchanged.
The entry list ends with `, "requests_second_call"` on spreadsheetbench and `, "state_bytes"` on alfworld.

```text
A helper program you wrote for a solver model on searchqa tasks was rejected by a check before it could be tested. Correct it. Keep what the program does; change only what the check requires. You get this one correction.

WHAT YOU RECEIVE (user message, JSON). change: the entry of the rejected program. failed_source: its full text. failed.check: which check failed ("policy" = the static screen below; "hooks" = no usable hook function is defined; "structure" = the entry and the hooks do not fit together; "source" = no program text was found). Each row of failed.detail gives: rule (the name used in the screen rules below), line and source_line (where; line 0 = the file as a whole), detail (what the checker saw), rule_text (the rule in words) and rewrite (the standard legal form). failed.more counts violations not shown.

WHAT YOU RETURN. Reply with one fenced json block holding {"changes": [<the one corrected entry>]} and then one fenced python block with the complete corrected program. Put no program text inside the JSON.
Apply the rewrite on every listed line. Then read the whole program once more against every rule of the static screen: a rejected program often breaks the same rule in other places. Return the complete corrected program, not a patch, with the same entry fields ("kind": "new", "description", "hooks", "header", "max_note_chars").
```

### 1.6 What is kept from the old prompt, and why

Kept because code reads it: (1) the reply contract (one json fence with `changes`, one python fence per change in
order, no program text in the JSON), read by `T/replies.py` over the frozen `X/engineer_reader.py:397`; (2) the entry
keys and types (`X/engineer.py:164-166`, read at `W:365-372`) and kind `new` only (`W:495-498`); (3) the hook names
as top-level functions (`X/protocol.py:222`, `X/engineer_reader.py:299`) with their parameter counts
(`X/package.py:39-40`); (4) the limits: 24,000 bytes, 2,000 characters per constant, description 600, header 200,
note cap 4,000 (ALFWorld 1,500 per step), state 65,536 bytes, 3 changes (`X/protocol.py:427`); (5) note field names
and caps (`X/notes.py:43-49` [V]), the fault rule (a bad field suppresses the whole note, `X/notes.py:277-291`,
`X/solver.py:361`; a note over its declared cap or over the bench total is skipped, `X/notes.py:419-439` [V]),
return shapes per hook, `requests_second_call` only with a second-call hook (`X/package.py:42`, `W:390-392`);
(6) the payload keys the text names: `task_card`, `format_block`, `skill_index`, `trajectories`, `hook_views`
(`W:352-355` [V], not edited).
Dropped as stale (no typed code reads it): configuration names (main-v4, zebra-pc-v8, alfworld-v5), J1..J7 and
thresholds, adoption / confirmation, replay tests and `claims_fix`, revision / deletion / narrowing kinds,
`excluded_benches`, inert-repair and fault-repair calls, two-reviewer audits, the Main-v7 / Main-v9 paragraphs.

## 2. Change list

| # | File and site today | Change | New names / signatures |
|---|---|---|---|
| 1 | `T/engineer_prompt.py` (NEW) | prompt parts, rule table, pins, evidence, self-check | `PROMPT_VERSION = 'typed-engineer-prompt-1'`, `PURPOSES`, `RULES`, `NOTE_HOOKS_BY_BENCH`, `CHECK_WORDS`, `EVIDENCE_ROWS = 8`, `SOURCE_LINE_CHARS = 240`, `PINS`, `system(bench, purpose) -> str`, `rule_key_for(rule, detail, source_line) -> str`, `screen_evidence(failed, source, bench) -> dict`, `verify() -> dict` |
| 2 | `T/__init__.py:43` | add next to `MAX_PROGRAM_CANDIDATES` | `MAX_PROGRAM_PROPOSALS = 3` |
| 3 | `W:29-30` imports | add `MAX_PROGRAM_PROPOSALS`, `engineer_prompt` | import order `replies` <- `engineer_prompt` <- `writers` |
| 4 | `W:40`, `W:299-307` | delete `ALFWORLD_PROMPTS`, `alfworld_prompt_configuration` (callers only `W:301`, `W:314`, `tests/test_typed_writers.py:317` [V, grep]) | none |
| 5 | `W:310-315` `engineer_system` | body becomes `return engineer_prompt.system(bench, purpose)` | signature unchanged |
| 6 | `W:387` in `_bounded_entry` | statement 16 | none |
| 7 | `W:396-415` `build_procedure` | hooks check after `W:404` (statement 17) | failure `{'check': 'hooks', 'detail': [{'rule': 'no_hook_function', 'line': 0, 'detail': 'defined: ...'}], 'repairs'}` |
| 8 | `W:436-439` `_row` | keys `n`, `status`, `slot`, `first_screen` (reply area adds `read`, `format_retry`) | `PROPOSAL_STATUS` (six names of statement 11) |
| 9 | `W:442-466` `_fix_once` | `W:446` new user message; keyword `budget`; record gains `screen_evidence` (the reading at `W:452-461` belongs to reply.md) | `_fix_once(..., n, budget)` |
| 10 | `W:469-515` `propose_programs` | memoised `verify()`; one `RetryBudget`; the loop of 1.3 replaces `W:499-502` and `W:505-514` | signature unchanged |
| 11 | `T/chain.py:871-872` | iterate every row: slot rows call `self.program(..., slot, proposal, snapshot)`; `dropped_screen` / `unreadable` / `kind_not_new` rows call `self.program_decision(..., None, None, proposal, snapshot)`, which returns at the guard `T/chain.py:892-893`; `not_needed` rows are skipped | none |
| 12 | `T/chain.py:888-891` `base` | add `'proposal': proposal.get('n')`, `'status': proposal.get('status')` | none |
| 13 | `T/smoke.py:36-41,180` | scripted writer: proposal 1 fails the screen and its fix, proposal 2 passes into slot 1 (shared with reply.md's scripted retry) | second scripted reply |
| 14 | `T/readout.py:174-185` `_decision_row` | optional: copy `status`, `proposal`, `candidate` into program rows | none |
| 15 | `docs/current-workflow.md`, typed-v2 DESIGN | describe the program stage as in section 1 | none |

Not edited by this area: `W:349-356` `program_payload`, `W:57-72`, `W:416-418`, `W:429-433`, `T/chain.py:860-865`,
`T/gates.py`, `DEFAULT_LIMITS` (`T/chain.py:61`) and `SMOKE_LIMITS` (`T/smoke.py:28`): no new limits key.

## 3. Records and identity

- `proposals.json` rows (reply order). typed-v1 keys stay: `procedure`, `entry`, `source`, `kind`, `screen: {passed,
  reason}`, `request_sha256`, `repairs`, `fix` (`W:436-439` [V]). New: `n` (position in the reply), `status`, `slot` (1,
  2 or null), `first_screen` = `{'passed', 'check', 'rules': [checker ids]}` for every screened row, else null.
  Promoted row: `status` `passed` / `passed_after_fix`, `slot` set, `procedure` set, `screen.reason` null. Dropped
  row: `status` `dropped_screen`, `slot` null, `procedure` null, `screen.reason` `'<check>: ... | fix: ...'`, `fix`
  set. `unreadable`: `screen.reason` `'unparseable: <code>: <detail>'` (reply.md), `fix` null. `not_needed`:
  `screen.reason` `'not_needed'` (replaces `'over_max_candidates'`, `W:500`), `fix` null.
- `fix` record: typed-v1 keys `request_sha256`, `parsed`, `reason`, then `entry`, `source`, `repairs` (`W:448-462`
  [V]); new `screen_evidence` = `{'rows': [{'rule', 'key', 'line', 'detail', 'source_line'}], 'more'}` (the words
  follow from `key` and `PROMPT_VERSION`). `procedure.lineage.engineer_call` of a `passed_after_fix` row is the call
  whose reply gave the final source (`W:463-465` [V]; under reply.md possibly the retry call).
- `decisions.json` `programs`: one row per slot candidate as in typed-v1 (`candidate` = slot, `unit` =
  `s<k>/program-<slot>`) plus one zero-call row per `dropped_screen` / `unreadable` / `kind_not_new` proposal
  (`candidate` and `unit` null, `accepted` false, `reason` `'screen:' + screen.reason`, no unit directory); every row
  gains `proposal` and `status`. `not_needed` rows get none, as the surplus proposal got none in typed-v1.
- Ledger: no new field; at most two more `program_writer` calls per programs unit through the same recorder
  (`T/chain.py:864` [V]). Manifest: `engineer_prompt: {'version', 'pins'}` is offered to the identity area. Readout:
  reads `decisions.json` only [V, grep], so the zero-call rows appear without an edit; change 14 is optional.
- Requests that change against typed-v1: all ten engineer system texts, hence every proposal and fix request hash
  (`request_sha256` hashes system and user, `W:57-59` [V]); the fix user message (statement 7).
- Byte-identical to typed-v1: the proposal user message for equal inputs (`program_payload` is not edited),
  `request_sha256` itself, `POLICY_VERSION` (`W:37`), the `Procedure` construction (`W:406-412`). This area touches no
  solver, card, describer or typing request.
- Pins: typed-v1 has no 64-hex engineer pin (identity.md; it held the text only by equality at
  `tests/test_typed_writers.py:237,279` [V]). typed-v2 adds ten, one per bench and purpose, computed once the reply
  area has fixed the `REPLY_FORMAT` wording and question 1 is answered. The draft of 1.5 renders at 10,076
  (zebralogic, fix) to 11,216 (alfworld, propose) characters.

## 4. Tests

One legal and one illegal example per row, all executed here against the screen at `POLICY_VERSION` with no bench:
22 rows, 0 mismatches [V]. Each example is this line inside (or above) a module that defines `before_call`. The
`statement` example also reports `module_level`, so the test asks for the row's id among the violations.

| row key | checker id | illegal (rejected with that id) | legal (no violation) |
|---|---|---|---|
| `size` | `size` | the module plus one comment line of 24,000 characters | the module alone |
| `syntax` | `syntax` | `return {"facts": [}` | `return {"facts": []}` |
| `top_level` | `module_level` | `LIMIT = 3` / `if LIMIT > 2: LIMIT = 2` | `LIMIT = 3` |
| `constant_value` | `module_level` | `WORDS = {w.lower() for w in ("Alpha", "Beta")}` | `WORDS = {"alpha", "beta"}` |
| `constant_word_set` | `module_level` | `WORDS = frozenset("alpha beta".split())` | `WORDS = frozenset({"alpha", "beta"})` |
| `constant_regex` | `module_level` | `UNIT = "kg"` / `PAT = re.compile(r"(\d+)\s*" + UNIT)` | `PAT = re.compile(r"(\d+)\s*" r"(kg)")` |
| `constant_other` | `module_level` | `SEP = ", ".join(sorted(["b", "a"]))` | the same line inside the function |
| `constant_size` | `constant_size` | `BIG = "..."` with 2,100 characters | `BIG = "..."` with 1,900 characters |
| `statement` | `statement` | `class Box: pass` | `def box(): return {}` |
| `decorator` | `decorator` | `@functools.lru_cache(maxsize=None)` above `def helper(x)` | `def helper(x): return x` |
| `import` | `import` | `from typing import List` | `from datetime import datetime` |
| `name` | `name` | `found = hasattr(view, "question")` | `found = "question" in view` |
| `attribute` | `attribute` | `value = view._cache` | `value = view.get("cache")` |
| `attribute_type_name` | `attribute` | `except Exception as e: kind = type(e).__name__` | `except ValueError: kind = "ValueError"` |
| `attribute_data` | `attribute` | `rows = view.to_dict()` | `rows = dict(view)` |
| `numpy_random` | `numpy_random` | `rng = np.random.default_rng()` | `rng = np.random.default_rng(7)` |
| `clock` | `clock` | `t = pd.Timestamp("now")` | `t = pd.Timestamp("2020-01-01")` |
| `sympify` | `sympify` | `e = sympy.S("x+1")` | `e = sympy.Symbol("x") + 1` |
| `dunder_string` | `dunder_string` | `k = "__main__"` | `k = "main"` |
| `meta_option` | `meta_option` | `# of the remaining options` | `# among the options given` |
| `bulletin_literal` | `bulletin_literal` | `s = "see page 12"` | `s = "see the page named in the question"` |
| `receptacle_literal` | `receptacle_literal` | `s = "open drawer 3"` | `s = "open the drawer"` |

New, in `tests/test_typed_engineer_prompt.py`:
- `test_rule_examples_match_screen` (per row): legal gives `[]`; illegal gives a violation with the row's checker
  id, which `rule_key_for` maps back to the row (for the two parent rows: to one of their rewrite rows).
- `test_every_screen_rule_is_stated`: rule ids of `RULES` equal `set(policy.RULES)`; every STATIC SCREEN line of each
  text comes from a row; every row except the two parents has a rewrite.
- `test_rendered_lists_are_the_bound_lists`: each element of the five `policy` lists and each limit of statement 3 is
  in the text; changing a constant under monkeypatch changes the rendered text.
- `test_pins`: the ten sha256 equal `PINS`; `verify()` passes; a one-character edit makes it raise.
- `test_reply_format_embedded`: `replies.REPLY_FORMAT[purpose]` is contained in every text (asked by reply.md).
- `test_hook_signatures`: parameter counts in the text equal `package.HOOK_PARAMETERS`; `NOTE_HOOKS_BY_BENCH` values
  are inside `package.NOTE_HOOKS`; every hook named in a text is in `protocol.HOOKS`.
- `test_no_stale_route_b_text`: no `J1`..`J7`, `replay`, `claims_fix`, `main-v`, `zebra-pc`, `excluded_benches`.
- `test_rule_key_for`: the three F6 sources map to `constant_word_set`, `constant_regex`, `attribute_type_name`.
- `test_screen_evidence`: 10 violations give 8 rows and `more == 2`; `source_line` is the stripped line; line 0
  gives null; `rule_text` / `rewrite` are substrings of the system text; checks `hooks` and `structure` give one row.
New, in `tests/test_typed_writers.py`:
- `test_fix_request_carries_evidence`: key set `{request, bench, change, failed_source, failed}`; no `source` in
  `change`; the system text is the pinned fix text.
- `test_promotion` (scripted replies): (a) pass, pass, third gives `passed, passed, not_needed`, 1 call; (b) fail and
  failed fix, pass, pass gives `dropped_screen`, slot 1, slot 2, 2 calls; (c) fail then good fix gives
  `passed_after_fix`; (d) three failures give no slot and 4 calls; (e) an unreadable first record gets no fix call
  and the second takes slot 1; (f) `max_candidates=1`; (g) a dropped proposal keeps ordinal 1, the next gets 2;
  (h) the same `RetryBudget` object reaches every read; (i) `MAX_PROGRAM_PROPOSALS == profiles.MAX_CHANGES`.
- `test_bounded_entry_defaults` (statement 16) and `test_no_hook_function` (statement 17, per bench, with the fix).
New, in `tests/test_typed_chain.py`: `test_slot_rows_run_units_other_rows_get_zero_call_decisions` (no `program-3`
unit; a step with no slot has decisions that explain every proposal).
Fresh interpreter under `bind_machinery` (pattern `tests/test_typed_cli.py:80-105` [V]):
`test_engineer_prompt_under_bound_machinery`. The snapshot is a copy of this tree's `skillopt/` without
`execskill/typed/` (equal to the dl snapshot by F2). The child asserts `policy.__file__` is under the snapshot and
`engineer_prompt.__file__` under the tree, then runs `engineer_prompt.verify()`, `build_procedure` plus
`screen_evidence` on the three F6 sources, `_bounded_entry` defaults, and promotion case (b) with scripted calls. On
dl the same test also runs against `/data/execskill-code-20261109-main-v10` when that directory exists.
Existing tests that must change:
- `tests/test_typed_writers.py:237`, `:279`: the system text equals `engineer_prompt.system(...)`, not
  `profiles.engineer_prompt(...)`. `:283`: the key set gains `failed_source` (`:281-282` and `:291` still hold).
- `tests/test_typed_writers.py:297-311`: `:304` `'over_max_candidates'` becomes status and reason `not_needed`.
- `tests/test_typed_writers.py:315-338`: the ALFWorld prompt-family test goes (`:317` calls the deleted function).
- `tests/test_typed_writers.py:340-350`: stays (`:346`, 99,999 gives 4,000); extended by the defaults test.
- `tests/test_typed_chain.py:105-113`, `:537-550`: fake proposal rows need `n`, `status`, `slot`. `:263-270`: a
  failed screen gives a zero-call decision with `unit` null and no `program-1` directory.
- `tests/test_typed_e2e.py:201-210`, `:230`, `:245-246`: assert `slot`; the lineage hash may be a fix or retry call.

## 5. Interfaces to other areas

- Reply (`spec/reply.md`). Its four needs are met: (a) `test_reply_format_embedded`; (b) statement 11; (c) the one
  `budget` goes to every fix read; (d) `failed_source`. I need: `read_with_retry` for `propose` returning at most 3
  records in reply order, each with `n`, `kind`, `entry`, `source`, `problem`; `read_fix` returning one record or a
  problem; `outcome['request_sha256']` as the lineage call; the final `REPLY_FORMAT` wording before the pins are
  computed; `replies` importing neither `writers` nor `engineer_prompt`. A reply that stays unreadable as a whole
  gives the single row reply.md defines at `W:483-487`, with `status` `unreadable`.
- Identity (`spec/identity.md`). Offered: `PROMPT_VERSION`, `PINS`, `verify()`. Asked: the zero-call run-start check
  calls `engineer_prompt.verify()` under the bound snapshot, and the manifest sealed at `prepare` records the pins.
- Gate (`spec/gate.md`). Its sentence "the gate takes `proposals[:max_program_candidates]` as today" must read "the
  rows with a slot" (change 11). Unit names `program-<i>-smoke` / `program-<i>-gate` and the two-candidate maximum
  are unchanged; `program_decision` `base` gains two keys (change 12) in a function the gate area also edits.
- Smoke: change 13 and reply.md's scripted unreadable reply fit one `s1/programs` unit (retry, failed fix, promotion).
- Card, schedule and lock areas: none. `proposals.json` is written once inside the learning step.

## 6. Risks and open questions for the coordinator

1. Entry-point check (statement 17)? Recommended: yes. An inert program counts as fired on every item
   (`T/mount.py:114-120` [V]) and would cost a smoke unit and a full gate arm (three runs per item under D5). The
   per-bench list is the route-B registrar's (`X/engineer.py:2359-2361`). If no new rejection is wanted, drop
   change 7 and write "and is useless" for "and is rejected" in the HOOKS paragraph.
2. Fix request shape (statements 7 and 8: `failed_source`, up to 8 rows with words and rewrite)? Recommended: yes.
3. Decision rows (changes 11 and 12: zero-call rows for dropped proposals, none for `not_needed`)? Recommended: yes;
   otherwise a step whose proposals all fail the screen shows no program row at all in the readout.
4. Screen `not_needed` proposals once for the record (`first_screen`), so that the first-try pass rate over all
   proposals measures D3 against typed-v1's 8 of 12? Recommended: yes; it costs no call.
5. The literal bans without a bench (section 0)? Recommended: keep the call, tell the model (done in the text).
   Passing `bench=` would change what the screen accepts, which D1 and F5 rule out.
Risks: the text is 10,076 to 11,216 characters (old: 9,619; ALFWorld 4,436); an interruption inside the programs
unit repeats up to 5 calls instead of 3 (`T/chain.py:316-323` writes the record once [V]); a long rule list may make
programs more timid, which only the first-try pass rate and the gate can show.

## NOT DONE

- The ALFWorld sentences (module globals reset between calls, state `None` at first, first fault disables the
  program for the episode) and "state is always None" for `before_call` come from the route-B prompt texts; they are
  not re-read in the sandbox worker (`X/sandbox/worker_v222.py`).
- Whether the `replies` normalisation fills the same defaults as the frozen `read` (reply.md marks it [I]).
- No pin is fixed and no test of the tree was run. `T/engineer_prompt.py` exists only as a scratch draft outside the
  tree, from which the blocks of 1.5 were rendered and the 22 example pairs executed; `screen_evidence`, `verify`
  and the promotion loop are specified here but not drafted.
