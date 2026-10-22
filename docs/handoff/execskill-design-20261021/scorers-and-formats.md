# Judging area -- scorers, format guards, scorer v2, generated-task truth (route B "judge" module)

Status: COMPLETE (2026-10-21). Read-only; nothing executed except read-only ls/stat/find/sha256 on dl.
Author: read-only code-reader subagent, 2026-10-21.
Area: judging. skillopt/coevo5/scoring.py, skillopt/coevo5/checks.py, skillopt/envs/searchqa/evaluator.py,
skillopt/envs/officeqa/evaluator.py, LiveMath scoring path, SpreadsheetBench native scorer + recalc image,
skillopt/coevo5/qualify.py ("reference-qualified"), ALFWorld success, official vs lenient,
D9 feasibility report (JSON answers 0/364), direction-recommendation "scorer v2", REQUIRED_FORMAT / contract-first-v2.

## 1. Scope and files read
Convention: "verified" = read at the cited lines; "inferred" = my reading of the code, not executed (no pytest, no model
calls, nothing run). Paths are repo-relative to /Users/dulin/Documents/Paper/SkillOpt unless absolute; "dl" paths are on
the Linux machine (read-only ls/cat/find/python -c hashing only). No test/holdout/final data file was opened.

| file | lines | read |
|---|---|---|
| skillopt/coevo5/scoring.py | 93 | full |
| skillopt/coevo5/checks.py | 105 | full |
| skillopt/envs/searchqa/evaluator.py | 100 | full |
| skillopt/envs/officeqa/evaluator.py | 46 | full |
| skillopt/envs/livemathematicianbench/evaluator.py | 62 | full (legacy env path; NOT the coevo5 scorer) |
| skillopt/continual_eval/backends.py | 783 | full |
| skillopt/continual_eval/code_delivery.py | 83 | full |
| skillopt/continual_eval/sheet_numeric_adapter.py | 151 | full (the v7 scorer `qualified_lo_recalc_v7_v1`) |
| skillopt/continual_eval/sheet_recalc.py | 886 | 1-50, 198-248, 395-440, 500-510, 579-616 |
| skillopt/continual_eval/sheet_recalc_v7.py | 180 | 1-37 + def list |
| skillopt/continual_eval/spreadsheet_compat.py | 265 | 1-40, 203-265 |
| skillopt/envs/spreadsheetbench/evaluator.py | 317 | 1-84 (+ def list) |
| skillopt/coevo5/qualify.py | 144 | full |
| skillopt/coevo5/outcomes.py | 402 | full |
| skillopt/coevo5/cells.py | 263 | 97-236 |
| skillopt/coevo5/protocol.py | 357 | 1-160, 320-357 |
| skillopt/coevo5/texts.py | 183 | full |
| skillopt/coevo5/smoke.py | 435 | 71-77, 270-320 |
| skillopt/coevo5/step.py | 861 | 150-190 |
| skillopt/coevo5/examiner.py | 516 | 470-516 |
| skillopt/coevo5/forward.py | 443 | 1-345 |
| skillopt/envs/alfworld/vendor/alfworld_envs.py | 221 | 1-80 |
| skillopt/continual_eval/datasets.py | 507 | 18-60, 160-200 |
| skillopt/continual_eval/runtime/{Dockerfile, Dockerfile.sheet-recalc, requirements-native.txt} | 13/9/10 | full |
| tests/test_coevo5_core.py | 404 | 120-170 (lenient/check cases; NOT run) |
| docs/handoff/direction-recommendation-20261021.md | 191 | 1-70, 96-104, source table 134-190 |
| docs/handoff/coevo5-registration-v3-delta-20261019.md | 387 | 60-100 |
| docs/handoff/feasibility-20261021/D5/critic-result.json | 8 | refuted_claims, missing, notes_cn |
| docs/handoff/feasibility-20261021/D9/result.json (+critic) | 20 | structure + JSON/format grep (no report.md exists in D9/) |
| docs/handoff/feasibility-20261021/D6/report.md | 865 | 1-40, 280-310 |
| session scratchpad prototypes: feas/E7/run2/json_counterfactual.py, feas/E10-critic/scripts/ceiling_by_scorer.py, feas/E10/scripts/json_aware.py | 40/62/48 | the JSON-extraction parts |
| dl: /etc/docker/daemon.json, /data/docker/image/overlay2/{imagedb, repositories.json}, /root/continual-fivebench-20261003-f-q23/{qualification,protocol}.json (ls + sha256 only), ALFWorld train dir (file count only) | - | read-only |


## 2. Facts
(All "verified" = read in the file at the cited line in the working tree of branch research/active-evidence-skill-evolution on 2026-10-21;
"inferred" is marked explicitly.)

### 2a. Official (frozen) scorers -- `skillopt/continual_eval/backends.py` is THE scoring entry
- F1 (verified) Module identity: `VERSION = "continual-eval-native-backends-v1"`, `PROTOCOL = "continual-eval-native-v1"`
  (skillopt/continual_eval/backends.py:30-31). Benchmarks: `BENCHMARKS = {"searchqa", "korbench", "bigcodebench",
  "spreadsheetbench", "alfworld", "livemath", "officeqa"}` (:32); `ANSWER_TAG_BENCHMARKS = {"livemath", "officeqa"}` (:34).
- F2 (verified) Entry point `score(benchmark, public, private, prediction, *, runtime=None)` (:517) -- "Hidden audit only;
  never call the model". A prediction whose `status != "available"` is returned as
  `_unknown(prediction.get("reason", ...))` (:520-521), i.e. `{"status": "unknown", "score": None, "metrics": {}, "reason": ...}`
  (:65-66). Any `KeyError/ValueError/TypeError/OSError/BadZipFile` inside scoring -> `_unknown("native_scoring_input_error:<Exc>")` (:565-566).
  Return shape on success: `{"status": "pass"|"fail", "score": float, "reason": str, "metrics": {...}}`.
- F3 (verified) SearchQA official = repository EM. `score` calls `skillopt.envs.searchqa.evaluator.evaluate(output, answers)` on the
  WHOLE reply (:524-531); status pass iff `result["em"]`; reason `"repository_searchqa_native_em"`; metrics `em, f1, sub_em`.
  `evaluate` extracts the LAST `<answer>...</answer>` (re.DOTALL|IGNORECASE), FALLING BACK to the last non-empty line, then the
  whole stripped text (skillopt/envs/searchqa/evaluator.py:28-39). EM = SQuAD normalisation equality against any gold
  (:19-25, :42-47): lowercase, drop ALL `string.punctuation`, remove articles a/an/the, collapse whitespace.
  Consequence: a reply `{"answer": "Paris"}` without a tag normalises to "answer paris" -> EM 0 (inferred from :22 + :36-38).
- F4 (verified) OfficeQA official = `_score_answer_tag("officeqa", output, private["answer"])` (:532-533, :491-514): text of the
  LAST answer tag (empty string if none); `valid = bool(text)`; `ok = valid and exact_match(text, answer) == 1.0`; reason
  `"officeqa_native_normalized_em_on_last_answer_tag"`; metrics `{"em": float(ok), "invalid_format": float(not valid)}`.
  NO numeric tolerance (docstring :496). `exact_match` uses `normalize_answer` (skillopt/envs/officeqa/evaluator.py:11-21):
  lowercase+strip, delete ",", delete punctuation except `0-9 . -` and `%`, delete words
  `million|millions|billion|billions|dollars|dollar|nominal`, collapse whitespace. So "1,234.5" == "1234.5", but "1234.50" !=
  "1234.5", "$1234.5" == "1234.5" ("$" is punctuation), "12%" != "12", "1.2 thousand" != "1200".
- F5 (verified) LiveMath official = `_score_answer_tag("livemath", ...)` (:501-506): last tag text, upper-cased, ONE trailing
  `.`, `)` or `:` stripped; valid iff exactly one char in "ABCDE"; ok iff equal to `private["answer"]` (the letter; dataset
  requires it in `LIVEMATH_LABELS`, skillopt/continual_eval/datasets.py:42, :173). Reason `"livemath_strict_letter_in_last_answer_tag"`.
  A missing tag or "(B)" or "B. 42" is a delivered WRONG answer (`invalid_format` 1.0), never unknown (docstring :492-493).
- F6 (verified) ALFWorld official: `score` requires `output["won"]` to be a bool, else `_unknown("missing_native_environment_success")`
  (:558-563); score `float(won)`, metrics `{"success", "steps"}`, reason `"alfworld_native_won"`. `won` is the simulator's
  `infos[0]["won"]` after each `env.step([action])` (:762-770); a step without the `won` key -> prediction unknown
  `"native_won_signal_missing"` (:765-767). Episode loop: `max_steps` default 50, int in 1..150 (:727-729); prompt
  `"Act in the text environment. Return a single action inside <action>...</action>."` (:730); action = first
  `<action>(.*?)</action>` (re.S, case-SENSITIVE) else the whole stripped reply (:752-753); empty or >1000 chars ->
  prediction unknown `"invalid_action_format"` (:754-756). Any exception -> `"alfworld_environment_error:<Exc>"` (:774-776);
  cleanup failure overrides with `"alfworld_cleanup_unconfirmed"` (return inside `finally`, :777-783).
- F7 (verified) Model-reply admission `_response` (:90-111): finish_reason `length`/`max_tokens` -> no reply, reason
  `"model_response_truncated"` (:105-106) => prediction `unknown` => score `unknown` (NOT wrong) for every benchmark;
  filtered/network errors are unknown under the closed retry policies (:99-104); blank or > `MAX_RESPONSE = 262144` bytes ->
  unknown (:36, :109-110). Exception for the two answer-tag benches only: a provider-completed blank reply with reported
  usage becomes `response = ""` (`"model_response_completed_without_text"`) and is scored WRONG (:418-422, :475-488).
- F8 (verified) The scorer input `output` is the raw reply for searchqa/korbench/livemath/officeqa (:436); SpreadsheetBench
  output is `{"code": <program>, "cases": [<native generate receipt per public input file>]}` (:437-452); ALFWorld output is
  `{"won": bool, "steps": int}` plus top-level `trace` (:771-773).


### 2b. Lenient (descriptive) scorer and the fixed format checks
- F9 (verified) `skillopt/coevo5/scoring.py` is the ONLY lenient scorer in the repo and is "descriptive only, never used by the
  gate or by any claim" (skillopt/coevo5/scoring.py:1). Entry `lenient(benchmark, private, prediction)` (:76-93) returns
  True/False, or None when the prediction is not `status == "available"`, the bench is not in
  `("searchqa", "officeqa", "livemath")`, or the output is not a str (:78-82). No last answer tag -> False (:83-85) -- i.e. a
  JSON-only reply is still False under "lenient". Rules (all on the LAST tag only, via `checks.last_answer`):
  - searchqa (:30-41): SQuAD-normalised tag tokens equal a gold, or contain the gold as a contiguous token run while
    `len(given) <= len(gold) + MAX_EXTRA_WORDS` with `MAX_EXTRA_WORDS = 3` (:27).
  - officeqa (:44-68): gold parsed by `_number` after removing `UNIT_WORDS` (:25-26:
    `million|millions|billion|billions|thousand|thousands|dollars|dollar|nominal|percent|per\s+cent|usd`), "$", "%", ","
    and requiring `[-+]?\d+(?:\.\d+)?`; the tag must contain EXACTLY ONE `NUMBER` match and equal the gold as `Decimal`
    (exact, no tolerance; "1234.50" == "1234.5" here, unlike official). Non-numeric gold: `_squeeze` compare (:54-61).
  - livemath (:71-73): exactly one standalone letter A-E anywhere in the tag text (so "(B)" or "Option B" passes; official fails them).
  Docstring warns the lenient-minus-official gap is not "the formatting part" because dropping "%"/units changes meaning (:12-13).
- F10 (verified) `skillopt/coevo5/checks.py` is the fixed library of host-run format checks ("no model-written code is ever
  executed", :3-4). Constants: `ANSWER = re.compile(r"<answer>(.*?)</answer>", re.S | re.I)` (:12),
  `NUMBER = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")` (:13). `last_answer(output)` -> stripped text of the last
  tag or None (:16-21). Registry `CHECKS` (:74-82): `answer_tag_present`, `answer_single_letter`,
  `answer_pure_number(allow_percent: bool)`, `answer_no_percent`, `answer_no_letters`, `answer_max_words(n: int 1..50)`,
  `code_present` (output is a dict with non-blank `code`). Each returns True/False/None (None = not applicable, e.g. no tag).
  `validate(spec)` requires `{"name", "params"}` exactly matching the schema, raising via `continual_eval.core.require` (:85-97);
  `run(spec, output)` (:100-105).
- F11 (verified) The frozen per-bench format guard of coevo5 v3 is `REQUIRED_FORMAT` (skillopt/coevo5/protocol.py:126-128):
  ```
  REQUIRED_FORMAT = {"searchqa": ("answer_tag_present",), "officeqa": ("answer_tag_present",),
                     "livemath": ("answer_single_letter",), "spreadsheetbench": ("code_present",), "alfworld": ()}
  ```
  comment: "§5.5 C3: the fixed per-bench format each answer must keep; the rubric's evolving items never change it." Used at
  skillopt/coevo5/step.py:179, skillopt/coevo5/examiner.py:485 and :513, skillopt/coevo5/smoke.py:279-310 (see F-section 2d).
- F12 (verified) `scoring.lenient` has NO production caller: a repo-wide grep for `lenient(` / `from .scoring` / `coevo5.scoring`
  over skillopt/, scripts/, tests/ finds only tests/test_coevo5_core.py:7, :162-168. So in coevo5 v3 the "lenient" score is
  defined and unit-tested (examples at tests/test_coevo5_core.py:142-159, e.g. officeqa gold "4.815%" vs tag "4.815" -> True;
  livemath "(C) 42" -> True; searchqa "The city of Paris" -> True) but never recorded in cells or reports (inferred from the grep).

### 2c. "Official" vs "completion-aware" (final) outcome per cell -- `skillopt/coevo5/outcomes.py`, `cells.py`
- F13 (verified) "Every cell keeps the official result (the frozen scorer's output, unchanged) next to the completion-aware one"
  (skillopt/coevo5/outcomes.py:4-5). The cell record (skillopt/coevo5/cells.py:221-230) stores
  `"final": {**verdict, "token": verdict.token}` and `"official": {"status": scored["status"], "reason": scored["reason"]}`
  (or `{"status": None, "reason": "not_scored:decided_before_scoring"}`); prediction and score bodies are stored by hash in
  `artifacts/<sha>.json` with summaries (:97-119). The official scorer is called as
  `backends.score(benchmark, task["public"], task["private"], prediction, runtime=runtime)` (:152-163); SpreadsheetBench gets a
  per-scoring `runtime["_score_context"]` with `artifact_dir = <store>/host_only/scorer_artifacts/<position>` (:158-161).
- F14 (verified) The decision table `classify(benchmark, prediction, score=None, receipts=(), *, refused=False, spent=frozenset())`
  returns `Verdict(outcome, kind, reason, row, remedy=None, exhausted=None)` (skillopt/coevo5/outcomes.py:123-138, :185-204).
  Where it DIFFERS from the official scorer:
  - row 5: truncation / filter / empty (`NONCOMPLETION_REASONS = {"model_response_truncated", "model_response_filtered",
    "empty_or_oversized_model_response"}`, :71-72; or last-receipt errors `finish_length`, `finish_max_tokens`,
    `finish_sensitive`, `finish_content_filter`, `content_missing`, `empty_content`, :69-70) -> `FAIL`/`noncompletion`
    (:261-262, :294-295), whereas `backends.score` returns unknown for these (F7).
  - row 6: `invalid_action_format` (ALFWorld) and `code_delivery:*` (SpreadsheetBench) -> `FAIL`/`malformed` (:75-76, :296-297).
  - row 4: undelivered receipts -> UNKNOWN/infrastructure (:259-260); rows 7-8 ALFWorld env errors -> UNKNOWN/infrastructure,
    with a RESTART remedy only when `calls == 0` (:298-303); row 10: scored pass/fail (:201-203); row 11: anything else
    UNKNOWN/unclassified (:204, :304). Rows 1-3 raise `ConfigurationError`, `BudgetStop`, `CleanupUnconfirmed` (:231-248).
  - row 9 SpreadsheetBench (:307-402): per case 9a generation (`missing_output` or `output_workbook_size_limit` -> FAIL
    artifact_defect; `native_exception:*` -> FAIL program_defect; `native_timeout` -> REEXECUTE then FAIL program_defect),
    9b workbook structure (`[Content_Types].xml` + `xl/workbook.xml` present, opens in openpyxl, >=1 worksheet, size bounds),
    9c scorer case status, 9d all-cases-must-pass.
  `Verdict.token` maps unknown+artifact to `"unknown_artifact"` (:133-138).

### 2d. Format guards: where they live, exact text
- F15 (verified) Solver prompt assembly `backends.solve(benchmark, public, skill_text, call, *, runtime=None)`
  (skillopt/continual_eval/backends.py:364-453): `system = "Solve the supplied task using only the supplied public information."`
  (:379); Skill block `"\n\nFrozen skill guidance (use only where applicable):\n" + skill_text` only when non-blank (:380);
  contracts (:381-390):
  - searchqa, officeqa: `"\nReturn the concise final answer inside <answer>...</answer>."`
  - livemath: `LIVEMATH_CONTRACT = "\nChoose exactly one of the listed options and return only its letter inside <answer>...</answer>."` (:35)
  - spreadsheetbench under contract-first-v2: `SHEET_CONTRACT_V2` (:53-56) =
    "\nReturn one complete Python program in a ```python code block whose opening fence starts its own line. The program
    reads input.xlsx and saves output.xlsx with the answer at the required answer position. A formula alone is not an
    answer: when the task asks for a formula, the program writes it into the answer cells."
  - spreadsheetbench otherwise: `"\nReturn one complete Python program in a ```python code block."` (:390)
  - korbench: `"\nApply the given rules; enclose the final answer in [[...]]."` (:386)
  Layout: `if runtime.get("prompt_layout") in CONTRACT_FIRST_LAYOUTS: system += contract + guidance` else
  `system += guidance + contract` (:391-394). `CONTRACT_FIRST_LAYOUT = "contract-first-v1"`, `CONTRACT_FIRST_LAYOUT_V2 =
  "contract-first-v2"` (:47-52). `_layout_supported` rejects any layout for ALFWorld (:359-361) -> `"invalid_prompt_layout"`.
  User message = `json.dumps(view, ensure_ascii=False)` of the public view only (:417); `_PUBLIC` fields (:57-62).
  ALFWorld's contract is fixed and FIRST already: `"Act in the text environment. Return a single action inside
  <action>...</action>."` then `"\nFrozen skill guidance (use only where applicable):\n" + skill_text` (:730-732).
- F16 (verified) coevo5 v3 freezes `PROMPT_LAYOUT = "contract-first-v2"` for searchqa/officeqa/livemath/spreadsheetbench
  (skillopt/coevo5/protocol.py:341-344). Why v2: the 10/19 format check failed for the EMPTY Skill on SpreadsheetBench
  (17/20: 2 replies gave an Excel formula instead of a Python program, 1 glued the opening fence to the sentence end) and the
  owner chose to add the sentence for every arm (docs/handoff/coevo5-registration-v3-delta-20261019.md:72-85). The second check
  (smoke-2) found LiveMath empty-Skill 16/20 (3 bare letters without tag, 1 `\boxed{A}`) and the owner floored only E and I
  (:90-97; `smoke.FORMAT_FLOORED = ("E", "I")`, skillopt/coevo5/smoke.py:76).
- F17 (verified) Format-guard consumers in coevo5: (a) gate C3 `step.violations(store, cells, arm, items, bench, *, unknown_counts)`
  (skillopt/coevo5/step.py:160-181): a cell violates when its final token is unknown (counted with weight `unknown_counts`),
  its kind is `malformed`, or any `checks.run({"name": n, "params": {}}, output) is not True` for n in `REQUIRED_FORMAT[bench]`
  (a truncated reply has output None -> check returns None -> violation); per-item share of runs, summed.
  (b) examiner diagnosis: a failed answer that fails a REQUIRED_FORMAT check is coded with the check's name, "by": "format",
  before any model call (skillopt/coevo5/examiner.py:481-487). (c) smoke format check `format_check(setting, root, chain_name)`
  with `FORMAT_ITEMS = 20`, `FORMAT_FLOOR = Fraction(9, 10)`, `FORMAT_MARGIN = Fraction(1, 20)` (skillopt/coevo5/smoke.py:71-77, :275-313).
- F18 (verified) The task cards (`texts.CARDS`, skillopt/coevo5/texts.py:31-96) quote the contracts and the public metric.
  Two card statements differ from the code: the SearchQA card says "Anything else in the reply is ignored" (:40) but the
  official extractor falls back to the last non-empty line when no tag exists (F3); the ALFWorld card says an empty or
  >1000-char action "counts as failed" (:94-95) -- true for coevo5's completion-aware verdict (row 6, F14) but the frozen
  backend returns prediction unknown. `texts.solver_cards` swaps the SpreadsheetBench card's quoted v1 contract
  `SHEET_CONTRACT_QUOTE` for `SHEET_CONTRACT_V2` for the roles' view only (:114-129).

### 2e. SpreadsheetBench native scorer, recalc engine, reference qualification
- F19 (verified) Generation: SpreadsheetBench `solve` extracts the program (with `code_extraction_version =
  "explicit-python-fences-v1"`, `code_delivery.extract_python`, skillopt/continual_eval/code_delivery.py:21-83: exactly one
  ```python/```py block wins; two explicit Python blocks -> `multiple_python_blocks`; else a sole unlabelled block or a
  fully unfenced reply; unclosed/odd fences -> unknown reasons) and then executes it ONCE PER PUBLIC INPUT FILE in the
  generation container via `_native({"operation": "spreadsheet_generate", ...}, runtime)` (backends.py:426-452). An
  extraction failure is prediction unknown `"code_delivery:<reason>"` (:431-432) which coevo5 maps to FAIL/malformed (F14).
  A bare Excel formula reply (no fences) is taken as whole_unfenced_response code and fails at execution (inferred from
  code_delivery.py:74-75 + outcome 9a `native_exception:*`); a formula in a ```excel fence -> `no_unambiguous_python_deliverable`
  (inferred from :72-77).
- F20 (verified) Frozen runtime (skillopt/coevo5/protocol.py:345-354): generation image
  `"sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd"`, `timeout_seconds 300`, `memory_mb 4096`, `cpus 1`,
  `spreadsheet_preview_version "public-formula-preview-v1"`, `_stop_on_cleanup_failure True`,
  `spreadsheet_scorer "qualified_lo_recalc_v7_v1"`, `recalculation = {"image":
  "sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790", "timeout_seconds": 120, "qualification_path":
  "/root/continual-fivebench-20261003-f-q23/qualification.json", "qualification_sha256": "f5bc90df...6f54c",
  "qualification_hash": "cc4ab804...b9bf"}`. Generation container flags: `--network=none --read-only --user=65534:65534
  --cap-drop=ALL --pids-limit=128 --memory=<m> --tmpfs=/tmp...` (backends.py:169-178).
- F21 (verified) v7 scoring `sheet_numeric_adapter.score(public, private, prediction, *, runtime, replay_only=False)`
  (skillopt/continual_eval/sheet_numeric_adapter.py:87-151): `qualified_engine(runtime)` re-validates the 23-control
  qualification offline (imports `scripts.replay_sheet_v6`, :28-74 -- a scorer dependency living in scripts/); requires
  `private["asset_sha256"][reference] == sha(reference)` for every reference (:93-94); per case
  `sheet_recalc.evaluate_pair(pred, ref, answer_position, engine, root / "recalculations")`; status hard-all-cases,
  reason `"qualified_numeric_recalculation_hard_all_cases"`, metrics include `"excel_equivalence_proven": False`; writes
  `started.json` / `result.json` under `_score_context.artifact_dir` and refuses an interrupted position (:104).
- F22 (verified) `sheet_recalc.evaluate_pair` (skillopt/continual_eval/sheet_recalc.py:579-615): BOTH the reference and the
  prediction workbook are recalculated independently by LibreOffice in a fresh networkless read-only container
  (`Recalculator`, :395-408: memory 1024 MB, 1 cpu, macros never, links no_update); receipts cached by input hash; a failed
  recalculation or read-view check of either side -> unknown `"<role>:<reason>"`; the recalculated reference must still match
  its ORIGINAL cached values (`compat.evaluate(recalc_ref, original_ref, ...)`), else unknown
  `"reference_native_cache_drift_or_unavailable"` (:608-612); finally `compat.evaluate(recalc_pred, recalc_ref, "", answer_position)`.
  `screen(path)` (:198-246) returns unknown reasons for macros/external links, `FORBIDDEN_FUNCTIONS` (:46-48:
  WEBSERVICE, HYPERLINK, RTD, DDE, CALL, REGISTER.ID, INDIRECT, NOW, TODAY, RAND, RANDBETWEEN, RANDARRAY), structured refs
  (`[`, `|`), and any `_xlfn.`/`_xlws.` extended function (:238-241) -- so XLOOKUP/IFS/TEXTJOIN-style formulas are unscorable.
- F23 (verified) Cell comparison = official SpreadsheetBench port (skillopt/envs/spreadsheetbench/evaluator.py:1-71):
  numbers and numeric strings -> `round(float(v), 2)` ("a fixed 2-decimal quantization (NOT a tolerance)"), bool -> float,
  `datetime.time` -> `str(v)[:-3]`, datetime -> Excel serial day rounded to 0 decimals, `""` == None, otherwise
  `type(v1) is not type(v2)` fails. `spreadsheet_compat.evaluate(pred_path, gold_path, instruction_type, answer_position)`
  (skillopt/continual_eval/spreadsheet_compat.py:203-265, `VERSION = "spreadsheetbench-official-quote-and-string-cache-v1"`):
  every target cell compared with `_compare_cell_value`; formula cell without cache -> unknown
  `"unavailable: formula cache not established"`; missing sheet -> `missing_output`; first mismatch -> `failed`.
- F24 (verified) "Reference-qualified" (skillopt/coevo5/qualify.py:1-8, :38-43, :85-131): each item is scored with its OWN
  reference workbooks submitted as the answer (`reference_prediction(task)`), `PASSES = 2` times in fresh directories with
  the frozen v7 scorer (`require(runtime.get("spreadsheet_scorer") == "qualified_lo_recalc_v7_v1")`); an item qualifies only
  if both scorings pass every case; exclusions are categorised `CATEGORIES = ("reference_recalculation_failed",
  "reference_cache_mismatch", "read_view_unverifiable", "other")` (:27, :46-52); record version
  `VERSION + "-sheet-qualification"`, `model_calls: 0`. `SHEET_MIN_QUALIFIED = 30` (protocol.py:68).
- F25 (verified on dl, read-only, 2026-10-21) Both pinned images are present on the new machine (docker `data-root` is
  `/data/docker`, /etc/docker/daemon.json): `/data/docker/image/overlay2/imagedb/content/sha256/0a0a5dcb7dd4...0f0dd` tagged
  `evolve-skill-native:smoke-20260928` and `.../f7f6f598c4f0...c4d790` tagged `evolve-skill-sheet-recalc:20260930-offline`
  (`/data/docker/image/overlay2/repositories.json`). `/root/continual-fivebench-20261003-f-q23/qualification.json` exists
  (11479 bytes, 2026-10-03 18:58) and its sha256 equals the pinned `f5bc90dfc435cf0ddf9cfa8179237568edb605673dd7f8e08a2658815da6f54c`.
  Image recipes: skillopt/continual_eval/runtime/Dockerfile.sheet-recalc:3-9 (`python:3.11-slim` + `libreoffice-calc
  python3-uno`, user 65534); skillopt/continual_eval/runtime/Dockerfile:1-13 with requirements-native.txt pins
  `sympy==1.13.3`, `openpyxl==3.1.5`, `numpy==1.26.4`, `pandas==2.2.3`, `antlr4-python3-runtime==4.11` (sympy is available
  inside the sandbox).

### 2f. ALFWorld success
- F26 (verified) Success is the simulator's own `infos["won"]` from the pip-installed `alfworld` package environment
  (`get_environment(env_type)(config, train_eval=...)`, skillopt/envs/alfworld/vendor/alfworld_envs.py:53-62; the vendor's
  reward is `10.0 * float(info['won'])`, :22-27). `_new_alfworld(public, runtime)` (skillopt/continual_eval/backends.py:666-698)
  only accepts an existing `game.tw-pddl` under the frozen `ALFWORLD_DATA` root (env var must equal
  `runtime["alfworld_data"]`, :670-677), split one of train / eval_in_distribution / eval_out_of_distribution (:679-683),
  `max_steps` written into the per-worker config copy (:684-696). coevo5 runtime: `alfworld_data
  "/root/continual-alf-prep-20260928/data"`, `alfworld_split "train"`, `max_steps 50`, `seed 42` (protocol.py:355-356).
  On dl, `/root/continual-alf-prep-20260928/data/json_2.1.1/train` holds 3553 `game.tw-pddl` files (counted with find, no
  file read) -- the pool from which route B could sample "new environments" without writing PDDL.

### 2g. Generated-task truth that already exists in coevo5 (forward panels)
- F27 (verified) skillopt/coevo5/forward.py:11-13: "Validity is decided by exact rational arithmetic (`evaluate`), never by a
  model alone". `evaluate(formula)` -> `Fraction`, AST-restricted: literals `\d+(?:\.\d+)?`, unary +/-, `+ - * / **` (integer
  exponent |e|<=10), parentheses, `FUNCTIONS = ("abs", "min", "max", "floor", "ceil", "factorial", "comb", "perm", "gcd",
  "lcm")`, limits `MAX_FORMULA_CHARS = 300`, `MAX_FORMULA_NODES = 100`, `MAX_FACTORIAL = 100`, `MAX_COMBINATORIAL = 1000`,
  `MAX_BITS = 4096` (:35-51, :196-203). `rounded(value, decimals)` rounds half away from zero to exactly 0-4 decimals,
  no separators (:213-220, `MAX_DECIMALS = 4`).
- F28 (verified) Generated item shapes (scored afterwards by the SAME official scorers): OfficeQA-style
  `{"public": {"question": q + " Round your answer to N decimal place(s).", "context": "Source: Wikipedia, <title> (revision
  <id>)\n" + text}, "private": {"answer": rounded(value, decimals)}}` -- every formula literal must be a table cell
  (`literal_not_in_table`), the stated answer must equal the rounded value (:278-302); LiveMath-style `{"public":
  {"question", "choices": "A. ...\n\nB. ..."}, "private": {"answer": letter}}` with five distinct exact numeric options of
  which exactly one equals the formula value (:305-342). Plus one model consistency-check call per item (:363-381).
  Trap for route B (inferred from F4 + :296): with `decimals = 2` the reference is e.g. "12.50", and the frozen OfficeQA EM
  marks "12.5" wrong; the question's rounding sentence is the only guard.
- F29 (verified) D6 (docs/handoff/feasibility-20261021/D6/report.md:14-22, :295-303): program-keyed LiveMath-style variants
  had keys 52/52 correct after an independent audit; advice: assign the key letter from a balanced schedule, exclude
  integral/series families sympy leaves unevaluated, or validate closed forms numerically at 50 digits.

### 2h. The JSON-answer problem (0/364) and the status of "scorer v2"
- F30 (verified) Source of "0/364": D5's critic, not D9: "replies wrapped as {"answer": ...} score 0 in every arm (0 passes
  out of 364). In 414 of 424 JSON replies, the identical answer string also appears inside an <answer> tag on the same item,
  and in 324 of those 414 the tagged version passed" (docs/handoff/feasibility-20261021/D5/critic-result.json,
  `refuted_claims` item 1; the ledger cites it as S12 "FS D5/critic-result.json #1",
  docs/handoff/direction-recommendation-20261021.md:143). D9 has no report.md (the folder holds only result.json and critic-result.json);
  neither contains "364", and "json" occurs there only in file names (grep) -- D9's relevant measurement is "H. Format drift": the scaffold's no-tag rate rose from 0.8% to
  6.0%/4.4% and 8.2-9.5% while the task card stayed 0-0.8% (D9/result.json `evidence` H).
  Mechanism (verified in code): SearchQA with no tag falls back to the last line (F3), so `{"answer": "Paris"}` is scored as
  "answer paris"; OfficeQA/LiveMath without a tag are invalid_format wrong (F4, F5).
  Rescoring the JSON replies post hoc moved control:3 from -0.100 to -0.005 and the learned rule s1-r1 from -0.0275 to
  +0.064 (D5 critic item 2) -- i.e. the format channel dominates measured differences on SearchQA.
- F31 (verified) Scorer v2 is ONLY A PROPOSAL. direction-recommendation-20261021.md:46 ("评分器加'也认 JSON 答案、格式错误与对错
  分开记'，登记为评分器 v2，只用于事后重读与并列报告；v3 的结论不变"), :53 (register it, then re-read cal-1 and v3 training
  cells), :58 (Codex review), :65-69 (official primary, JSON score reported alongside; validity check "JSON 评分下任务卡比空骨架
  ≥+2 分且下界 >0"), :100 (owner decision #2 pending; also docs/project-status.md:347). A grep for
  `scorer_v2|score_v2|scorer-v2|scorer v2|json_tolerant|json_answer` over skillopt/, scripts/, docs/ (*.py) finds nothing,
  and no coevo5/continual_eval code parses a JSON "answer" field (grep of `json` usages). Diagnostic prototypes exist ONLY
  in this session's scratchpad (not the repo), all SearchQA-only:
  `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E7/run2/json_counterfactual.py:11-28`
  (`JS = re.compile(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"')`; only when the reply has NO `<answer>` tag, the LAST JSON "answer"
  string, JSON-unescaped, is wrapped as `<answer>X</answer>` and scored by `backends.score("searchqa", ...)`),
  `.../scratchpad/feas/E10-critic/scripts/ceiling_by_scorer.py:13-27` (same rule, `max(strict, json)`, plus an
  alias-lenient substring variant), `.../scratchpad/feas/E10/scripts/json_aware.py:24-33` (non-greedy `{"answer": "(.*?)"}`
  regex without unescaping -- weaker). None handles OfficeQA/LiveMath, a JSON answer inside a tag, numbers as JSON numbers,
  or code-fenced JSON.

## 3. Interfaces an implementer would call or must replace

### 3a. Existing callables (verified signatures)
| callable | signature | returns / raises / side effects |
|---|---|---|
| official scorer | `skillopt.continual_eval.backends.score(benchmark, public, private, prediction, *, runtime=None)` (backends.py:517) | `{"status": "pass"/"fail"/"unknown", "score": float or None, "reason": str, "metrics": {...}}`; never raises for scoring-input errors (returns `native_scoring_input_error:<Exc>`, which coevo5 turns into a ConfigurationError stop, outcomes.py:60, :284-286). SpreadsheetBench v7: writes `started.json`, `recalculations/*.json`, `result.json` under `runtime["_score_context"]["artifact_dir"]`, runs LibreOffice containers; a second scoring of an interrupted position raises inside -> configuration stop (sheet_numeric_adapter.py:104). |
| official solver (to be wrapped/replaced by the route-B shell) | `backends.solve(benchmark, public, skill_text, call, *, runtime=None)` (:364) | prediction `{"status": "available"/"unknown", "output": ..., "costs": {...}, "reason": str, [trace, code_delivery]}`; `call(system, user)` must return a provider receipt dict (`ok`, `response`, `finish_reason`, `usage`, ...) (:90-111). |
| readiness probe | `backends.readiness(benchmark, runtime=None)` (:230) | `{"status": "ready"/"unsupported", "reason", ...}`; for sheet v7 runs `sheet_numeric_adapter.readiness` (offline qualification replay) then a native probe container. |
| answer-tag scorer (internal) | `backends._score_answer_tag(benchmark, output, answer)` (:491) | officeqa/livemath strict; `metrics = {"em", "invalid_format"}`; blank reference -> unknown `invalid_answer_tag_score_input` (= configuration stop in coevo5, outcomes.py:57). |
| completion-aware verdict | `skillopt.coevo5.outcomes.classify(benchmark, prediction, score=None, receipts=(), *, refused=False, spent=frozenset())` (:185); `preflight(...)` (:207); `finalize(verdict)` (:168) | `Verdict(outcome, kind, reason, row, remedy, exhausted)`, `.token` in `pass/fail/unknown/unknown_artifact`; raises `ConfigurationError`, `BudgetStop`, `CleanupUnconfirmed`, `AssumptionBroken`, `LedgerFailure`. |
| one cell end-to-end | `skillopt.coevo5.cells.run_cell(context, cell, task, skill)` (:166) | writes `cells/<id>.json` with `final` and `official`; raises `Pause` after writing on a stop. Bound to `backends.solve` with a plain Skill string (:134). |
| lenient (descriptive) | `skillopt.coevo5.scoring.lenient(benchmark, private, prediction)` (:76) | True/False/None; pure. |
| format checks | `skillopt.coevo5.checks.run(spec, output)`, `validate(spec)`, `last_answer(output)`; registry `CHECKS` (:16, :74-105) | True/False/None; `validate` raises ValueError (via `require`). |
| frozen guard table | `skillopt.coevo5.protocol.REQUIRED_FORMAT`, `PROMPT_LAYOUT`, `RUNTIME` (:127-128, :341-357) | constants. |
| fence extraction | `skillopt.continual_eval.code_delivery.extract_python(response)` (:21) | dict with `status`, `reason`, `code`, `candidate_kind`, `fenced_blocks`, `explicit_python_blocks`, hashes. |
| v7 sheet scorer | `skillopt.continual_eval.sheet_numeric_adapter.score(public, private, prediction, *, runtime, replay_only=False)` (:87); `qualified_engine(runtime)` (:28); `readiness(runtime)` (:77) | see F21. |
| pair recalc compare | `skillopt.continual_eval.sheet_recalc.evaluate_pair(prediction, reference, answer_position, engine, cache)` (:579); `screen(path)` (:198); `Recalculator(image, timeout=120)` (:395) | `{"status": "pass"/"fail"/"unknown", "reason", "evidence"?, "receipts"}`. |
| cell compare | `skillopt.continual_eval.spreadsheet_compat.evaluate(pred_path, gold_path, instruction_type, answer_position)` (:203); `skillopt.envs.spreadsheetbench.evaluator._compare_cell_value(v1, v2)` (:62) | `{"ok", "status": passed/failed/missing_output/unknown, "reason", "evaluator_version", "instruction_type", "evidence"}`. |
| reference qualification | `skillopt.coevo5.qualify.qualify(tasks, root, runtime, *, side, native, workers)` (:85); `reference_prediction(task)` (:38); `load(path)`; `summary(record)` | sealed record `{"version", "side", "tasks", "qualified", "excluded", "counts", "scorings_per_item": 2, "model_calls": 0, ...}` written to `<root>/qualification.json`; `root` must be NEW (ValueError otherwise); raises `Pause` on configuration/cleanup reasons. |
| exact arithmetic for generated truth | `skillopt.coevo5.forward.evaluate(formula)` -> Fraction; `literals(formula)`; `rounded(value, decimals)` -> str; `identity(material_text, question)` (:196-231) | raise `roles.Invalid` on disallowed syntax/limits; `rounded` requires 0..4 decimals. |
| native normalisers | `skillopt.envs.searchqa.evaluator.normalize_answer / extract_answer / evaluate`; `skillopt.envs.officeqa.evaluator.normalize_answer / exact_match`; `skillopt.continual_eval.datasets.livemath_options(choices)` | pure. |

### 3b. Route-B judge -- what it must compute per cell (PROPOSAL derived from the facts above; nothing here exists yet)
Inputs: the frozen task record `{"public", "private"}` (host only), the shell's prediction in TODAY's shapes (raw reply text
for QA, `{"code", "cases"}` for SpreadsheetBench, `{"won", "steps"}` + `trace` for ALFWorld), the provider receipts, and --
new for route B -- the raw model reply BEFORE and the delivered answer AFTER the fixed format guard. Output: one sealed
record with four independent blocks; the judge never feeds anything back to the solver or the shell.

1. `official` (frozen, primary for every claim): exactly `backends.score(...)` with `protocol.RUNTIME[bench]`
   unchanged, plus `outcomes.classify(...)` (completion-aware `final`) -- i.e. reuse `cells._score` / `run_cell` semantics.
   Record both, as coevo5 does (F13). Registration must say which of the two is the decision metric (they differ only on
   truncation/filter/empty, malformed action, code_delivery failure: F14).
2. `v2` (JSON-tolerant extraction, same comparison): a NEW module with its own VERSION (never edit `_score_answer_tag` or
   the env evaluators). Per bench:
   - extraction order (all QA benches): (i) last `<answer>` tag (as official); (ii) if no tag: the last JSON object in
     the reply (also inside a ```json fence) having key "answer" whose value is a string, or a number (rendered with
     `repr`-free decimal text), JSON-unescaped (prototype regex in F31); (iii) SearchQA only: the official last-line
     fallback; else no answer. Define the v2 verdict as `official pass OR JSON-extracted answer passes` (what the
     E10-critic prototype computes, `ja = max(st, ...)`, ceiling_by_scorer.py:24), so v2 >= official cell by cell -- make
     that a unit-test invariant; a JSON-first order alone could turn an official last-line pass into a v2 fail.
     Open: whether a JSON object INSIDE the tag (`<answer>{"answer": "X"}</answer>`) is unwrapped -- the prototypes do not.
   - comparison: the frozen one on the extracted text -- SearchQA `exact_match` (SQuAD normalisation), OfficeQA
     `officeqa.evaluator.exact_match`, LiveMath the strict single-letter rule (backends.py:501-505).
   - SpreadsheetBench, ALFWorld: v2 == official (no JSON channel); record `v2 = official` explicitly, do not leave None.
3. `lenient` (descriptive only, never a claim -- F9): `scoring.lenient(...)` applied to the v2-extracted answer, plus for
   OfficeQA a numeric-equality flag (`Fraction` equality of the single number, so "12.5" == "12.50").
4. `format` flags (all deterministic, host-side, none uses the reference):
   - `answer_tag_present` (`checks.answer_tag_present`), `tag_count` (len(`checks.ANSWER.findall`)), `json_answer_present`
     (no tag but JSON "answer"), `json_inside_tag`, `boxed` (`\boxed{` present, the 10/19 LiveMath case F16),
     `bare_letter_no_tag` (LiveMath: reply is a single letter), `last_line_fallback_used` (SearchQA).
   - `single_answer`: LiveMath `checks.answer_single_letter`; OfficeQA exactly one `checks.NUMBER` match in the tag;
     SearchQA: no list separators (`,`, `;`, ` or `, `/`, parenthesised alias) -- new deterministic rule (the D3
     "Not one answer" code is model-assigned today, protocol.py:153-154); also `checks.answer_max_words` with a registered n.
   - SpreadsheetBench: `program_delivered` (`code_delivery.extract_python(...)["status"] == "available"`, with
     `candidate_kind` and `explicit_python_blocks`), `excel_formula_only` (no Python deliverable and the reply's
     answer-like line starts with `=` and a function call -- new rule; today such replies become `code_delivery:*` malformed or
     a `native_exception` program defect, F19), `fence_glued` (a ``` not at line start -- the 10/19 third failure),
     per-case generation status/reason, workbook-valid (outcomes row 9b), `cases_passed/cases_total`.
   - ALFWorld: `action_tag_present` per step (backends.py:752 regex), `inadmissible_actions` (action not in the step's
     `admissible_commands`, from the trace -- needs `alfworld_trace_version`), `steps`, `won`.
   - all benches: `truncated` (prediction reason `model_response_truncated` or last receipt `finish_length` /
     `finish_max_tokens`), `filtered`, `completed_without_text`, `reply_chars`, `completion_tokens`, and route-B specific
     `guard_changed_answer` (delivered answer differs from what the raw reply would score as) -- see risk R2.
5. Generated tasks with program-computed truth (examiner side). Truth must be a host-computed value, never a model's
   word; the comparison must be the bench's official rule so that generated-panel results are commensurable:
   - OfficeQA-type: reference = `forward.rounded(forward.evaluate(formula), decimals)` and the question carries the
     rounding sentence (`forward._rounding`, :245-248). Official comparison = OfficeQA EM (no tolerance; trailing-zero trap F28);
     v2/lenient numeric = `Fraction(single number in tag) == Fraction(reference)`. Units: reference is the bare number in
     the table's unit; "%" and the words removed by `normalize_answer` (million/billion/dollar(s)/nominal) are ignored by the
     official EM, "thousand"/"percent" are NOT (F4) -- generator must state the unit in the question or avoid unit words.
   - LiveMath-type: five distinct exact options, exactly one equal to the program value (`forward._live`, :320-342);
     key letter from a balanced schedule (D6, F29); judge = official single-letter rule; add the examiner's
     options-only shortcut probe as a separate, registered check (design-v0.md:29).
   - SpreadsheetBench-type: reference workbook produced by the generator program; the task must pass the SAME
     reference qualification as real items (`qualify.qualify`, two v7 scorings of reference-as-answer) before use; judge =
     v7 scorer (recalc both sides, `_compare_cell_value`: 2-decimal rounding, strict types, "" == None); public and private
     `answer_position` equal; `private["asset_sha256"]` filled for every reference (F21). Formulas must avoid
     `FORBIDDEN_FUNCTIONS`, `_xlfn.`/`_xlws.` functions, structured refs (F22), and the reference's answer cells must carry
     cached values (risk R5).
   - ALFWorld-type: an unused `game.tw-pddl` under the frozen data root (3553 in train on dl, F26); judge = simulator
     `won` within `max_steps = 50`; same split key (`alfworld_split "train"`).
   - SearchQA: no executable truth (design-v0.md:29); only paraphrase-robustness probes whose reference answers are the
     original item's `answers` list, judged by the official EM.


## 4. Reusable unchanged for route B vs must be generalized

### Reusable unchanged (call as-is, keep frozen)
- U1 `backends.score` for all five benches as the official judge (F2-F6), provided the shell emits predictions in the
  current shapes (F8). Its SearchQA/OfficeQA/LiveMath branches are pure host functions (no container).
- U2 `outcomes.classify` / `preflight` / `Verdict` and the two-field cell record (`final` + `official`, F13-F14);
  the remedy limits (`MAX_REEXECUTIONS`, `MAX_RESCORES`, `MAX_EPISODE_RESTARTS`, protocol.py:86-91).
- U3 `checks` library and `REQUIRED_FORMAT` as the frozen per-bench format guard check (F10-F11); `smoke.format_check`'s
  criterion shape (floor 9/10, margin 1/20) as the pre-launch format check pattern (F17).
- U4 The v7 SpreadsheetBench chain: generation image `sha256:0a0a5dcb...`, recalc image `sha256:f7f6f598...`,
  qualification file (present on dl, hash verified, F25), `sheet_numeric_adapter.score`, `qualify.qualify` for any new
  item set (real or generated).
- U5 `code_delivery.extract_python` (`explicit-python-fences-v1`) for "program delivered".
- U6 `forward.evaluate` / `forward.rounded` / `forward.literals` / `forward.identity` as the exact-arithmetic truth
  kernel for OfficeQA-type and LiveMath-type generated items (F27-F28).
- U7 ALFWorld `won` from the vendored worker (F26) with the coevo5 runtime (split train, 50 steps, seed 42).

### Must be generalized (and why)
- G1 `backends.solve` hard-codes the prompt (`system` text, contract position, `json.dumps(view)` user message, one call
  per QA task, ALFWorld view = `initial_observation`, `observation`, `admissible_commands`, `recent_history[-5:]`,
  backends.py:379-417, :744-747). Route B's shell rewrites context, runs "precise computation" round trips and vetoes
  actions, so it needs its own solve loop. To keep U1/U2 valid it must (a) emit identical prediction shapes and reasons
  (`model_response_truncated`, `invalid_action_format`, `code_delivery:*`, ...), (b) keep the contract sentence and the
  contract-first order fixed, (c) for multi-call QA keep the "last receipt" semantics that `_completed_without_text` and
  outcomes rows 4-5 read (backends.py:411-422; outcomes.py:256-263) -- with several calls per task the "last receipt" is
  no longer the answer call unless the shell orders it so.
- G2 Scorer v2 does not exist (F31): new versioned module + registration; the prototypes are SearchQA-only and
  untagged-only.
- G3 `scoring.lenient` is unwired (F12) and last-tag-only; route B should compute it on the v2 extraction and store it.
- G4 `REQUIRED_FORMAT["alfworld"] = ()` (protocol.py:128): no ALFWorld format guard check exists; route B's veto/guard
  for actions needs registered flags (tag present, admissible).
- G5 `forward._office` requires every formula literal to be a cell of `material["table"]["rows"]` from a Wikipedia
  page with `source.title`/`source.revid` (forward.py:255-276, :294); route B's "change a real OfficeQA table's numbers and
  recompute" works on Treasury-bulletin `context` text, which has no parsed table structure -- a table extractor and a
  new material shape are needed (D6 also flags the research parser's missing row/col spans, D6/report.md:116).
- G6 Truth for LiveMath-type variants beyond arithmetic (symbolic) needs sympy (present in the native image, F25) and
  the D6 rules (numeric validation at 50 digits, exclude unevaluated integrals/series, F29); `forward.evaluate` alone
  covers only rational arithmetic + a few integer functions.
- G7 SpreadsheetBench generated items need a generator that writes reference workbooks with cached answer values and
  fills `private["test_files"]`, `["answer_position"]`, `["asset_sha256"]`, then a qualification run (two v7 scorings per
  item; container cost) before any use.
- G8 Path assumptions: `RUNTIME["spreadsheetbench"]["recalculation"]["qualification_path"]` and the ALFWorld data root
  are under `/root/...` on dl (verified present); a new output tree for route B must not reuse `/data/coevo5-*`.


## 5. Gaps and risks for route B in this area
- R1 (high) The measuring instrument is format-dominated on SearchQA: JSON-wrapped replies score 0/364 officially though
  324/414 of their identical tagged twins pass (F30); format drift moves between sessions (D9 evidence H). Any route-B
  comparison (S' vs S vs task card vs placebo) must record the format flags per arm and report v2 next to official, else a
  procedure that merely changes reply wrapping will look like a content effect (or mask one).
- R2 (high) Format guard vs "answer repair" (AGENTS.md: "Answer repair is not Skill evolution"): if route B's fixed format
  guard re-wraps or extracts the answer (e.g. JSON -> tag), the official score of the guarded output is effectively a v2
  score. The guard must be identical in every arm (including task-card-only and placebo), and the judge must store the
  raw-reply score as well as the guarded-answer score plus `guard_changed_answer`, so gains attributable to the guard are
  not credited to learned procedures.
- R3 (medium) Truncation semantics differ: official = unknown, completion-aware = fail (F7, F14); with
  `SOLVER_MAX_TOKENS["deepseek-v4-flash"] = 32768` (protocol.py:327) the 10/19 format check already lost 2 SpreadsheetBench
  replies to truncation (registration v3 delta :73-74). Route B shells that add context (state records, extracted tables)
  raise prompt length; the decision metric must be registered before launch.
- R4 (medium) OfficeQA official EM has no numeric tolerance and keeps "%" and "thousand" (F4): procedure outputs that
  print floats (`0.30000000000000004`), trailing zeros ("12.50" vs "12.5") or a different unit will be marked wrong.
  The "precise computation" procedure must format results to the question's precision, and the judge must flag
  `numeric_equal_but_em_fail` descriptively.
- R5 (medium, inferred from code) Generated SpreadsheetBench references written by openpyxl contain formulas WITHOUT
  cached values. `evaluate_pair` checks the recalculated reference against the ORIGINAL reference's cached values
  (`compat.evaluate(recalc_ref, original_ref, ...)`, sheet_recalc.py:610-612); a formula cell with no cache makes
  `compat.evaluate` return unknown ("formula cache not established", spreadsheet_compat.py:246-260), so the item would be
  excluded as `reference_cache_mismatch`. References need literal answer values, or a LibreOffice-recalculated copy
  frozen as the reference (then re-qualified). Not executed -- verify with a zero-model qualification smoke.
- R6 (medium) Unscorable formula space: `FORBIDDEN_FUNCTIONS`, `_xlfn.`/`_xlws.` (XLOOKUP, IFS, TEXTJOIN, FILTER, ...),
  structured refs -> unknown, not fail (F22). Generated tasks and procedures that emit such formulas inflate unknowns;
  `MAX_UNKNOWN_SHARE = 1/10` pauses a chain (protocol.py:84).
- R7 (medium) The SearchQA card says "Anything else in the reply is ignored" but the official extractor uses the last-line
  fallback (F3, F18); the ALFWorld card's "counts as failed" is true only for the completion-aware verdict. If route B
  freezes these cards as seeds, the discrepancy is part of the frozen seed (fine), but the judge docs must not repeat it.
- R8 (low) Blank generated references pause the run as configuration errors (`invalid_answer_tag_score_input` is in
  `outcomes.CONFIGURATION`, outcomes.py:57); generated-task builders must reject empty answers before cells exist.
- R9 (low) ALFWorld "new environments": the frozen backend only loads existing `game.tw-pddl` files under the data root
  (F26); sampling must exclude every game used by v1-v3, D3 (228-episode replay) / D14 (57 episodes)
  (design-v0.md:16) and the registered pools; I did not verify which train games those used.
- R10 (low) `backends.score` for SpreadsheetBench v7 re-validates the 23-control qualification on EVERY call
  (`qualified_engine`, sheet_numeric_adapter.py:28-74, imports `scripts.replay_sheet_v6`): route B must run from a source
  tree that contains scripts/ and the pinned qualification; cost per call is offline file hashing (inferred).


## 6. Open questions for the designer (not verifiable by reading)
- Q1 Scorer v2 scope: accept a JSON "answer" only for untagged replies (all prototypes) or also inside a tag; accept
  `\boxed{X}` / a bare final letter for LiveMath; accept JSON numbers for OfficeQA? Owner decision #2 of the direction
  recommendation is still pending (direction-recommendation-20261021.md:100; docs/project-status.md:347).
- Q2 Which outcome is route B's decision metric: official (truncation unknown) or completion-aware final (truncation
  fail)? coevo5 v3 gate statistics read the completion-aware token (`r["final"]["token"]`, step.py:125, :170, :210) while the
  frozen scorer's `official` status is kept alongside in each cell -- confirm the same choice for route B.
- Q3 Is the route-B format guard an instruction only (contract sentence, as in v3) or an output transformer? If a
  transformer, is its effect reported as part of the shell (all arms) and excluded from "learned" effects?
- Q4 For OfficeQA-type generated items from real Treasury pages, what is the table source (the one-call `context` is plain
  text; D6 says the research parser lacks row/col spans)? Who checks that a perturbed number keeps the page coherent?
- Q5 SpreadsheetBench generated references: literal answer values or formulas plus a frozen LibreOffice-recalculated
  copy? Either way, a zero-model qualification smoke on 5-10 generated items should precede any paid run (R5).
- Q6 ALFWorld sampling frame: which of the 3553 train games are already used (v1-v3 pools, D3 replay 228 episodes, D14
  57 episodes), and must new environments match the registered pool's task-type mix?
- Q7 The relayed user request for this workflow run asks for a different task (a summary of the best-looking/most
  persuasive past results, explicitly ignoring noise). This file covers only the computed judging-area step; that
  request is NOT addressed here and should be routed separately by the orchestrator.

