# coevo5 method roles -- what route B keeps conceptually

Status: COMPLETE (sections 1-6 written; later edits only add detail).
Author: read-only code-reader subagent, 2026-10-21. Area: method roles of skillopt/coevo5 (step, examiner, analyst,
research, forward, gate, texts, report, readout, roles) + task-card seed texts.
Convention: "verified" = read in the cited lines; "inferred" = my reading, not executed. All paths repo-relative to
/Users/dulin/Documents/Paper/SkillOpt unless absolute (dl paths are on the Linux machine `dl`).
Protocol in code: `skillopt/coevo5/protocol.py:10` VERSION = "fivebench-coevolution-v3" (registration v6 as changed
by the v2 and v3 deltas, protocol.py:1-5). Note `skillopt/coevo5/__init__.py:8` still says
"fivebench-coevolution-v1" (stale package docstring constant; protocol.VERSION is the one used, inferred).

## 1. Scope and files read (line counts from `wc -l`)

| file | lines | read |
|---|---|---|
| skillopt/coevo5/roles.py | 142 | full |
| skillopt/coevo5/step.py | 861 | full |
| skillopt/coevo5/examiner.py | 516 | full |
| skillopt/coevo5/analyst.py | 276 | full |
| skillopt/coevo5/research.py | 702 | full except HTML parser internals 242-312 |
| skillopt/coevo5/forward.py | 443 | full |
| skillopt/coevo5/gate.py | 241 | full |
| skillopt/coevo5/stats.py | 74 | full |
| skillopt/coevo5/texts.py | 183 | full |
| skillopt/coevo5/skill.py | 136 | full |
| skillopt/coevo5/protocol.py | 357 | full |
| skillopt/coevo5/prelaunch.py | 545 | 1-78, 255-412 (texts prep/import/verify) |
| scripts/run_coevo5.py | 311 | full |
(further files appended below as read)

| skillopt/coevo5/leakage.py | 291 | full |
| skillopt/coevo5/checks.py | 105 | full |
| skillopt/coevo5/readout.py | 396 | full |
| skillopt/coevo5/report.py | 732 | 1-60, 134-260 (updates, gate funnel, examiner description) |
| skillopt/coevo5/cells.py | 263 | 1-48, 84-87, 166-263 |
| skillopt/coevo5/units.py | 157 | 37-157 |
| skillopt/coevo5/chain.py | 314 | 70-86 (chain start) |
| skillopt/coevo5/smoke.py | 435 | 60-80, 218-272 (smoke-paths) |
| skillopt/continual_eval/backends.py | (large) | 30-60, 355-400, 724-740 (solver prompt + contracts) |
| docs/handoff/coevo5-registration-v6-20261017.md | 1120 | §4-§9 (lines 151-488) skimmed to confirm code |
| docs/project-status.md, docs/results-and-lessons.md | -- | grep hits only (v3 funnel, smoke 4/9, cal-1) |

dl (read-only, `ls`/`python3 -c` json reads only):
- /data/coevo5-20261019-v3-pre/texts/texts.json (v3 imported texts; instructions, cards, rubrics)
- /data/coevo5-20261019-v3-pre/smoke-3/I-ds/s1/smoke-paths/unit.json and attempt-1/forward.json (the 4/9 panel)
- /data/coevo5-20261019-v3-run/{I-ds,E-ds}/s{1..5}/{prepare,selftest,screen,confirm}/unit.json (training-side unit
  results only; nothing under evaluation/ or shared/ was opened)
- /data/coevo5-20261019-v3-run-manifest.json (keys `tolerance`, `regression` sizes only)

## 2. Facts

### 2.1 Role-call infrastructure (roles.py)
- F1 (verified) Every method role is GLM-5.3, reasoning low, temperature 0, behind the unit attempt's call wrapper
  `calls.Endpoint` (roles.py:3-6; protocol.py:30-32 `ROLE_MODEL = "glm-5.3"`, `ROLE_MAX_TOKENS = 16384`,
  `ROLE_READ_TIMEOUT_SECONDS = 900`).
- F2 (verified) Reply contract: the whole reply, or the whole reply inside one ```json fence, must be ONE JSON object
  (`FENCE`, `parse`, roles.py:21, 29-43). Anything else -> `Invalid("not_json" | "not_an_object" | "no_text")`.
- F3 (verified) `Roles.ask(role, system, user, *, label, check=None)` (roles.py:92-117): `user` is sent as
  `json.dumps(user, ensure_ascii=False, sort_keys=True)`; every call appends a record `{"role", "label",
  "request_sha256", "sends", "valid", "reason"}` to `Roles.calls`; returns the validated value or `None`.
  `None` when receipt `ok` is not True or `finish_reason != "stop"` (reason `"no_reply:<error_type|finish_reason>"`),
  or when `parse`/`check` raises `Invalid|ValueError|TypeError|KeyError` (reason `"invalid:..."`).
  `recorder.invalid` -> raises `ConfigurationError("invalid_model_receipt")` (a stop, not an invalid reply).
  Stops of the run (budget, ledger, reservation) propagate as exceptions from `recorder(system, message)` (roles.py:102).
- F4 (verified) `Roles.plain(...)` is the plain-text variant used only by the pre-launch instruction writer
  (roles.py:119-138). `Roles.count(prefix)` counts calls by label prefix (roles.py:140-142).
- F5 (verified) Validator helpers: `fields(value, required, optional=())` exact key set (roles.py:46-50);
  `text(value, *, limit, empty=False)` (53-56); `items(value, *, limit, low=0)` list length (78-81);
  `fit(user, key, budget)` drops the LAST entries of `user[key]` until the UTF-8 JSON is <= budget, records
  `user[key+"_omitted"]`, raises `ValueError` if the fixed fields alone exceed it (64-75). Budget used everywhere:
  `ROLE_INPUT_BYTES = 220000` (protocol.py:245).
- F6 (verified) Each prepare/selftest unit writes the role-call record to `attempt/roles.json` in a `finally`
  (step.py:398-399, 606-607).

### 2.2 The step (step.py) -- unit order and what each unit records
- F7 (verified) `learn(setting, chain_root, chain, stage, parent)` (step.py:830-861) runs, in order:
  `train` -> `prepare` -> `selftest` (only if some rule is "supported") -> `screen` (only if supported rules remain)
  -> `confirm` (only if some tentative placement) -> `composite` (only if the size-fitting subset has >= 2 rules)
  -> `merge` (always). Returns `(Skill.from_json(merged["result"]["skill"]), merged)`. Each unit is a
  `units.run_unit(unit_root, run=, identity=, work=)` (units.py:126-157): idempotent (a complete `unit.json` with the
  same run+identity is returned as is), new `attempt-N` dir per try, `Pause` on stops; identity =
  `{"unit": "<chain>/s<k>/<name>", "chain", "stage", "benchmark": ORDER[stage-1], "parent_sha256", "after": <record
  hash of the unit before>}` (step.py:99-101).
- F8 (verified) `train` (step.py:197-212): parent Skill on the stage's training draw
  `training_items(pool, bench, DATA_SEED, size=setting.extra["draw"][bench])`, `TRAIN_ROLLOUT[bench][1]` runs per item
  (protocol.py:60-61: searchqa (200,2), officeqa (74,2), livemath (100,2), spreadsheetbench (120,1), alfworld (57,2)).
  Result: `{"cells": {item: [cell ids]}, "tokens": {item: [final tokens]}}`. Guard: parent >10% infrastructure-unknown
  -> `Pause("infrastructure_incomplete")` (step.py:150-157; `MAX_UNKNOWN_SHARE = 1/10`, protocol.py:84).
- F9 (verified) `halves(tokens, *, chain, stage)` (step.py:216-225): split items into "proposal"/"check", stratified
  by "failed at least once"; within each stratum the first ceil(n/2) of a sha256 seeded order propose. Re-drawn every
  step; no fixed validation partition (registration §4 step 2, lines 154-156).
- F10 (verified) `answers(...)`/`answer_of(...)` (step.py:228-254) produce the per-cell "answer" dict every role reads:
  `{"key", "item", "benchmark", "completion" (cell token), "official" ("pass"|"fail"|"unknown"), "kind",
  "output", "public", "private", "trace", "cases", "sheet_cells", "run", "half"}`. NOTE: it carries `private`
  (the reference) -- the role decides what to show.
- F11 (verified) `prepare` (step.py:320-401) order: halves -> `examiner.revise` (writes revision.json) ->
  `examiner.diagnose` on ALL failures of both halves (diagnoses.json) -> SpreadsheetBench `panel_insufficient` if the
  qualified pool < `SHEET_MIN_QUALIFIED = 30` -> `analyst.payload` + `analyst.propose` -> evidence-invalid rows recorded
  never tested -> `analyst.deduplicated` -> per proposal `_research` (pre-dispatch leak check, verify requests,
  rewrite; research.json) -> dedup again -> per kept proposal `_admissible` (leak + adjudication + own-placement
  length) and trigger set `T_r` = check-half items with a failed answer whose diagnosis code is in the rule's codes;
  `len(T_r) < MIN_TRIGGER (=4)` -> "insufficient_support" (step.py:386-389; protocol.py:81).
  Result keys: `halves, revision, rubric, analyst, rules, supported, duplicates, answer_values, status="prepared"`.
- F12 (verified) Rule status vocabulary produced in prepare/selftest: `invalid` (row failed validation),
  `evidence_invalid`, `duplicate`, `duplicate_after_rewrite`, `dropped_pre_dispatch`, `leak_mechanical`,
  `leak_adjudicated`, `leak_adjudicated_word`, `overlength`, `insufficient_support`, `supported`, then (selftest)
  `selftest_failed`, `selftest_dropped`, `revision_duplicate`, `revision_<leak/overlength>`; similar candidates also
  get `similar_status` in {`forward_panel_short`, `similar_overlength`, `similar_candidate`} (step.py:359-393, 545-600).
- F13 (verified) `selftest` (step.py:496-609; v3 §7): round 1 = every supported rule (own placement) on its own
  PROPOSAL-half evidence items x `SELFTEST_RUNS` (2/2/2/1/1, protocol.py:249) plus the parent on their union; pass iff
  `Sum L(rule) > Sum H(parent)` and rule unknown share <= 1/10 (`_passes`, step.py:461-465). Failing rules get ONE
  batch revision call (`SELFTEST_SYSTEM`, step.py:405-416; <= `SELFTEST_ATTEMPTS = 2`, the second only after an
  invalid reply; payload shows <= `SELFTEST_SHOWN = 3` evidence items per rule with answers and reference); revised
  texts re-pass dedup + `_admissible`, then round 2 against the parent's round-1 table. Then forward panels for
  similar candidates (`_forward`). Writes selftest.json; its unit record is the plan every later unit reads
  (`plan_path`, step.py:625-628).

### 2.3 Analyst (analyst.py)
- F14 (verified) Purpose (system prompt `ANALYST_SYSTEM`, analyst.py:59-85): propose <= 5 new rules for the section
  being improved; one short general instruction each (<= 600 chars, no headings/blank lines); never a fact about one
  task, never steer by answer distribution, may depend only on what the solver sees; cite 2-8 shown failures as
  evidence; `covered` / `adds`; optional similar placement and transfer slot; <= 2 research questions per rule.
- F15 (verified) Input payload (`payload(benchmark, *, parent_text, failures, diagnoses, meanings, cards, seed, tag,
  passed=())`, analyst.py:125-153), bounded by `fit(..., "examples", ROLE_INPUT_BYTES)`:
  `{"section": TITLES[b], "applies_when": APPLIES_WHEN[b], "task_card": cards[b], "current_skill", "failures":
  {"total", "by_code"}, "codes": [{"code","meaning"}], "examples": [{"task_id","task","answer","reference","code"}],
  "correct_examples": [{"task","answer","reference"}] (<= CONTRAST_EXAMPLES=4), "similar": {"kinds": [{"section",
  "task_card"}], "checkable": [titles]}, "limits": {...}}`. Examples: round-robin over codes by count, seeded,
  <= 40 (`MAX_EXAMPLES`), OfficeQA 16 and SpreadsheetBench 20 (`ANALYST_EXAMPLES`, protocol.py:237); OfficeQA task
  view clipped at 20000 chars (`ANALYST_CONTEXT_CHARS`, protocol.py:238).
- F16 (verified) Output schema: `{"rules": [{"text", "placement": "local"|"similar", "codes": [...], "evidence":
  [task_id], "covered", "adds", "rationale", "questions": [str]}], "transfer": {"rule": int} | {"none": str}}`
  (analyst.py:81-85). Validator `_check` -> `_row` per row (analyst.py:198-246): bad row -> recorded with `row_status`
  (never tested), reply invalid only if envelope malformed or no valid row, or > `MAX_SIMILAR_RULES = 2` similar
  rows; `transfer` required only when a checkable similar target exists. Evidence check `evidence_problem`
  (analyst.py:164-178): 2-8 distinct ids, all shown, each cited item carries a targeted code, every targeted code is
  on some cited item -> else `evidence_status` reason (rule kept in record, not tested).
- F17 (verified) Call ceiling and fallback: `propose(...)` at most `ANALYST_ATTEMPTS = 2` calls; two invalid replies
  -> `{"status": "method_failure", "proposals": []}` (analyst.py:249-262; protocol.py:33). Proposal ids are
  `"s<stage>-r<n>"` by reply position (analyst.py:260). Dedup by case/whitespace-normalised text vs parent rules and
  lower-numbered proposals (`deduplicated`, analyst.py:265-276).

### 2.4 Examiner (examiner.py): what a "rubric" is, judging, revision, diagnosis
- F18 (verified) A rubric = `{"bench": <bench|"general">, "items": [{"id", "text", "check", "basis"}]}` with 1-12
  items (`MAX_ITEMS = 12`), ids `R<n>` (bench) / `G<n>` (general), text and basis <= 450 chars
  (`RUBRIC_ITEM_CHARS`), `check` = null or a host check from the fixed library (`validate_rubric`,
  examiner.py:103-121). The general rubric never changes (examiner.py:3-4). There is NO model-written code anywhere:
  "no model-written code is ever executed" (checks.py:3).
- F19 (verified) The host-check library (checks.py:73-82) -- name: params: `answer_tag_present: {}`,
  `answer_single_letter: {}`, `answer_pure_number: {"allow_percent": bool}`, `answer_no_percent: {}`,
  `answer_no_letters: {}`, `answer_max_words: {"n": int 1-50}`, `code_present: {}`. Each returns True/False/None (not
  applicable). `last_answer(output)` = text inside the LAST `<answer>...</answer>` (checks.py:12-21).
- F20 (verified) Judging (`judge`, examiner.py:235-246) never sees a reference: host checks first (first violated item
  fails the answer, `by: "check"`), else GLM-5.3 with `JUDGE_SYSTEM` (examiner.py:77-81), payload `{"task":
  task_view(...), "answer": answer_text(...), "items": text items}`; reply `{"verdict": "pass"|"fail", "violated":
  [ids]}` validated by `_judgment` (verdict pass iff violated empty; ids must be text items). Invalid reply ->
  `{"verdict": "invalid"}`. One call per judgeable answer (`judge_all`); judgeable = official in pass/fail and an
  answer text exists (examiner.py:256-258).
- F21 (verified) Revision (`revise(roles, benchmark, rubric, general, answers, *, seed, tag, label, workers)`,
  examiner.py:384-426), only on `EXAMINER_BENCHES = ORDER[:4]` (no ALFWorld; protocol.py:131):
  1. `selection_panel` (examiner.py:267-279), fixed before judging: one judgeable answer per CHECK-half item (seeded),
     then <= 20 official-pass + <= 20 official-fail (`RUBRIC_PANEL_PER_CLASS = 20`); minority < 8
     (`RUBRIC_MIN_MINORITY`) -> status `insufficient_panel`.
  2. judge every judgeable answer with the current rubric; `disagreements` = proposal-half judged validly but against
     the official result, <= 10 of each kind (examiner passed an official fail / failed an official pass),
     `RUBRIC_MAX_DISAGREEMENTS = 20` (examiner.py:287-296).
  3. ONE `revise` call (`REVISE_SYSTEM`, examiner.py:90-99; payload `{"rubric", "library", "disagreements":
     [{"task_id","task","answer","reference","official","examiner"}]}` fitted to 220000 bytes); edits
     `{"op": add|edit|remove, "id", "text", "check", "basis", "evidence"}` <= `RUBRIC_MAX_EDITS = 3`, validated one by
     one (`_edit`, `_edits`), evidence filtered to shown items; edits without evidence are skipped (`apply_edits`).
  4. Re-judge the panel with the candidate; accept iff BA gain >= `RUBRIC_MIN_BA_GAIN = 1/20` AND net correct >=
     `RUBRIC_MIN_NET = 2` (examiner.py:417-421).
  Statuses: `not_revised`, `insufficient_panel`, `no_disagreements`, `invalid_reply`, `no_valid_edits`, `accepted`,
  `rejected`. The revised rubric serves only THIS stage's diagnosis (examiner.py:9, registration §6 line 416).
- F22 (verified) Balanced accuracy (`balanced_accuracy(panel, answers, judgments)`, examiner.py:299-309):
  `(correct_pass/total_pass + correct_fail/total_fail) / 2` as an exact Fraction on the selection panel; an
  "invalid" verdict counts as wrong under either rubric; returns `(BA, correct_pass + correct_fail)`. The docstring
  states it is selection material, "no independent evidence that the examiner improved" (examiner.py:14-15).
- F23 (verified) v3 run examples (dl prepare unit.json `result.revision`): I-ds s1 SearchQA rejected BA 11/20 ->
  23/40 (correct 22 -> 23); I-ds s2 OfficeQA rejected 293/360 -> 38/45 (24 -> 24); I-ds s3 LiveMath ACCEPTED 1/2 ->
  58/85 (17 -> 25); I-ds s4 SpreadsheetBench `no_valid_edits`; s5 ALFWorld `not_revised`. E-ds s1 ACCEPTED 11/20 ->
  13/20 (22 -> 26, invalid 1 -> 2); E-ds s2 `insufficient_panel`; E-ds s3 rejected 379/760 -> 52/95; s4
  `no_valid_edits`; s5 `not_revised`.
- F24 (verified) Diagnosis (`diagnose_one`, examiner.py:481-498), one per failed answer of BOTH halves: decision-table
  kind `noncompletion`/`malformed` -> that code (`by: "table"`); else first violated fixed format check of
  `REQUIRED_FORMAT[bench]` (protocol.py:127-128) -> its name (`by: "format"`); LiveMath meta-option table codes D1/D2
  (`stronger_option_code`, examiner.py:450-466, `STRONGER_OPTION` protocol.py:222); else GLM-5.3 `DIAGNOSE_SYSTEM`
  (examiner.py:82-89) SEES THE REFERENCE (`reference(...)`, examiner.py:199-217) and picks one code from the frozen
  `TAXONOMY[bench]` D-codes (precedence), else a rubric text item, else "other"; invalid reply -> "other"
  (`by: "invalid"`). OfficeQA diagnosis context 30000 chars (`DIAGNOSE_CONTEXT_CHARS`, protocol.py:223).
- F25 (verified) `TAXONOMY` (protocol.py:146-219) is the de-facto failure-category set: SearchQA D1-D5 (extra words,
  other form, not one answer, wrong candidate, wrong kind), OfficeQA D1-D5 (wrong data, wrong method, calculation
  slip, answer form, not in document), LiveMath D1-D5 (missed/wrongly chose stronger result, weaker, stronger,
  different claim), SpreadsheetBench D1-D6 (program error, wrong target, hardcoded, wrong logic, formula semantics,
  key alignment), ALFWorld D1-D4 (wrong object, missing step, search loop, invalid actions). Code meanings for the
  analyst: `code_meanings` (examiner.py:508-516).
- F26 (verified) What a role may see of the reference (`reference`, examiner.py:199-217): SearchQA `answers`;
  OfficeQA `answer`; LiveMath `answer` + the correct option text; SpreadsheetBench `answer_position`,
  `official_cases`, answer-range `cells`; ALFWorld the last 30 trajectory steps (`TRACE_STEPS = 30`,
  `TRACE_CHARS = 300`). The judge never gets it; diagnosis, rubric reviser, analyst and self-test reviser do.

### 2.5 Research (research.py)
- F27 (verified) Two jobs only (research.py:3-9): (1) verify a rule's research questions -> conclusion with verbatim
  quotes, then ONE rewrite call; (2) real public material for forward items (a Wikipedia numeric table for
  OfficeQA style, a verbatim Wikipedia definition/theorem for LiveMath style). The researcher never sees a benchmark
  item (research.py:20-21).
- F28 (verified) Frozen sources: English Wikipedia API (`WIKIPEDIA_API`, fixed `search_params`/`page_params`,
  research.py:49, 135-142; disambiguation pages and titles containing "jeopardy" dropped, also after redirects,
  research.py:53, 348-349, 440-442) and a SHA-256-pinned archive (`Archive`, research.py:353-392: `index.json` =
  {name: {"sha256","title"}}, hash-verified on open; search = files holding >= half of the query's distinct words,
  `ARCHIVE_MIN_WORD_SHARE = 1/2`). Everything fetched is archived write-once by hash under `store/sources/`
  (`Sources.keep`, research.py:395-454). HTTP client: `httpx.Client(trust_env=False, follow_redirects=False)` with
  an explicit credential-free proxy (`Wikipedia.__init__`, research.py:149-154).
- F29 (verified) `request(roles, sources, *, purpose, question, label, rule=None)` (research.py:578-664): purpose in
  `("verify","table","definition")`; per round 3 calls (`research_query` -> `research_pick` -> `research_conclude`);
  ceilings `RESEARCH_MAX_ROUNDS = 3`, `RESEARCH_MAX_QUERIES = 3` per round, `RESEARCH_MAX_PAGES = 3`,
  `RESEARCH_MAX_CALLS = 8` (protocol.py:254-257); a round starts only if 3 calls still fit (research.py:595); an
  invalid reply consumes its call and is not retried. A "found" conclusion must have every quote verbatim
  (whitespace-normalised) in the archived page text (`verbatim`, `_qualify`, research.py:342-345, 510-530), else it is
  void and the request continues. Return: `{"purpose","question","rule","status": "found"|"none","reason",
  "conclusion","quotes","pages","calls","rounds","log", ...}`; reasons `pages_exhausted`, `calls_exhausted`,
  `researcher_none`, `rounds_exhausted`.
- F30 (verified) `rewrite(roles, rule_text, findings, *, label)` (research.py:686-702): one call (`REWRITE_CALLS = 1`,
  protocol.py:53), reply `{"text"}`; invalid or not a valid `Rule` text -> `(rule_text, "rewrite_failed")`; returns
  `"kept"` / `"rewritten"`. `material(roles, sources, *, rule_text, style, label, log=None)` (research.py:667-683)
  wraps `request` with `MATERIAL_REQUEST[style]` (research.py:114-120) and returns `{"style","source": {"title",
  "revid"},"page","table"|"quote","text"}` or None. Eligible table: 2-60 rows, 2-15 columns, >= 1 numeric cell
  (`eligible`, research.py:328-333).
- F31 (verified) `step._research` (step.py:266-290): pre-dispatch `leakage.mechanical(rule_text)`:
  `"answer_word"` alone -> rule kept but NO research ("skipped_answer_word"); any other hit -> rule
  `dropped_pre_dispatch`; each question with a mechanical hit is `not_dispatched`.

### 2.6 Forward items = today's generated tasks (forward.py)
- F32 (verified) Scope: only for a rule proposed for the SIMILAR placement, only on forward targets = similar benches
  not yet learned with a generated style; `FORWARD_STYLES = ("officeqa", "livemath")` (protocol.py:20, 23-28;
  forward.py:1-18). So only the SearchQA stage (target OfficeQA style) and the OfficeQA stage (target LiveMath style)
  can ever generate items. They are "selection material for the placement, never evidence of transfer"
  (forward.py:17-18).
- F33 (verified) Per (rule, target): <= `FORWARD_ATTEMPTS = 5` rounds; each round = 1 material request (<= 8 calls) +
  1 generation call asking `FORWARD_PER_CALL = 3` items + 1 independent check call per item passing the program's
  checks; panel = first 12 valid distinct items, "ok" iff >= 8 (`FORWARD_PANEL = (8, 12)`), else "short"
  (protocol.py:97-100; forward.py:384-443). Each forward item runs `FORWARD_RUNS = 2` times per arm in the gate.
- F34 (verified) Generation prompts `GENERATE_SYSTEM["officeqa"|"livemath"]` (forward.py:59-90) and check prompts
  `CHECK_SYSTEM` (forward.py:91-101). OfficeQA-style item fields `{"question","formula","decimals" (0-4),"answer"}`;
  LiveMath-style `{"question","options" (5 distinct exact numbers),"answer" (letter),"formula"}`. Formula language:
  `FORMULA_RULES` (forward.py:56-58): `+ - * / **`, parentheses, `abs, min, max, floor, ceil, factorial, comb, perm,
  gcd, lcm`, plain decimal literals only.
- F35 (verified) The checks every generated item must pass, in order (drop reasons `DROPS`, forward.py:53-54):
  OfficeQA style (`_office`, forward.py:278-302): `format` (fields/lengths: question <= 600, answer <= 40, formula <=
  300, decimals int 0-4) -> `formula` (`evaluate` exact rational arithmetic via a restricted `ast` walk,
  forward.py:105-203: <= 300 chars, <= 100 nodes, exponent <= 10, factorial n <= 100, comb/perm n <= 1000, values
  <= 4096 bits) -> `literal_not_in_table` (every literal must equal a table cell after `_cell` cleaning: strip, drop
  ",", one leading "$", one trailing "%", leading sign; forward.py:235-242) -> `answer_mismatch` (stated answer must
  equal `rounded(value, decimals)`, half away from zero) -> identity dedup (sha256 of NFKC-lowercased material +
  question; duplicates counted, no check call) -> independent check (`_check`, forward.py:363-380): a second call sees
  only the table and the question and writes its own formula; `check_invalid`, `check_literal_not_in_table`,
  `check_mismatch` (its rounded value must equal the reference). LiveMath style (`_live`, forward.py:320-342):
  `format` -> `options` (five distinct exact numbers) -> `formula` -> `answer_mismatch` (exactly one option equals
  the formula value and it is the stated letter) -> dedup -> check call returns yes/no (`check_rejected`).
  The public item is `{"question": q + " " + rounding sentence, "context": "Source: Wikipedia, <title> (revision
  <revid>)\n" + table text}` (OfficeQA) or `{"question","choices"}` (LiveMath); private `{"answer"}`.
- F36 (verified, dl) The "4/9" panel: v3 smoke `smoke-3`, unit `I-ds/s1/smoke-paths` (smoke.py:223-272 runs the
  forward path once on the analyst's first valid proposal when the stage never reached it), rule `s1-r1` (a SearchQA
  rule: "When the clue names a specific or derivative example ... answer with that parent entity"), target
  `officeqa`. `/data/coevo5-20261019-v3-pre/smoke-3/I-ds/s1/smoke-paths/unit.json` -> forward: `{"status": "short",
  "items": 4, "counts": {"rounds": 5, "generated": 9, "valid": 4, "duplicates": 0, "dropped":
  {"check_literal_not_in_table": 1, "check_mismatch": 2, "literal_not_in_table": 2}}}`. From attempt-1/forward.json:
  rounds 3 and 5 got NO material (material requests ended `rounds_exhausted` and `pages_exhausted`), so only 3
  generation calls x 3 = 9 items; of those, 2 failed the generator's own literal-in-table check, 1 the checker's
  literal check, 2 the checker's recomputation; 4 kept (< 8 -> "short" -> the rule could only be tested locally).
  Material pages were "List of states and territories of the United States", "The Rolling Stones discography",
  "List of national parks of the United States". Kept items were trivial and unrelated to the rule (e.g. formula
  `1 + 1 + 1 + 1 + 1 + 1 + 4 + 1`, "sum of peak positions"; `9/8` ratio), and the generator also wrote its own
  rounding sentence despite the prompt ("Round to the nearest whole number. Round your answer to the nearest whole
  number."). So 4/9 = 2 empty material rounds (cap 5 rounds) + 5/9 arithmetic-consistency drops.
  For comparison (docs/project-status.md:226, 353 as of 2026-10-21 ~17:30; the file is living and its line numbers
  drift -- grep "合格 9 道" / "10/12 道合格"): v1 GLM smoke generated 12, 9 valid; v2 smoke 10/12 valid. The 4/9
  itself is reported at project-status.md:27 and :189 (grep "9 道只").
- F37 (verified, dl) In the v3 formal run NO forward panel was ever built: every `I-ds`/`E-ds` stage plan has
  `forward: {}` for all rules and `similar_status` None (all proposals at SearchQA/OfficeQA stages were "local"; the
  one similar proposal was E-ds s3-r5 at LiveMath, whose similar targets are backward only (OfficeQA), and it
  died `insufficient_support` with 2 trigger items; dl E-ds/s3/selftest/unit.json). Same file: s3-r1 had 21
  trigger items but was `leak_adjudicated`.

### 2.7 Gate (gate.py, stats.py, step._round/screen/confirm/composite)
- F38 (verified) Cell outcome tokens `("pass","fail","unknown","unknown_artifact")`; `bounds(cells)` maps
  {(arm,item): [tokens]} -> (L, H, unknown runs, runs, infrastructure-unknown runs) with L = pass share (unknown =
  fail) and H = (pass+unknown) share (unknown = pass) (stats.py:16-28). `total(table, arm, items, side)` = exact
  Fraction sum of per-item rates (stats.py:31-37). A rule arm is judged on L, parent and controls on H
  (conservative against the rule; gate.py:5-7).
- F39 (verified) Criteria per round (`gate.verdict`, gate.py:100-128; registration §5.5 lines 283-296):
  C1 `Sum_T L(rule) - Sum_T H(parent) >= MIN_GAIN (=1)` AND `Sum_T L(rule) > max_c Sum_T H(control_c)` over the four
  same-placement controls; C2 `Sum_R L(rule) - Sum_R H(parent) >= -t_k` on the rest of the focal panel (R = focal
  minus trigger minus the rule's own proposal-half evidence items, which are "held": counted in unknown share only;
  step.py:689-693); C3 per earlier bench regression panel `delta >= -t_b` AND extra format violations (rule minus
  parent) <= `MAX_EXTRA_VIOLATIONS = 2` (gate.py:57-67; `step.violations` step.py:160-181: per item the violating
  share of its runs, a rule's unknown cells count as violations, the parent's do not); C4' (similar arm only) on every
  similar target's check panel `delta >= MIN_SIMILAR_DELTA = 0` (gate.py:83-97). Arm unknown share > 1/10 ->
  "undetermined" (never accepted, gate.py:74-80). Fewer than `MIN_TRIGGER = 4` trigger items after excluding
  shared-unanswered items -> "undetermined" (gate.py:38-41). Priority = C1 margin (+ C4' deltas for similar).
- F40 (verified) Tolerances are integers in ITEMS (sums of per-item rates), applied as `>= -t` on the paired sum
  difference: registered `TOLERANCE_FOCAL = {"searchqa": 7, "officeqa": 6, "livemath": 9, "spreadsheetbench": 9,
  "alfworld": 5}` and `TOLERANCE_REGRESSION = {"searchqa": 5, "officeqa": 6, "livemath": 8, "spreadsheetbench": 6}`
  (protocol.py:78-79; calibrated by `docs/handoff/coevo5_power_sim.py` / `_v2.py`, protocol.py:75-77); the run reads
  them from the manifest via `prelaunch.tolerances(pools)` (prelaunch.py:414-426; SpreadsheetBench recomputed by
  `data.sheet_tolerances`). v3 manifest (dl `/data/coevo5-20261019-v3-run-manifest.json`): `tolerance` =
  {searchqa 7, officeqa 6, livemath 9, spreadsheetbench 7, alfworld 5}; regression panels 60 items each for the first
  four benches with t_b 5/6/8/6, ALFWorld none. (The v6 registration table, lines 300-303, still shows t_b OfficeQA 7,
  LiveMath 9 -- superseded by v2 §5.2 per protocol.py:76-77.)
- F41 (verified) Runs per cell (`runs_plan`, step.py:184-193): focal items `GATE_RUNS` (2/2/2/1/1), trigger items
  `TRIGGER_RUNS` (4/4/4/2/2), regression items once for a rule/composite arm and `PARENT_REGRESSION_RUNS = 2` for the
  parent, forward items `FORWARD_RUNS = 2` (protocol.py:62, 72-74, 100). Controls run only on the union of the
  same-placement rules' trigger items at TRIGGER_RUNS (step.py:665-670).
- F42 (verified) Interleaving ("same-session"): `run_round(setting, attempt, endpoint, unit, arms, schedule, tasks,
  *, tag)` (step.py:105-121) builds every (arm, item, run) job of the round, shuffles them by
  `_order(range(len(jobs)), tag + ":" + unit)` (sha256 of `[DATA_SEED, tag, index]`, step.py:79-80) and runs them on
  one thread pool (`run_cells` -> `run_parallel`, `ThreadPoolExecutor(max_workers=workers)` mapping jobs in order,
  cells.py:237-263). So all arms of a round (rule arms, parent, 4 controls) are solved in one seeded-random
  interleaved stream in the same time window; each cell is keyed by `cell_id(unit, arm, task_id, run)`
  (cells.py:84-85), claimed exclusively and written once per attempt (cells.py:169-171).
- F43 (verified) Shared-unanswered mask (`shared_unanswered`, step.py:139-147): pool items on which NO arm got any
  delivered reply leave every criterion of the round (e.g. content filter); guard pauses the chain if parent or any
  control has > 10% infrastructure-unknown cells (step.py:150-157, 679).
- F44 (verified) Rounds: `screen` (PLACEBOS_SCREEN; arms local, plus similar when `rule["also"]`), tentative placement
  `gate.placement(similar, local)`; `confirm` (fresh calls, PLACEBOS_CONFIRM; `gate.confirmation_arms`), final
  `gate.final_placement` (similar if similar arm passes again; else local if local passed in both rounds);
  priority order `gate.priority`, size-capped `gate.fitting_subset(order, size, cap=MAX_SKILL_BYTES)`; `composite`
  when >= 2 (members each keep trigger gain >= 1, C2 on focal minus all members' triggers/evidence, C3, C4' panels; no
  controls); `gate.accepted(subset, status)`: whole S if composite passed else only the top rule
  (step.py:720-813; gate.py:131-213). `merge` appends exactly the tested texts (step.py:816-827).
- F45 (verified) Placebo texts (protocol.py:102-124): screen = haiku 5-7-5; hex colour `#1A2B3C`; recipe ingredients
  first; Latin inscription names. Confirm = limerick AABBA; kelvin "300 K"; chess algebraic notation; knitting
  pattern. Placed with `parent.text_with(Rule("control-<n>", text, bench, targets?))` at exactly the rule's placement,
  not bound by the 20000-byte cap (step.py:666-670; skill.py:111-114). `gate.placebo_passage` (gate.py:216-230) is a
  descriptive diagnostic: each control in turn plays "rule" vs the other three on each rule's trigger items (C1 only).
- F46 (verified, dl) v3 formal gate outcomes (screen/confirm unit.json): I-ds screen s1-r1/r2/r4 fail (C1 gains 1/2,
  3/4, 0), s3-r2 fail, s4-r2 PASS (C1 gain 1, margin 1/2) then confirm fail (gain 1/2, margin -3/2), s5-r1 fail;
  E-ds s1-r1 screen PASS (gain 7/4) then confirm fail on C2 (delta -15/2 < -7), s2 r2/r3, s3 r2/r3, s4 r4 fail.
  Placebo passage 0/12, 0/4, 0/4, 0/4, 1/4 (I-ds) and 0/16, 0/4, 0/8, 1/8, 1/4 (E-ds). No composite round ever ran.
  Funnels (docs/results-and-lessons.md:142): I-ds 24 -> 10 -> 6 -> 1 -> 0 -> 0, E-ds 25 -> 18 -> 9 -> 1 -> 0 -> 0
  (proposed -> entered -> passed self-test -> passed screen -> passed confirm -> accepted).
- F47 (verified, ledger) Placebos are not inert: cal-1 (11 texts x 200 SearchQA training items x 4 runs) measured
  control:3 -0.098 [-0.136, -0.059], control:1 -0.035, control:2 +0.036, control:4 +0.003 vs parent; re-running the
  same text moves 20% of items (docs/results-and-lessons.md:144). The overnight review attributes most of the -9.8 to
  JSON-formatted answers being scored wrong (results-and-lessons.md:146, item (6)). D8: current C1 "at least one more
  item" passes a text against ITSELF 14-17% of the time (same line, item (1)).

### 2.8 Leakage (leakage.py) -- the principle route B must keep for code
- F48 (verified) What counts as leakage (leakage.py:1-33; registration §9 lines 471-488): a rule text compared with
  every item of the stage bench's TRAINING pool (never test): mechanical checks in order `REASONS = ("shared_8gram",
  "answer_text", "answer_number", "option_text", "answer_word")` (leakage.py:62):
  (1) shares 8 consecutive normalised words with an item's task surface (question+context / options / instruction /
  ALFWorld initial observation), ignoring 8-grams present in >= 5% of items (template) (`LEAK_NGRAM = 8`,
  `LEAK_TEMPLATE_SHARE = 1/20`); (2) answer text: a >= 2-word reference as a whole-word run (mechanical drop) or a
  single-word reference of >= 5 chars as a whole word (`answer_word`, goes to the adjudicator with <= 3 colliding
  items); answer number: any number in the rule equals in absolute value an OfficeQA numeric reference with >= 3
  significant digits (years 1900-2030 exempt); LiveMath correct-option content (>= 4 non-space chars) as a
  substring. SpreadsheetBench and ALFWorld: check (1) only. Normalisation: NFKC, lower case, punctuation/symbols to
  spaces (leakage.py:93-97).
- F49 (verified) Adjudicator (`adjudicate(roles, text, *, label, colliding=None, values=None)`, leakage.py:280-291;
  prompt `ADJUDICATE_SYSTEM`, leakage.py:73-90): "yes" (drop) when the rule states a fact about one specific task, maps
  a specific kind of task to a specific answer ("when the question mentions X, answer Y"), steers by answer
  distribution ("option C is usually right"), makes advice depend on what the solver cannot see (the reference,
  correctness, a score), gives away a colliding item's answer, or copies an expected SpreadsheetBench answer-cell
  value (`answer_values`, <= 60, leakage.py:247-261). An invalid reply also drops. Reply `{"verdict": "yes"|"no",
  "reason" <= 300}`. One call per rule text (and again for each self-test revision).
- F50 (verified) Order in the step: `_admissible` (step.py:305-317): any non-`answer_word` mechanical hit ->
  `leak_mechanical`; adjudicator "yes"/invalid -> `leak_adjudicated[_word]`; then own-placement length ->
  `overlength`. The same principle is in every role prompt: analyst "may depend only on what the solver sees ...
  never on the reference answer, on whether an answer is correct, or on a score" (analyst.py:67-69), self-test
  reviser (step.py:413-415), rewrite "do not add facts about particular questions or answers" (research.py:111).
  v3 run hits: I-ds s1 one `leak_adjudicated_word` + one `dropped_pre_dispatch`; I-ds s3 one `dropped_pre_dispatch`;
  E-ds s3 one `leak_adjudicated`; E-ds s2 one `revision_leak_mechanical` (dl prepare/selftest unit.json).

### 2.9 Texts: cards, instructions (seeds), scaffold, format sentences
- F51 (verified) `texts.CARDS` (texts.py:31-96) = five PUBLIC task cards (agent/human-written descriptions: task kind,
  input, the solver's fixed instructions quoted verbatim, public metric; "never an example task, a model answer or a
  score", texts.py:4-7). They are frozen into the manifest (`"cards": texts.CARDS`, prelaunch.py:510) and archived
  as `card-<bench>.txt` in the research archive (prelaunch.py:127; dl `/data/coevo5-20261019-v3-archive/card-*.txt`).
  `texts.solver_cards(cards, runtime)` swaps the SpreadsheetBench contract quote for `backends.SHEET_CONTRACT_V2`
  under the contract-first-v2 layout (texts.py:118-129).
- F52 (verified) The five TASK-CARD INSTRUCTIONS (chain I's seeds) are GLM-5.3 zero-shot Skill texts written from
  the cards by `INSTRUCTION_SYSTEM` (texts.py:22-30, verbatim from scripts/generate_zero_shot_skill.py; user message
  `"Public task card:\n\n" + CARDS[bench]`, texts.py:132-135). SearchQA/OfficeQA/LiveMath are EXISTING generations
  (`EXISTING`, `EXISTING_VERSIONS`, prelaunch.py:71-77; dirs `/root/fivebench-g-20261012-searchqa-bzero2`,
  `/root/fivebench-g-20261013-officeqa-bzero`, `/root/fivebench-g-20261013-livemath-bzero` per the dl texts record);
  SpreadsheetBench and ALFWorld were written once each (`WRITTEN`, prelaunch.py:78, 295-301; labels
  `pre/instruction/<bench>`). v1 texts (`/data/coevo5-20261017-pre/texts-2/texts.json`, version
  `fivebench-coevolution-v1-texts`) were imported unchanged into v2/v3 by `import-texts` (prelaunch.py:354-370);
  v3 record `/data/coevo5-20261019-v3-pre/texts/texts.json`, version `fivebench-coevolution-v3-texts-import`.
  `verify_texts` re-derives them from recorded replies (prelaunch.py:337-410).
- F53 (verified) Chain starts (chain.py:73-82): I = `Skill.seeded(setting.instructions)` (each instruction passed
  through `seed_text`, headings demoted, at the top of its section); E = `Skill(scaffold=True)` (every section's
  `## <Title>` + "Applies when:" line, nothing else; renders 593 bytes -- rendered locally with `python3 -B -I`);
  NoSkill = `Skill()` (renders "", so the prompt equals the No-Skill prompt, skill.py:6-8).
- F54 (verified) Format sentences the solver always receives (backends.py:379-392, 730-732), placed BEFORE the Skill
  under `PROMPT_LAYOUT = "contract-first-v2"` (protocol.py:341; backends.py:391-392): system opening
  "Solve the supplied task using only the supplied public information." then the contract:
  SearchQA/OfficeQA "\nReturn the concise final answer inside <answer>...</answer>."; LiveMath `LIVEMATH_CONTRACT`
  "\nChoose exactly one of the listed options and return only its letter inside <answer>...</answer>."
  (backends.py:35); SpreadsheetBench `SHEET_CONTRACT_V2` "\nReturn one complete Python program in a ```python code
  block whose opening fence starts its own line. The program reads input.xlsx and saves output.xlsx with the answer
  at the required answer position. A formula alone is not an answer: when the task asks for a formula, the program
  writes it into the answer cells." (backends.py:53-56); then "\n\nFrozen skill guidance (use only where
  applicable):\n" + Skill text (backends.py:380). ALFWorld: "Act in the text environment. Return a single action
  inside <action>...</action>." + "\nFrozen skill guidance (use only where applicable):\n" + Skill (backends.py:730-732).
  The fixed per-bench format checks of C3/diagnosis: `REQUIRED_FORMAT` (protocol.py:127-128).

### 2.10 Verbatim seed texts (training-side, not test data)

#### 2.10a The five PUBLIC task cards (`skillopt/coevo5/texts.py:31-96`, `texts.CARDS`), printed from the repo
##### card: searchqa (754 chars)
```text
Task kind: open-domain question answering over retrieved search snippets (the SearchQA benchmark).
Input the solver receives: a JSON object with two fields -- "question" (a short clue-style question) and "context" (several retrieved web search snippets, possibly noisy or irrelevant).
Fixed instructions the solver always receives: "Solve the supplied task using only the supplied public information." and "Return the concise final answer inside <answer>...</answer>."
Scoring (public metric): the text inside the last <answer>...</answer> is compared with the reference answer(s) by exact match after SQuAD-style normalization (lower case, punctuation removed, the articles a/an/the removed, whitespace collapsed). Anything else in the reply is ignored.
```

##### card: officeqa (1052 chars)
```text
Task kind: questions about U.S. Treasury Bulletin documents (the OfficeQA benchmark, in a one-call form). Answering needs finding the right values in the supplied document pages (running text and tables) and often a calculation with them.
Input the solver receives: a JSON object with two fields -- "question" and "context" (the parsed text of the bulletin page or pages the question refers to; tables are rendered as text; a long page may be cut).
Fixed instructions the solver always receives: "Solve the supplied task using only the supplied public information." and "Return the concise final answer inside <answer>...</answer>."
Scoring (public metric): the text inside the last <answer>...</answer> is compared with the reference answer by exact match after normalization (lower case; commas removed; punctuation removed except digits, '.', '-' and '%'; the words million, billion, dollar(s) and nominal removed; whitespace collapsed). There is no numeric tolerance. A reply without such a tag counts as wrong. Anything outside the tag is ignored.
```

##### card: livemath (842 chars)
```text
Task kind: multiple-choice questions about research-level mathematics (the LiveMathematicianBench benchmark): each question is built from a theorem of a recent arXiv paper.
Input the solver receives: a JSON object with two fields -- "question" (the statement to complete or decide) and "choices" (five options labelled A to E, separated by blank lines; exactly one is correct).
Fixed instructions the solver always receives: "Solve the supplied task using only the supplied public information." and "Choose exactly one of the listed options and return only its letter inside <answer>...</answer>."
Scoring (public metric): the letter inside the last <answer>...</answer> is compared with the letter of the correct option; a reply without such a tag, or with anything but one letter in it, counts as wrong. Anything outside the tag is ignored.
```

##### card: spreadsheetbench (1366 chars)
```text
Task kind: spreadsheet manipulation (the SpreadsheetBench benchmark): a natural-language instruction asks for a change to an Excel workbook, and the solver writes a Python program that makes it.
Input the solver receives: a JSON object with five fields -- "instruction", "workbook_preview" (for up to 20 sheets: the sheet name, its row and column counts, and the first 5 rows of up to 20 columns, with formulas shown as formulas), "input_path" ("input.xlsx"), "required_output_path" ("output.xlsx") and "required_answer_position" (the cells or range the instruction's result must occupy).
Fixed instructions the solver always receives: "Solve the supplied task using only the supplied public information." and "Return one complete Python program in a ```python code block."
Scoring (public metric): the program is taken from the reply's one ```python code block (without one, from a single unlabelled block or a reply that is entirely code; two Python blocks count as wrong) and runs once per test case in a sandbox (no network, a time limit of 300 seconds), reading that case's input.xlsx and writing output.xlsx; the workbook is recalculated, and the values in the answer position are compared with the reference workbook's. A task counts as solved only when every test case matches; a program that raises an error or writes no valid output.xlsx does not solve it.
```

##### card: alfworld (1023 chars)
```text
Task kind: household tasks in a text environment (the ALFWorld benchmark): the solver acts step by step, one action per step, to reach a goal stated at the start (for example, to put a cleaned object in a receptacle).
Input the solver receives at every step: a JSON object with four fields -- "initial_observation" (the room description and the task, as given when the episode starts), "observation" (the environment's latest text), "admissible_commands" (the actions the environment accepts now) and "recent_history" (the last five observation-action pairs).
Fixed instructions the solver always receives: "Act in the text environment. Return a single action inside <action>...</action>."
Scoring (public metric): the episode succeeds when the environment reports the goal reached within 50 steps; an episode that runs out of steps counts as failed. The text inside the first <action>...</action> is executed (a reply without the tag is executed whole); an empty action or one longer than 1000 characters counts as failed.
```


#### 2.10b The five TASK-CARD INSTRUCTIONS = chain I seeds (GLM-5.3-written from the cards), verbatim from dl
Source: `/data/coevo5-20261019-v3-pre/texts/texts.json` key `instructions` (identical to the manifest's
`instructions`, prelaunch.py:510). In the Skill each is passed through `skill.seed_text` (level-1/2 headings demoted
to 3/4; only the OfficeQA one has a heading) and placed under its section heading + "Applies when:" line.
##### instruction: searchqa (1846 chars, sha256 48b10afcc1dd0dcf)
```text
- Read the question first and note its type (person, place, date, number, title, etc.) so you know what form the answer should take.
- Scan all snippets, not just the first: the answer may appear only in a later snippet, and early snippets are often irrelevant.
- Snippets are noisy: ignore SEO text, navigation fragments, and off-topic content. Use only what directly answers the question.
- Prefer an answer that appears verbatim in the snippets over one you synthesize; the metric is exact match, so the exact surface form from the context is safest.
- If snippets disagree, favor the most authoritative, specific, or repeated source; consider whether the question's phrasing (e.g., "Jeopardy!"-style clue) implies a well-known fact.
- Answer with the minimal entity or value requested, not a full sentence: e.g., a name, a date, a title, a number.
- Match the question's expected unit and granularity: if asked "how many", give just the number (unless the source shows a unit is part of the canonical answer).
- If the question asks for one of several (e.g., "which city"), return only that item, not a list, unless the question explicitly asks for multiple.
- Watch for near-miss distractors in the snippets (similar names, different dates, related works); verify the snippet actually matches all constraints in the question.
- Handle titles and proper nouns carefully: include articles that are part of a title (e.g., "the great gatsby" keeps "great gatsby"), since normalization only strips articles ambiguously — keeping the source's wording avoids risk.
- If no snippet contains the answer, still give your best short guess from the context or general knowledge; an empty answer scores zero.
- Output the final answer inside `<answer>...</answer>`, ensuring that the last such tag in your reply contains exactly the concise answer text.
```

##### instruction: officeqa (2926 chars, sha256 2e92500a832ee32e)
```text
# Guidance for U.S. Treasury Bulletin Questions (OfficeQA, one-call)

- Read the **question first** to identify the exact quantity sought (a date, a single value, a percentage change, a sum/ratio across line items, etc.) — this determines what to hunt for in the context and whether a calculation is needed.
- Search the supplied **context** for the relevant table or passage. Treasury Bulletin pages mix running text with tables rendered as text; match on row/column labels, table titles, footnote markers, and period labels (e.g., fiscal-year vs. calendar-year, month, quarter) before trusting any number.
- **Use only the supplied context.** Do not fill gaps from memory of Treasury data, and do not "correct" numbers that look odd — the reference answer is derived from these pages.
- Watch for **units and scaling**: tables may state "millions of dollars", "percent", or "billions" in headers or notes. If the answer must be in a specific unit, convert carefully; the normalization removes the words million/billion/dollars/nominal, so the *digits* you emit must already reflect the intended magnitude.
- Pay close attention to **row and column alignment** in flattened tables: parsed text can misalign headers, so verify a candidate value by checking neighboring values that you can cross-check against totals or subtotals in the same table.
- If a computation is required (difference, sum, growth rate, share of total), show the work in your reasoning, then perform it **exactly** with the figures as printed — round only if the question or table conventions clearly imply it (e.g., "percent change to one decimal").
- Be careful with **signs and negatives**: values in parentheses typically mean negative; the normalization keeps '-', so include it when the answer is negative.
- Distinguish similar series that commonly appear together (e.g., fiscal year-to-date vs. monthly, assets vs. liabilities, holdings vs. transactions, different maturities or instrument types) — a one-word mismatch in the label usually means the wrong figure.
- If the context is cut off or the needed figure is genuinely absent, pick the best-supported answer from what is present rather than guessing wildly; prefer a value from the same table over one inferred from text.
- Format the final answer to survive normalization: **emit the bare number (or short string) inside `<answer>...</answer>`**, without commas, currency symbols, or units if the reference is a pure number; keep '%' only if the answer is a percentage. Avoid thousand separators, since commas are stripped anyway but any extra words will break exact match.
- If multiple `<answer>` tags appear, only the **last** one is scored — so place exactly one final tag at the end with your definitive answer.
- Keep the answer **concise**: a number, a short label, or a date in the form most likely used by the reference (e.g., "12345.6" rather than "12,345.6 million dollars").
```

##### instruction: livemath (2068 chars, sha256 9cb3d860ec6970b5)
```text
- The question is built from a theorem in a recent arXiv paper, so expect precise, technical mathematical content; read the statement carefully for quantifiers, hypotheses, and exact constants.
- Do not assume the theorem is one you know from classical literature; it may be a recent refinement, so verify each option against the statement rather than against memory of older results.
- Parse the "question" field completely before looking at the choices: identify what is being asked (a value, an inclusion, a yes/no decision, a completion of a sentence).
- Examine all five options; distractors are typically near-misses such as swapped quantifiers, weakened/strengthened hypotheses, wrong constants or dimensions, or plausible but false generalizations.
- Check edge cases and boundary conditions: strict vs. non-strict inequalities, open vs. closed sets, equality vs. containment, "for all" vs. "there exists".
- Beware of options that are true statements in general but do not answer the specific question, or that hold only under additional assumptions not present in the question.
- Use only the supplied public information; do not rely on external knowledge of the specific paper, but standard mathematical reasoning and background are fine.
- If two options look close, translate both into precise mathematical language and test them against simple examples or limiting cases consistent with the hypotheses.
- Eliminate clearly wrong options first; among the remainder, prefer the option that matches the theorem's exact formulation rather than a paraphrase that changes meaning.
- When the question asks to "complete" a statement, ensure grammatical and logical continuity with the stem; a choice may be correct only when read in the full sentence.
- Decide on exactly one letter; if uncertain, choose the most defensible option after elimination rather than leaving the answer ambiguous.
- Return only a single letter (A–E) inside `<answer>...</answer>`, with nothing else in the tag, as the final part of your reply; the last such tag is what gets scored.
```

##### instruction: spreadsheetbench (2907 chars, sha256 48a5df7f745606ba)
```text
- Write a single, self-contained Python program in exactly one ```python code block; use openpyxl (the standard tool for this benchmark) and nothing requiring network access.
- The program must read `input.xlsx` (hardcode this path or read it from the supplied JSON's `input_path`) and save to `output.xlsx`; do not rename sheets or move data unless the instruction explicitly says so — only the cells named in `required_answer_position` are compared.
- Inspect the `workbook_preview` carefully: note sheet names (including exact spelling, spaces, and capitalization), dimensions, and the first rows/columns. Formulas appear as formulas in the preview, so the stored cell values may differ from what is shown; if the preview shows formulas, expect the real workbook to contain them and handle them via openpyxl's formula-preserving mode (`load_workbook(path, data_only=False)` is the default).
- Decide whether the answer position should contain literal values (computed in Python) or formulas. Safest: write literal values that equal the recalculated reference result, unless the instruction explicitly asks for formulas. If you do write formulas, they must recalculate to the correct values when the grader recalculates the workbook.
- When reading values, remember `data_only=True` returns cached results (None if the file was never recalculated by Excel) and `data_only=False` returns formula strings. Load twice (once each way) if you need both formulas and cached values.
- Match data types exactly where the comparison is value-based: numbers as numbers (not strings), dates as datetimes, and beware of text that looks like numbers. Preserve number formats only if the instruction concerns formatting; otherwise prefer writing plain values.
- Locate the target cells robustly: the answer may span a range (e.g. `Sheet1!B2:D5`) or multiple sheets. Ensure every cell in the range is written, including empty strings/None where the reference is empty, if that's plausible from the instruction.
- Handle merged cells, hidden sheets, and sheets beyond the 20-sheet preview limit — the actual workbook may be larger than the preview, so iterate dynamically rather than assuming preview bounds.
- Avoid operations that depend on Excel itself (no xlwings/win32com); openpyxl cannot evaluate formulas, so compute any derived results in Python rather than relying on cached formula values unless verified present.
- Keep runtime well under the 300-second limit: avoid O(n²) scans over huge ranges; operate only on the relevant sheets and columns.
- Wrap risky operations defensively: if a sheet or column mentioned in the instruction might not exist, check and fall back sensibly rather than raising. A raised error means zero credit.
- After writing the required cells, save the workbook with `wb.save("output.xlsx")` and ensure the program exits cleanly; verify the save path matches `required_output_path`.
```

##### instruction: alfworld (2301 chars, sha256 5ae6ea9bffa3902e)
```text
- Always emit exactly one action per reply, wrapped in `<action>...</action>`; anything outside the tag is ignored, and a missing tag causes the whole reply to be executed, which almost always fails.
- The action must be one of the strings listed in `admissible_commands` — copy it character-for-character rather than paraphrasing, since the environment only accepts the listed commands.
- Before acting, re-read `initial_observation` to keep the goal in mind; it states both the task type (e.g., heat/cool/clean/examine an object, or place two objects somewhere) and the specific objects and receptacles involved.
- Parse the task into a concrete subgoal sequence, e.g., "find object → pick it up → find the required appliance (basin, fridge, microwave, etc.) → use it → move to the destination receptacle → put the object down".
- Use navigation commands (`go to X`) to explore locations named in the room description; `admissible_commands` reveals which receptacles and locations currently exist, so use it as a map of what is reachable.
- When you need an object's location, check the likely receptacles listed in the room description one at a time (e.g., `go to countertop 1`, `open drawer 1`, `examine X`) until you find it.
- Keep your physical state in mind: you can hold at most two objects (hands are used in commands like `take A from B`); note what you took from `recent_history` since it is not restated each turn.
- For cleaning tasks you need a sinkbasin; for heating a microwave; for cooling a fridge. Put the object in/on the appliance (e.g., `put A in/on sinkbasin 1`, `heat A with microwave 1`), then take it back out before delivering it to the final receptacle.
- Prefer efficient exploration: plan multi-step routes (e.g., go directly to a likely receptacle rather than re-visiting ones already seen as empty in `recent_history`).
- Watch `observation` after each action for success/failure feedback — "Nothing happens" or an error message usually means the action was inapplicable; adjust rather than repeating it.
- Do not emit empty actions or replies over 1000 characters; keep the action short and exact.
- Track progress against the 50-step limit: if a plan stalls, fall back to systematically exploring all receptacles named in the room description rather than wandering.
```

#### 2.10c The empty scaffold (chain E start) = `Skill(scaffold=True).render()` (593 bytes; skill.py:63-74 with
`TITLES`/`APPLIES_WHEN`, protocol.py:36-47)
```text
## SearchQA
Applies when: the task gives a clue-style question with retrieved web search snippets and asks for a short answer.

## OfficeQA
Applies when: the task gives document text or data tables, such as U.S. Treasury Bulletin pages, and asks a question answered from them.

## LiveMath
Applies when: the task is a mathematics question with lettered answer options.

## SpreadsheetBench
Applies when: the task asks for a Python program that modifies a spreadsheet workbook.

## ALFWorld
Applies when: the task is a text household environment where you choose one admissible action per step.
```
- F55 (verified) Every Skill is rendered WHOLE into every task's prompt: all sections in ORDER (skill.py:63-74), sent as
  "Frozen skill guidance (use only where applicable):" (backends.py:380, 732). So in chain I every task sees all five
  instructions, including other benches' format advice (e.g. SpreadsheetBench's "exactly one ```python code block").
  The applicability lines are fixed text, never learned (protocol.py:35).

- F56 (verified) Code vs registration v6 §4-§9 (docs/handoff/coevo5-registration-v6-20261017.md:151-488): the step
  order, fallbacks (lines 182-184), gate criteria C1-C4' (283-296), two rounds/placement/composite (357-377),
  examiner rubric/judge/revision/selection panel (398-421), research ceilings (423-443), forward-item validity and
  ceilings (445-469) and leakage (471-488) match the code, with the v2/v3 deltas the code marks: diagnosis no longer
  lets rubric host checks pre-empt the model and uses `TAXONOMY` first (examiner.py:21-25, v2 §3; v6 §6 line 417
  still describes the v1 order); per-edit/per-row validation (v2 §6, v3 §4); regression tolerances from
  `calibrate_split` (protocol.py:75-79) instead of the v6 table (lines 300-303); `TRIGGER_RUNS`/`PARENT_REGRESSION_RUNS`
  (v2 §5); the self-test unit and `held` evidence items (v3 §7); shared-unanswered exclusion (v3 §3).

### 2.11 Role table: system prompt purpose, payload, schema/validator, fallback, ceiling (all verified)

| role label (`Roles.ask` role) | where | purpose | input payload | reply schema / validator | fallback on invalid | ceiling |
|---|---|---|---|---|---|---|
| `judge` | examiner.py:77-81, 235-253 | reference-free pass/fail on rubric TEXT items | `{task, answer, items}` | `{"verdict","violated"}` / `_judgment` | verdict "invalid" (wrong under both rubrics on the panel) | 1 per judgeable answer (all answers of the training execution) + <= 40 re-judged with the candidate |
| `revise` | examiner.py:90-99, 384-426 | <= 3 rubric edits from disagreements | `{rubric, library, disagreements[]}` (fit 220000 B) | `{"edits":[...]}` / `_edits` (per-edit) | status `invalid_reply`, no revision | 1 per stage, never retried; benches ORDER[:4] |
| `diagnose` | examiner.py:82-89, 481-505 | one failure code per failed answer (sees reference) | `{task, answer, reference, codes}` | `{"code"}` / `_code` | code "other" (`by: "invalid"`) | 1 per failed answer not decided by table/format |
| `analyst` | analyst.py:59-85, 249-262 | <= 5 rules + transfer slot | `payload(...)` (F15) | `{"rules","transfer"}` / `_check` (per-row) | `method_failure`, no rules this step | `ANALYST_ATTEMPTS = 2` |
| `research_query`/`research_pick`/`research_conclude` | research.py:68-106, 578-664 | queries, page pick, conclusion w/ verbatim quotes | request JSON (rule, question, tried, pages) | `_query`/`_pick`/`_conclusion` | call consumed; round continues/ends | <= 8 calls, 3 rounds, 3 queries/round, 3 pages per request; <= 2 questions per rule |
| `research_rewrite` | research.py:107-113, 686-702 | rewrite rule to agree with findings | `{rule, findings}` | `{"text"}` + `Rule` format | keep original (`rewrite_failed`) | 1 per researched rule |
| `forward_generate` | forward.py:59-90, 384-443 | 3 items on real material | `{topic, source, material, count}` | `{"items":[...]}` / `_generated` (<= 3) | round yields nothing | 1 per round, <= 5 rounds per (rule, target) |
| `forward_check` | forward.py:91-101, 363-380 | independent formula / yes-no consistency | `{table, question}` or `{passage, question, formula}` | `{"formula"}` / `{"verdict"}` | item dropped (`check_invalid`) | 1 per item passing program checks (<= 3 per round); <= 60 calls per (rule, target) incl. material |
| `leak_adjudicate` | leakage.py:73-90, 280-291 | veto task-specific / answer-distribution / unseen-condition rules | `{rule, colliding_items?, answer_values?}` | `{"verdict","reason"}` / `_verdict` | rule dropped | 1 per rule text (again per self-test revision) |
| `selftest_revise` | step.py:405-416, 419-443, 536-543 | batch-rewrite or drop rules that failed self-test | `_revision_payload` (bounded 220000 B) | `{"rules":[{"id","text"}|{"id","drop":true}]}` / `_revisions` (per-entry) | rules `selftest_failed` | `SELFTEST_ATTEMPTS = 2` (2nd only after invalid) |
| `rubric_writer` (pre-launch) | texts.py:97-111, 168-176 | initial rubric from the card(s) | `{rubric, task_card(s)}` | `{"items"}` / `_rubric` | preparation stops (owner decides) | `ANALYST_ATTEMPTS = 2` |
| `instruction_writer` (pre-launch, `plain`) | texts.py:22-30, 179-183 | zero-shot Skill text from a card | plain text card | non-blank text, one fence removed | preparation stops | 1 per written bench |

Token ceilings per learning step are scopes in the ledger (`LEARNING_CAP`, protocol.py:286-290, declared in
chain.py:107-117; deepseek chains' GLM role cap per bench: searchqa 10M, officeqa 6M, livemath 6M,
spreadsheetbench 4M, alfworld 3M). v3 spent GLM 7,804,250 in all (results-and-lessons.md:142).

## 3. Interfaces an implementer would call or must replace

All signatures verified by reading (exact text). "->" gives the return shape; side effects noted.

### 3.1 Role calls (reuse as is)
- `roles.Roles(endpoint)`; `.ask(role, system, user, *, label, check=None) -> value | None` (appends to `.calls`;
  raises `ConfigurationError("invalid_model_receipt")` on an invalid receipt; stops of the run propagate from the
  endpoint); `.plain(role, system, user, *, label) -> str | None`; `.count(prefix) -> int`. Role name must match
  `[a-z][a-z0-9_]{0,39}` (roles.py:22, 95).
- Validators: `roles.parse(text) -> dict` (raises `Invalid`), `fields(value, required, optional=())`,
  `text(value, *, limit, empty=False)`, `items(value, *, limit, low=0)`, `fit(user, key, budget) -> user`
  (raises `ValueError` when fixed fields exceed the budget), `message_bytes(user) -> int`, `class Invalid(ValueError)`.
- Endpoint construction: `units.endpoints(setting, chain, stage, kind="learning") -> (solver_endpoint,
  role_endpoint)` (charges scopes `(OVERALL, chain_scope(chain), step_scope(chain, stage, kind))`, units.py:78-94).

### 3.2 Execution of arms (reuse; generalize the `skill` argument)
- `step.run_round(setting, attempt, endpoint, unit, arms, schedule, tasks, *, tag) -> {(arm, item): [cell record per
  run]}`; `arms`: {arm: Skill TEXT}; `schedule`: {arm: [(item, runs)]}; `tasks`: {item: {"public","private"}}. Side
  effects: writes `attempt/cells/<cell id>.json` (+ `.claim`) and `attempt/artifacts/<sha>.json`; raises
  `cells.Pause(kind, reason, cell)` after writing the cell record on a stop.
- `cells.run_cells(context, jobs, *, workers)` with jobs `(cell, task, skill)`, `cell = {"id","unit","arm",
  "benchmark","task_id","run"}`; `cells.run_parallel(function, jobs, *, workers) -> [results in job order]` (halts on
  the first error, re-raises it); `cells.cell_id(unit, arm, task_id, run) -> 32-hex`; `cells.Context(*, store,
  endpoint, runtime, native, episodes)`; `units.cell_context(setting, attempt, endpoint)`.
- The solver entry the shell must wrap: `cells._solve` -> `backends.solve(benchmark, public, skill_text, call, *,
  runtime=None)` where `call(system, user)` is the endpoint recorder (cells.py:122-136; backends.py:364-392). The
  skill enters ONLY as a text string in the system prompt. Re-execution `cells._replay` requires the IDENTICAL request
  hash (cells.py:139-149). (inferred) A route-B shell can be inserted as a wrapper around `call` (pre/post each model
  call, also per ALFWorld step since `_solve_alfworld` calls `call` once per step), but anything that changes the
  messages changes request hashes and the prompt layout, i.e. it is a new runtime/protocol.
- Units: `units.run_unit(unit_root, *, run, identity, work) -> sealed record {"version","run","identity","status":
  "complete","attempt","result"}`; `work(attempt_dir) -> JSON-safe dict`; raises `Pause` (writes
  `attempt/status.json`, `diagnostics.log`); `units.unit_path(chain_root, stage, name)`.

### 3.3 Paired statistics (reuse unchanged)
- `stats.bounds(cells) -> {(arm,item): (L, H, unknown, runs, infra_unknown)}` (cells = {(arm,item): [tokens]});
  `stats.total(table, arm, items, side) -> Fraction` (requires every item scheduled); `stats.unknown_share(table, arm,
  items, infrastructure_only=False) -> Fraction`; `stats.sign_test(wins, losses) -> float`; `stats.bootstrap(strata,
  statistic, *, resamples=10000, seed=20261017, level=0.95) -> (lo, hi)`.
- `step.table_of(cells)`, `step.guard(cells, arms, unit)` (raises `Pause("infrastructure_incomplete")`),
  `step.shared_unanswered(cells, items) -> [items]`, `step.violations(store, cells, arm, items, bench, *,
  unknown_counts) -> Fraction`.
- Test-set readings: `readout.panel(items, groups=None) -> Panel`; `readout.Readings(units, panels, *,
  resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED)`; `.reading(parts, *, transform=None) -> {"available": True,
  "known"|"low"|"high": {"estimate","interval95","lower90","resamples","items"}} | {"available": False,"missing"}`;
  `holds_large(result, threshold, *, bound="interval95")`, `holds_small`, `noninferiority(result, margin)`;
  term builders `accuracy`, `combine`, `macro`, `difference`, `step_change`, `transfer_cells()`.

### 3.4 Gate (replace by version-level acceptance; keep the pieces noted in §4)
- `gate.verdict(table, *, arm, parent, controls, trigger, rest, tolerance, regression, targets=None,
  min_trigger=None, held=()) -> {"status": "pass"|"fail"|"undetermined", "margin", "priority", "criteria"}`
  (requires exactly 4 controls); `gate.composite(table, *, arm, parent, members, rest, tolerance, regression,
  panels=None, min_trigger=None, held=())`; `gate.placement(similar, local)`; `gate.confirmation_arms(tentative,
  screen_local)`; `gate.final_placement(tentative, *, screen_local, confirm_similar=None, confirm_local=None)`;
  `gate.priority(margins)`; `gate.fitting_subset(order, size, cap=MAX_SKILL_BYTES)`; `gate.accepted(subset,
  composite_status=None)`; `gate.placebo_passage(table, controls, trigger_sets, parent) -> {control: {rule: bool}}`;
  `gate.round_complete(table, guards)`.
- Step units: `step.train/prepare/selftest/screen/confirm/composite/merge/learn` (signatures in step.py:197, 320,
  496, 720, 741, 765, 816, 830).

### 3.5 Examiner, analyst, research, forward, leakage (reuse pieces; replace the rule-text roles)
- Views: `examiner.task_view(benchmark, public, *, trace=None, context_chars=None) -> dict` (never a reference),
  `examiner.answer_text(benchmark, output) -> str|None`, `examiner.reference(benchmark, answer) -> dict`;
  `step.answers(store, result, tasks, bench, split) -> [answer dict]` (F10), `step.answer_of(store, record, tasks,
  bench, item, key)`.
- Examiner: `validate_rubric(value, bench)`, `judge(...)`, `judge_all(roles, benchmark, rubric, general, answers, *,
  label, workers) -> {key: judgment}`, `selection_panel(answers, *, seed, tag) -> [keys] | None`,
  `disagreements(answers, judgments, *, seed, tag)`, `balanced_accuracy(panel, answers, judgments) -> (Fraction,
  int)`, `revise(roles, benchmark, rubric, general, answers, *, seed, tag, label, workers) -> record`,
  `diagnose(roles, benchmark, rubric, general, failures, *, label, workers) -> {key: {"code","by"}}`,
  `taxonomy(benchmark, *, model=False)`, `code_meanings(benchmark, rubric, general)`, `library()`.
- Analyst: `payload(benchmark, *, parent_text, failures, diagnoses, meanings, cards, seed, tag, passed=())`,
  `propose(roles, benchmark, value, *, stage, codes, label) -> {"status","attempts","transfer","proposals"}`,
  `deduplicated(proposals, parent_texts) -> (kept, dropped_ids)`, `normalized(value)`, `examples(failures, diagnoses,
  *, seed, tag, limit=MAX_EXAMPLES)`, `contrast(passed, *, seed, tag)`, `evidence_problem(evidence, codes, shown)`.
- Research: `research.Wikipedia(*, proxy=None, transport=None, timeout=60)`, `research.Archive(root)`,
  `research.Sources(wikipedia, archive, store)`, `research.request(roles, sources, *, purpose, question, label,
  rule=None)`, `research.material(roles, sources, *, rule_text, style, label, log=None)`, `research.rewrite(roles,
  rule_text, findings, *, label) -> (text, "rewritten"|"kept"|"rewrite_failed")`; `FetchError` is recorded, never
  a stop. `setting.sources(store)` builds `Sources` (units.py:55-56).
- Forward: `forward.evaluate(formula) -> Fraction` (raises `roles.Invalid`), `forward.literals(formula) -> [str]`,
  `forward.rounded(value, decimals) -> str`, `forward.identity(material_text, question) -> sha256 hex`,
  `forward.build_panel(roles, *, rule_id, rule_text, target, material, label) -> {"status": "ok"|"short", "items":
  [{"id","benchmark","public","private","identity","source","formula","round"}], "counts": {"rounds","generated",
  "valid","duplicates","dropped"}, "rounds": [...]}`.
- Leakage: `leakage.Corpus(benchmark, items, *, alfworld_texts=None)`, `.evidence(words)`; `leakage.findings(text,
  corpus) -> {reason: True | [words]}`, `leakage.mechanical(text, corpus) -> reason | None`,
  `leakage.adjudicate(roles, text, *, label, colliding=None, values=None) -> bool (True = keep)`,
  `leakage.answer_values(answers, limit=60)`, `leakage.normalize(text)`, `leakage.surface(benchmark, item, *,
  task_text=None)`.
- Texts/Skill: `texts.CARDS`, `texts.INSTRUCTION_SYSTEM`, `texts.instruction_prompt(benchmark) -> (system, user)`,
  `texts.solver_cards(cards, runtime)`; `skill.Rule(id, text, home, also=())`, `skill.Skill(seeds=(), rules=(),
  scaffold=False)` with `.seeded(seeds)`, `.add(*rules)`, `.render()`, `.text_with(*rules)`, `.size_with(*rules)`,
  `.fits(*rules)`, `.to_json()/.from_json(value)`; `chain.start(setting, chain)`.

## 4. What route B can reuse unchanged vs what must be generalized

### 4.1 Reusable unchanged (code or concept)
1. **Role-call contract** `roles.py` as a whole: one-JSON-object reply, per-call record with request hash and
   receipts, validators, `fit` input bounding, invalid reply -> registered fallback, stops propagate (F1-F6). The
   engineer and examiner-as-programmer roles can be `Roles.ask` calls with new system prompts and validators.
2. **Interleaved same-session execution**: `step.run_round` (seeded shuffle of every (arm, item, run) job of a round)
   + `cells.run_cells/run_parallel` + `cell_id` + exclusive claim/once-written records + `Pause` (F42). This is exactly
   the "四组同时段逐题交错" mechanism; only the `arms` values must become packages instead of text (see 4.2).
3. **Paired exact statistics**: `stats.bounds/total/unknown_share/sign_test/bootstrap` (F38, 3.3); conservative L/H
   imputation (rule on L, comparators on H) generalizes directly to "candidate S' on L, S / task-card / placebo on H".
   `step.shared_unanswered` (provider-side content filter mask), `step.guard` (>10% infrastructure-unknown pauses),
   `step.violations` (format violations as per-item shares) are bench-generic.
4. **Readings**: `readout.Readings` (paired bootstrap per bench with OfficeQA file groups, known/low/high variants,
   `holds_large/holds_small/noninferiority`) is reusable for the per-step five-domain test reading, provided ORDER and
   chain names are parameterized (4.2).
5. **Answer views**: `examiner.task_view/answer_text/reference`, `step.answers/answer_of`, `sheetview` (bounded,
   clipped, reference only where allowed, F10, F26) -- the engineer needs exactly these views of failure records.
6. **Failure taxonomy** `TAXONOMY` (F25) as the examiner's initial failure classes (e.g. ALFWorld D3 "search loop",
   OfficeQA D3 "calculation slip") -- the classes route B's first detectors would target.
7. **Exact arithmetic + independent consistency check** of generated items: `forward.evaluate/literals/rounded/
   identity`, the drop-reason accounting (`DROPS`, `counts`, per-round records) and the "program decides validity,
   never a model alone" principle (forward.py:11-13) -- directly the "真值由程序算出" gate for OfficeQA-style items.
8. **Research sources and archive** (`Wikipedia`, `Archive`, `Sources`, `request`, verbatim-quote check) if route B
   keeps research (e.g. the engineer looking up openpyxl/LibreOffice semantics in the pinned archive).
9. **Leakage principle and text checks** `leakage.Corpus/findings/mechanical/adjudicate` for every TEXT part of a
   procedure (description, any string the procedure injects into the prompt, string/number literals extracted from
   its code) -- see 4.2 #8 for what must be added for code.
10. **Placebo diagnostic** `gate.placebo_passage` (descriptive) and the practice of fixed, pre-written irrelevant
    controls at the same placement; the four-arm design of route B is the version-level analogue.
11. **Seeds**: `texts.CARDS`, the five instructions (2.10b), `Skill.seeded/seed_text`, `TITLES`, `APPLIES_WHEN`; and
    the prompt contract sentences (F54) as the fixed per-bench "format guardrail" text (they are already outside the
    learnable Skill, placed before it by contract-first-v2).
12. **Unit/attempt/ledger discipline** `units.run_unit` (idempotent units, new attempt dirs, sealed records, owner
    recovery) and the per-step token scopes (`endpoints`, `LEARNING_CAP` scopes).

### 4.2 Must be generalized (and which constant/assumption it bakes in)
1. **Chain order** `protocol.ORDER = ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")`
   (protocol.py:13). Route B's order is SpreadsheetBench -> OfficeQA -> LiveMath -> SearchQA -> ALFWorld. ORDER is
   baked into: section render order (skill.py:66), `step._identity` benchmark (step.py:100), `regression_keys`
   (`ORDER[:stage-1]`, step.py:91), `similar_targets` (protocol.py:23-28), `EXAMINER_BENCHES = ORDER[:4]`
   (protocol.py:131; still "all but ALFWorld" in route B's order by coincidence), `data.regression_items`
   (`ORDER[-1]` has none, data.py:202), readout `stage_of/gain/forgetting/ahead/transfer_cells` (readout.py:103-142),
   `smoke.BENCHES = ORDER[:2]` (smoke.py:64), `research.rewrite` validating with `ORDER[0]` as dummy home
   (research.py:699), `leakage.Corpus` bench check. -> a new protocol module (new version, new output dir).
2. **The learnable object** `skill.Rule/Skill` (text bullets <= 600 chars, `MAX_RULES = 5`, `MAX_SKILL_BYTES =
   20000`, sections + similar placement `also`, protocol.py:48-53; skill.py:23-136) -> a package of procedures
   {code, applicability predicate (code), description, replay tests} + frozen cards + fixed router + fixed format
   guardrails. `Skill.render()` (one text) is replaced by the shell; the "use only where applicable" whole-Skill
   prompt (F55) is replaced by router activation per item.
3. **Solver path** `backends.solve(benchmark, public, skill_text, call, ...)` takes a text Skill (backends.py:364-392);
   route B needs a shell around `call` (context rewrite, deterministic computation, action veto) and an activation log
   per item. `cells._solve/_replay` (cells.py:122-149) must pass the package and keep replay-by-identical-request.
4. **Similar placement and forward targets** (`SIMILAR_PAIRS`, `FORWARD_STYLES`, `similar_targets`, `Rule.also`,
   C4', `gate.placement/confirmation_arms/final_placement`, protocol.py:18-28) -> gone; transfer is read from
   per-procedure activation logs. `readout.transfer_cells` (self/similar/rest classes from the map) must be replaced
   or re-parameterized by the new order and the owner's 10/17 similarity cluster.
5. **Rule-level gate** (`gate.verdict` C1 on diagnosis-code trigger sets with `MIN_GAIN = 1`, `MIN_TRIGGER = 4`,
   tolerances in items `TOLERANCE_FOCAL/REGRESSION`, two rounds screen/confirm with 4+4 text placebos, composite,
   priority/fitting subset) -> version-level acceptance: four interleaved arms (S', S, task-card only, placebo
   procedure) on a FRESH, once-used batch, mean paired accuracy vs a pre-registered minimum effect per bench. Keep:
   `run_round`, `bounds/total`, L/H conservatism, `shared_unanswered`, `guard`, `violations`; replace: `runs_plan`
   (trigger-set-dependent run counts, `TRIGGER_RUNS`, `GATE_RUNS`), `verdict`, `composite`, `placement` logic.
6. **Placebos** are TEXT rules (`PLACEBOS_SCREEN/CONFIRM`, protocol.py:105-124) placed via `Skill.text_with`; route B
   needs a placebo PROCEDURE that occupies the same context slot and makes the same number of shell calls with no
   useful information -- new code; cal-1 shows text placebos move scores by -9.8..+3.6 points (F47).
7. **Examiner revision** (rubric text items + fixed 7-check library, accepted on balanced accuracy vs official
   pass/fail, F18-F22) -> model-written detector CODE accepted on pre-registered precision/recall on held-out
   trajectories. Reusable pattern: selection panel fixed before judging, invalid = wrong, minimum gain AND minimum net
   count, honest "selection material" label. New: sandboxed execution, label source (see §5 #5).
8. **Leakage for code**: `leakage.surface/Corpus` compare natural-language text with item surfaces and references;
   procedures need (a) static extraction of string/number literals, regexes and lookup tables from the code AST, run
   through `findings` + `adjudicate`; (b) a shell-level guarantee that procedures and detectors never receive
   `private` fields (today every answer dict carries `private`, F10); (c) the adjudicator's categories (fact of one
   task, "when X answer Y", answer-distribution steering, unseen conditions; leakage.py:73-90) restated for code,
   e.g. an applicability predicate keyed to one task's surface string is the code form of "maps a specific kind of
   task to a specific answer".
9. **Analyst -> engineer**: `ANALYST_SYSTEM` + `_row` (text <= 600 chars, codes, evidence 2-8 shown ids, covered/adds,
   research questions) -> code fields; the evidence rule maps to "replay tests = the failure records it claims to
   fix"; per-row validation (an invalid row never tested, the rest stands) and `ANALYST_ATTEMPTS = 2` carry over.
10. **Self-test** (rule vs parent on its own proposal-half evidence items, one batch revision, second round; F13) ->
    route B step 5 (S' vs S on generated item sets of this and earlier benches; a sieve, not acceptance). The batch
    revision call shape (`SELFTEST_SYSTEM`, `_revisions`) is reusable as "fix-or-drop the failing procedures once".
11. **Generated items** (`forward.build_panel`, only OfficeQA/LiveMath styles, only for similar candidates, Wikipedia
    material) -> examiner-written GENERATOR PROGRAMS per bench (perturb real training tables and recompute; symbolic
    verification for LiveMath; synthetic workbooks + reference formula; ALFWorld simulator sampling) plus two gates
    with no code today: 20%-80% pass-rate saturation filter and predictive validity (sign agreement with real fresh
    items). `forward.evaluate`'s formula language (no sqrt/log/exp/fractional powers, forward.py:50-51, 138-154) is too
    narrow for OfficeQA's real methods (CAGR, roots: TAXONOMY officeqa D2/D3) and LiveMath needs a symbolic engine.
12. **Data draws**: `data.training_items` returns ONE fixed seeded draw per bench ("the same for every chain",
    data.py:188-196): SearchQA 200 of 600, OfficeQA all 74, LiveMath 100 of 283, SpreadsheetBench all qualified,
    ALFWorld all 57 (`POOLS`, `TRAIN_ROLLOUT`, protocol.py:60-64), and `halves` re-splits those same items. Route B
    needs disjoint once-used batches (run batch, acceptance batch per step), which the small pools (OfficeQA 74,
    ALFWorld 57) can barely supply.
13. **Chains/families/caps** (`units.CHAINS`, `readout.FAMILIES`, `LEARNING_CAP`, `CHAIN_CAP`, `SOLVERS =
    ("glm-5.3", "deepseek-v4-flash")`, `SOLVER_MAX_TOKENS`, `SLOTS`, `DEEPSEEK_ROUTE`; protocol.py:29, 285-331) -> the
    smoke must use the new endpoint model "deepseek-v4.1-flash-1017" (design-v0 last line), which is in none of these
    tables.
14. **Report** (`report.examiner/_gate/_support/untestable`, rule-level funnel) -> version-level acceptance records,
    procedure activation and transfer per procedure; the accounting/spending parts can be kept.

### 4.3 Verbatim constants route B is most likely to reuse (printed from the repo with `python3 -B -I`)
##### leakage.ADJUDICATE_SYSTEM (leakage.py:73-90)
```text
You review one guidance rule written for a language model that solves benchmark tasks. Decide whether the rule states a fact about one specific task -- for example a particular question's answer, entity, number, date or document detail -- or maps a specific kind of task to a specific answer (for example "when the question mentions X, answer Y"), or steers the answer by how the benchmark's answers are distributed rather than by reasoning about the task (for example "option C is usually right" or "the option saying that none of the others hold is usually the answer"), or makes its advice depend on something the solver cannot see while solving -- the reference answer, whether an answer is correct, or a score (for example "when the reference is a pure number, ..."). General advice on method, reading the material, calculation or the answer format is not such a statement, even when it gives an illustrative example.

The user message is a JSON object {"rule": the rule's text}, possibly with "colliding_items": training tasks whose reference answer is a word that also occurs in the rule (each with an excerpt of its question and its answer), and possibly with "answer_values": values that training spreadsheet tasks expected in their answer cells. Then decide also whether the rule gives away those answers or copies those values, or uses a word only incidentally in general advice. Reply with one JSON object and nothing else: {"verdict": "yes" or "no", "reason": a short reason of at most 300 characters}. "yes" means the rule states such a fact, mapping, answer distribution or unseen condition, gives away a colliding item's answer, or copies an expected value.
```

##### forward.GENERATE_SYSTEM["officeqa"] (forward.py:60-75)
```text
You write practice questions about a real data table. You receive a guidance rule ("topic"), the source of the table and the table itself ("material"), copied verbatim from a Wikipedia page. Write as many distinct questions as "count" asks. Every question must be answerable from this table alone, by reading the right cells and computing with them, and must exercise the situation the guidance rule addresses. Do not mention any benchmark, dataset or test, and do not refer to the rule.

For each question give:
- "question": at most 600 characters; do not say how to round (the rounding instruction is added from "decimals");
- "formula": one arithmetic expression that computes the exact answer, in which every number is copied exactly from a cell of the table (a cell's minus sign is written as an operator; no other constant, such as 100 for a percentage); operators + - * / ** and parentheses; functions abs, min, max, floor, ceil, factorial, comb, perm, gcd, lcm; numbers written with digits and at most one decimal point (no thousands separators, currency signs, percent signs, exponents or variables);
- "decimals": an integer from 0 to 4, the number of decimal places the answer is rounded to;
- "answer": the formula's value rounded half away from zero to exactly that many decimal places, written with digits only, a decimal point when "decimals" is not 0, and a leading minus sign when negative.

Reply with one JSON object {"items": [...]} and nothing else.
```

##### forward.GENERATE_SYSTEM["livemath"] (forward.py:76-89)
```text
You write multiple-choice mathematics questions about a real definition or theorem. You receive a guidance rule ("topic"), the source of the passage and the passage itself ("material"), quoted verbatim from a Wikipedia page. Write as many distinct questions as "count" asks. Every question must be about this passage and must exercise the situation the guidance rule addresses. The solver sees only the question and the five options, never the passage: state in the question every definition and value it needs. Do not mention any benchmark, dataset or test, and do not refer to the rule.

For each question give:
- "question": at most 600 characters;
- "options": five distinct exact numbers (integers, decimals or fractions p/q, optionally signed), exactly one of them correct;
- "answer": the letter, A to E, of the correct option in the order given;
- "formula": one arithmetic expression whose value is exactly the correct option; operators + - * / ** and parentheses; functions abs, min, max, floor, ceil, factorial, comb, perm, gcd, lcm; numbers written with digits and at most one decimal point (no thousands separators, currency signs, percent signs, exponents or variables).

Reply with one JSON object {"items": [...]} and nothing else.
```

##### forward.CHECK_SYSTEM["officeqa"] (forward.py:92-96)
```text
You receive a data table and a question about it. Write one arithmetic expression that computes the exact, unrounded answer to the question from the table: every number copied exactly from a cell of the table (a cell's minus sign written as an operator); operators + - * / ** and parentheses; functions abs, min, max, floor, ceil, factorial, comb, perm, gcd, lcm; numbers written with digits and at most one decimal point (no thousands separators, currency signs, percent signs, exponents or variables). Reply with one JSON object {"formula": "..."} and nothing else.
```

##### forward.CHECK_SYSTEM["livemath"] (forward.py:97-100)
```text
You receive a passage quoted from Wikipedia, a multiple-choice question and an arithmetic expression. Decide whether the expression computes exactly the quantity the question asks for, given the passage. Reply with one JSON object {"verdict": "yes"} or {"verdict": "no"} and nothing else.
```

##### research.MATERIAL_REQUEST (research.py:114-120)
```text
officeqa: Find an English Wikipedia article on the topic of the rule below that contains a table of numbers (for example statistics, measurements, finances or results by year) from which questions requiring a calculation can be written.
livemath: Find an English Wikipedia article on the topic of the rule below that states a mathematical definition or theorem from which a question with a numerical answer can be computed.
```

##### protocol.PLACEBOS_SCREEN (protocol.py:105-114)
```text
1. When a task asks you to compose a haiku, keep the 5-7-5 syllable pattern across its three lines. Avoid end rhymes and do not give the poem a title unless one is explicitly requested.
2. If you are asked to give a color in hexadecimal notation, write the six hex digits in uppercase and prefix them with a single # sign, for example #1A2B3C; never use the three-digit shorthand.
3. When a recipe is requested, list every ingredient with its quantity before describing any cooking step, and group the steps under short headings for preparation, cooking and serving.
4. When translating a Latin inscription, keep personal and place names in their original Latin form and put any modern equivalent in parentheses after the first mention only.
```

##### protocol.PLACEBOS_CONFIRM (protocol.py:115-124)
```text
1. If a task asks for a limerick, use an AABBA rhyme scheme, keep the third and fourth lines shorter than the others, and end on the punch line rather than an explanation.
2. When asked to state a temperature in kelvin, write the number followed by a space and a capital K, never with a degree sign, for example 300 K rather than 300 degrees K.
3. If you are asked to record a chess move, use standard algebraic notation such as Nf3 or exd5, mark checks with + and checkmate with #, and omit move commentary.
4. When asked to describe a knitting pattern, state the needle size and yarn weight before the stitch sequence, and give each row on its own line with its stitch count.
```

## 5. Gaps and risks for route B in this area

1. **Executing model-written code is new.** coevo5's examiner "code" is a fixed 7-check library and "no model-written
   code is ever executed" (checks.py:3; examiner.py:3-5). Route B executes model-written procedures, applicability
   predicates, detectors and generator programs. Nothing in coevo5 sandboxes such code; the only sandbox is the
   SpreadsheetBench solver-program container (`RUNTIME["spreadsheetbench"]`: image sha, `timeout_seconds` 300,
   `memory_mb` 4096, `cpus` 1, protocol.py:345-354). Needs: no network, CPU/memory/time limits, determinism, no file
   access to pools, and no `private` fields in the procedure's inputs.
2. **JSON-object reply contract vs code.** `Roles.ask` requires one JSON object (F2); code inside JSON strings is
   escape-fragile. Observed validator attrition with plain text already: v3 analyst needed a 2nd attempt in 3/10
   stages (I-ds s1, s2, s5; dl prepare `analyst.attempts`), I-ds s2 had 3/5 rules `evidence_invalid`, and D13 found
   21/49 proposals died of small faults (results-and-lessons.md:146). Keep per-row validation; consider a fenced-code
   field convention validated by the program.
3. **Generated items: only the "truth by program" gate exists.** Evidence so far: v3 smoke 4/9 valid (F36: 2/5 rounds
   without material, 5/9 arithmetic-consistency drops; kept items trivial and unrelated to the rule; generator ignored
   "do not say how to round"), v1 smoke 9/12, v2 smoke 10/12 (project-status.md:226, 353); v3 formal run built no
   panel (F37); overnight E9: the empty scaffold gets 89% of generated items right (results-and-lessons.md:146 (3)).
   Route B's 20%-80% saturation gate and predictive-validity gate have no code; `forward.evaluate` lacks roots/logs
   (OfficeQA D2/D3 failures) and LiveMath symbolic verification. (inferred) Perturbing a REAL OfficeQA table needs a
   formula for the real item; validating that formula against the item's known reference on the unperturbed table
   is the natural anchor, but OfficeQA tables are text-rendered Treasury pages (no parsed cell grid like
   `research._Page` gives for Wikipedia HTML), so a number-perturber must keep totals/sub-totals consistent.
4. **Material/topic coupling caused the empty rounds.** The material request asks for a table "on the topic of the
   rule" (research.py:114-117); a SearchQA answer-form rule led to tables about US states, a discography and national
   parks (F36). Route B's design (perturb training items) removes this coupling; if research is kept for generation,
   topic-matching must not be the rule text.
5. **Detector acceptance has no anchored label for failure CATEGORIES.** Today's only anchored truth is official
   pass/fail (rubric revision is scored by BA against it, F21-F22). Failure categories come from the GLM diagnosis
   that SEES the reference (F24) -- a model judgment. A detector's precision/recall "on the target failure category"
   (design-v0 step 2) therefore needs either mechanically decidable categories (e.g. ALFWorld revisits from the
   trajectory, `noncompletion`/`malformed`/format codes) or a declared model-labelled reference set, reported as such.
   Also, BA acceptance is selection material, "no independent evidence that the examiner improved"
   (examiner.py:14-15); the same honesty applies to detectors scored on the trajectories they were written from.
6. **Acceptance instrument sensitivity.** Rule-level C1 passes a text against itself 14-17% of the time (D8), placebos
   move SearchQA by -9.8..+3.6 points (cal-1, much of it a JSON-answer scoring artifact; F47), same request different
   time windows ~6 points apart (results-and-lessons.md:146 (4)). Version-level acceptance therefore needs: the fixed
   scorer first, all four arms interleaved in one session (reuse F42), pre-registered minimum effects, and a placebo
   procedure whose format behaviour is identical to S's.
7. **Fresh-batch supply.** Training pools: SearchQA 600, OfficeQA 74, LiveMath 283, SpreadsheetBench 120 nominal
   (qualified fewer), ALFWorld 57 (`POOLS`, protocol.py:63-64); v3 used ALL of OfficeQA and ALFWorld in one training
   execution and the gate re-used the same items (focal panel = training items, step.py:737-738). Route B wants a run
   batch and a separate once-used acceptance batch per step, plus regression/self-test material from generated items
   only -- OfficeQA ~37+37 and ALFWorld ~28+29 items cannot resolve the 10-point effects design-v0 names (inferred
   from sizes; the overnight report already says OfficeQA 74 / ALFWorld 57 "only >= 9-12 visible" using ALL items).
8. **Leakage for code is unspecified.** Current checks are text-surface checks (F48); code can carry answers as
   literals, as regexes/dict keys on question text, or via predicates matching one task. Static AST literal checks +
   adjudication of descriptions + a shell guarantee that `private` is never passed (today `answer_of` puts `private`
   in every answer dict, F10) are needed; also check generated items derived from training items do not leak
   test-pool content (generators must read only the training pool).
9. **Replay tests prove determinism, not repair.** A procedure "must run through the failure records it claims to
   fix", but the solver is stochastic (`cells._replay` only re-executes a stored reply, cells.py:139-149). A replay
   can show the procedure's output on recorded inputs (e.g. D3's state tracker on 228 recorded episodes) and zero
   crashes, not that the solver would now succeed; success is only measured in acceptance.
10. **Cross-bench format conflict persists in the seeds.** All five instructions are rendered into every prompt
    (F55) and each contains format advice for its own bench (2.10b); E4/E9's negative transfer was format conflict
    (design-v0 §一 4). Route B's router can show only the active bench's card; if it keeps the v3 whole-Skill
    rendering, the conflict stays inside the frozen part.
11. **No role ever proposed cross-bench placements in v3.** All SearchQA/OfficeQA-stage proposals were "local"; the
    transfer slot answered "none" with reasons like "clue-style answer form ... no counterpart" (dl prepare
    `analyst.transfer`). Expect few "通用" procedures outside the table/number cluster (consistent with design-v0's
    first risk).
12. **Budgets for code roles.** Role ceilings exist per call type (2.11) and per-step token scopes (`LEARNING_CAP`);
    code-writing and detector/generator calls are larger (design-v0 cites ~5,000 tokens for a recorder) and need
    their own ceilings and retry policy (today invalid = consumed, never retried, except analyst/self-test/rubric x2).

## 6. Open questions for the designer (not verifiable from code/data)

1. Which text is a "task card" in route B: `texts.CARDS` (agent/human-written public descriptions, 2.10a) or the five
   GLM-5.3-written instructions that were chain I's seeds (2.10b)? design-v0 says "人写的说明" (human-written) and "和
   v3 一样"; in v3 the I chains and cal-1's `ids-full` arm ("I-ds initial Skill: `Skill.seeded(instructions)`",
   docs/handoff/cal1-registration-20261020.md:42) used the GLM-written instructions. This also fixes what the
   "只有任务卡" acceptance arm contains.
2. Is the card shown only for the active bench (router) or all five rendered together as in v3 (F55)? And do the
   format guardrails replace or coexist with the format bullets inside the instructions?
3. What is the ground truth for detector precision/recall (model diagnosis with reference, mechanical definitions,
   or only pass/fail)? Which held-out trajectories (proposal/check halves of the same run batch, or another batch)?
4. Is the reference-free rubric judge (and the general rubric) dropped entirely? Today its only effect is the
   diagnosis code list (F21, F24); route B's detectors would supersede it.
5. Is the research role kept (Wikipedia + pinned archive incl. openpyxl/LibreOffice/Python docs), e.g. for the
   engineer? design-v0 does not mention it.
6. Predictive validity: "连续两次不一致的出题程序作废" -- with one acceptance per bench per step, when can a generator
   have two consecutive disagreements (it would need to be reused across steps/benches)?
7. SearchQA paraphrase probes ("换说法、答案不变"): who certifies that a paraphrase keeps the answer -- a model? That
   would be the one non-program anchor in the examiner side.
8. Batch arithmetic for OfficeQA (74) and ALFWorld (57): how are run vs acceptance batches split, is any item reused,
   and are the regression panels kept (they are drawn from the same pools, data.py:199-205)?
9. Version-level acceptance of several new procedures at once: is there any per-procedure attribution (ablation)
   before labelling a procedure "通用" vs "仅本 bench", or is the label purely from activation logs?
10. Which sandbox runs procedures/detectors/generators, and may a procedure make extra model calls (the "精确计算" tag
    loop implies a second solver call inside one cell; the placebo must then match the call count)?
