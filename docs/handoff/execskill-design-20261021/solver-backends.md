# Solver backends: how the frozen solver runs the five benchmarks, and where a route-B "shell" can hook in

Read-only mapping, 2026-10-21. Every fact cites `repo-path:line` (repo-relative) or an absolute path on the
development machine `dl`. "Verified" = read in the source or observed read-only on dl; "inferred" = my reading,
not executed. Nothing in the repository or on dl was modified; no model call was made.

## 1. Scope and files read

Repository (line counts from `wc -l`):

| File | Lines | Read |
|---|---|---|
| skillopt/continual_eval/backends.py | 783 | all |
| skillopt/continual_eval/core.py | 359 | all |
| skillopt/continual_eval/datasets.py | 507 | all |
| skillopt/coevo5/units.py | 157 | all |
| skillopt/coevo5/cells.py | 263 | all |
| skillopt/coevo5/calls.py | 279 | all |
| skillopt/coevo5/outcomes.py | 402 | all |
| skillopt/coevo5/protocol.py | 357 | all |
| skillopt/coevo5/manifest.py | 154 | all |
| skillopt/coevo5/skill.py | 136 | all |
| skillopt/coevo5/ledger.py | 103 | 1-72 |
| skillopt/coevo5/texts.py | 183 | 1-140 |
| skillopt/coevo5/evaluation.py | 455 | 308-400 |
| skillopt/coevo5/chain.py | 314 | 131-224 |
| skillopt/coevo5/step.py | 861 | 80-130 |
| skillopt/coevo5/smoke.py | 435 | 276-300 (+grep) |
| skillopt/coevo5/data.py | 358 | 155-185 |
| skillopt/coevo5/budget.py | 351 | grep (scopes, `rooted`) |
| skillopt/continual_eval/native_worker.py | 119 | all |
| skillopt/continual_eval/code_delivery.py | 83 | all |
| skillopt/continual_eval/sheet_numeric_adapter.py | 151 | all |
| skillopt/continual_eval/sheet_recalc.py | 886 | 395-500, 579-614 |
| skillopt/skill_validation/sandbox.py | 312 | grep (L39 `_IMAGE`, L53 `_bounded_command`) |
| skillopt/envs/alfworld/vendor/alfworld_envs.py | - | 30-113 (worker) |
| skillopt/envs/alfworld/vendor/config_tw.yaml | - | grep |
| skillopt/envs/searchqa/evaluator.py | - | 28-41, 88-100 |
| skillopt/envs/officeqa/evaluator.py | - | 11-23 |
| scripts/weak_solver_probe.py | 608 | 1-420 |
| skillopt/validator_pilot/api.py | 679 | grep only |
| docs/project-status.md | - | line 14, line 201 (grep hits) |

Development machine `dl` (read-only: ls/grep/python -c; nothing written): listing of `/data`, `/data/execskill-ops`,
`/root/.config/weak-solver` (names only); variable NAMES (not values) in `/root/.config/weak-solver/elucid.env`;
keys/paths of `/data/coevo5-20261019-v3-run-manifest.json`; SHA-256 of seven source files in three trees; the installed
ALFWorld env source (grep); interpreter/library versions; `/proc` scan for running coevo5 processes; aggregate
SpreadsheetBench case counts of the two TRAINING panels.
NOT read: the new-endpoint probe logs `/data/execskill-ops/probe-20261021-{1,2}.log` (the permission classifier refused
the read; I did not work around it). What they say is known only through docs/project-status.md:14.

## 2. Facts

### 2.1 Single-call benchmarks (SearchQA, OfficeQA, LiveMath, SpreadsheetBench): prompt assembly

- **F1** Entry point `def solve(benchmark, public, skill_text, call, *, runtime=None)` (skillopt/continual_eval/backends.py:364).
  Pre-checks before any call: `code_extraction_version` must be None or `"explicit-python-fences-v1"` and only for
  bigcodebench/spreadsheetbench (backends.py:367-370); `prompt_layout` must be None or in `CONTRACT_FIRST_LAYOUTS` and
  the benchmark must not be alfworld (backends.py:371-372, 359-361); the public task is whitelisted by `_PUBLIC`
  (backends.py:57-62, 73-87); alfworld is dispatched to `_solve_alfworld` (backends.py:377-378). Verified.
- **F2** System prompt base: `"Solve the supplied task using only the supplied public information."` (backends.py:379).
  Skill text goes ONLY into the system prompt: `guidance = ("\n\nFrozen skill guidance (use only where applicable):\n" + skill_text) if skill_text.strip() else ""` (backends.py:380).
- **F3** Fixed format sentences (the "contract"):
  - searchqa, officeqa: `"\nReturn the concise final answer inside <answer>...</answer>."` (backends.py:381-382)
  - livemath: `LIVEMATH_CONTRACT = "\nChoose exactly one of the listed options and return only its letter inside <answer>...</answer>."` (backends.py:35, 383-384)
  - spreadsheetbench with `prompt_layout == "contract-first-v2"`: `SHEET_CONTRACT_V2` = `"\nReturn one complete Python program in a ```python code block whose opening fence starts its own line. The program reads input.xlsx and saves output.xlsx with the answer at the required answer position. A formula alone is not an answer: when the task asks for a formula, the program writes it into the answer cells."` (backends.py:53-56, 387-388) -- this is the "Python program, not an Excel formula" line.
  - spreadsheetbench otherwise: `"\nReturn one complete Python program in a ```python code block."` (backends.py:389-390).
- **F4** Layout: with `runtime["prompt_layout"]` in `("contract-first-v1", "contract-first-v2")` the system prompt is
  `base + contract + guidance`; otherwise the historical `base + guidance + contract` (backends.py:47-52, 391-394).
  v1 and v2 differ only in SpreadsheetBench's contract (backends.py:48-50). The v3 protocol sets
  `PROMPT_LAYOUT = "contract-first-v2"` for searchqa/officeqa/livemath/spreadsheetbench and no layout for alfworld
  (skillopt/coevo5/protocol.py:341-357). Hence the exact v3 system prompts (S = rendered Skill; with S blank the guidance
  part disappears):
  - SearchQA/OfficeQA: `Solve the supplied task using only the supplied public information.\nReturn the concise final answer inside <answer>...</answer>.\n\nFrozen skill guidance (use only where applicable):\n` + S
  - LiveMath: `...public information.\nChoose exactly one of the listed options and return only its letter inside <answer>...</answer>.\n\nFrozen skill guidance (use only where applicable):\n` + S
  - SpreadsheetBench: `...public information.` + SHEET_CONTRACT_V2 + `\n\nFrozen skill guidance (use only where applicable):\n` + S
- **F5** User message = `json.dumps(view, ensure_ascii=False)` (backends.py:417): default separators, dict insertion order,
  no sort. QA views: searchqa `{"question", "context"}` (context str or list of str), officeqa `{"question", "context"}`
  (context one str: the rendered pages), livemath `{"question", "choices"}` (backends.py:57-62, 78-86;
  skillopt/continual_eval/datasets.py:28-35, 177-178).
- **F6** LiveMath options: `choices` is ONE string `"A. ...\n\nB. ...\n\nC. ...\n\nD. ...\n\nE. ..."`
  (datasets.py:33, parser `livemath_options` datasets.py:186-200); the private answer is one letter of `"ABCDE"`
  (datasets.py:23, 173-176). The meta-option `STRONGER_OPTION = "One of the remaining options is correct, but a stronger result can be proven."` occurs in 129 of 283 training items per protocol.py:220-222 (comment; not recounted).
- **F7** SpreadsheetBench view is rebuilt before the call (backends.py:397-409):
  `{"instruction", "workbook_preview": _sheet_preview(files[0], version=preview_version), "input_path": "input.xlsx", "required_output_path": "output.xlsx", "required_answer_position": view["answer_position"]}`.
  The preview is of the FIRST input workbook only (backends.py:407): up to 20 sheets, each `{"sheet", "rows", "columns", "preview"}`
  with the first 5 rows x 20 columns; under `"public-formula-preview-v1"` values are `str(value)[:200]` or a formula
  dict for ArrayFormula/DataTableFormula (backends.py:296-356).
- **F8** One model call per task: `_response(recorded, system, user)` (backends.py:417). `_response` (backends.py:90-111):
  exception -> `(None, {"calls": 1}, "model_call_exception:" + type(exc).__name__)`; non-dict -> `"invalid_model_receipt"`;
  `finish_reason in {"length", "max_tokens"}` -> `"model_response_truncated"`; `not ok` or response not str ->
  `"model_call_unavailable"`; blank or > `MAX_RESPONSE = 262144` bytes (backends.py:36) -> `"empty_or_oversized_model_response"`;
  else `"model_response_available"`; costs `{"calls": 1, "usage": receipt.get("usage", {})}`. The branch on
  `request.service.delivery_retry_policy` (backends.py:99-104) applies only to validator_pilot receipts, not to the
  coevo5 solver client (inferred: weak_solver_probe receipts carry no `request` key, scripts/weak_solver_probe.py:268-303).
- **F9** For livemath/officeqa only, `solve` keeps the receipts (backends.py:411-416) and turns a completed blank reply
  (finish "stop", stream not incomplete, HTTP 200, valid usage, `ok True` or `error_type == "empty_content"`) into output
  `""`, i.e. scored wrong (backends.py:418-422, 475-488).
- **F10** Extraction: with `code_extraction_version == "explicit-python-fences-v1"` the program comes from
  `code_delivery.extract_python` (backends.py:426-433): one explicit ```python/py block (line-delimited fences), else a
  sole unlabelled block, else an entirely unfenced reply; two Python blocks -> `"multiple_python_blocks"`; failures ->
  prediction unknown `"code_delivery:<reason>"` (skillopt/continual_eval/code_delivery.py:21-83), classified as
  MALFORMED fail, row 6 (skillopt/coevo5/outcomes.py:75-76, 296-297). QA outputs are the raw reply (backends.py:436).
- **F11** SpreadsheetBench execution happens INSIDE `solve`, right after the reply: for each `public["input_files"]` path,
  `_native({"operation": "spreadsheet_generate", "code": output, "input_base64": ...}, runtime)` (backends.py:437-442),
  i.e. one fresh container per input case running the same program; with the private option
  `_stop_on_cleanup_failure` an unconfirmed cleanup marks the remaining cases `"not_executed_after_cleanup_failure"`
  (backends.py:443-450). Result: `{"status": "available", "output": {"code", "cases": [...]}, "costs", "reason": "generated_once_executed_per_public_case", "code_delivery": {...}}` (backends.py:451-452).
- **F12** Container: image must match `_IMAGE = r"(?:[A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[0-9a-f]{64}\Z"`
  (skillopt/skill_validation/sandbox.py:39) and be present locally (`docker image inspect`, linux, no volumes;
  backends.py:132-150). Command (backends.py:169-178): `docker run --pull=never --name continual-eval-<uuid4> --network=none --read-only --user=65534:65534 --cap-drop=ALL --security-opt=no-new-privileges=true --pids-limit=128 --memory=<m>m --memory-swap=<m>m --cpus=<c> --ipc=private --shm-size=64m --no-healthcheck --log-driver=none --ulimit=nofile=256:256 --ulimit=core=0:0 --env CONTINUAL_EVAL_CONTAINER=continual-eval-native-v1 ... --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777 --workdir=/tmp --mount type=bind,source=<tmp>,target=/input,readonly --entrypoint=python <image> -I -B /input/worker.py`;
  stdout limit 16 MiB (backends.py:183), request <= 32 MiB (backends.py:160), `docker rm --force` bounded at 10 s and an
  unconfirmed cleanup is `"container_cleanup_unconfirmed"` (backends.py:188-198). Limits: `timeout_seconds` 5..600
  (default 300), `memory_mb` 256..32768 (default 4096), `cpus` (0, 8] (default 1) (backends.py:119-129).
- **F13** Inside the container (skillopt/continual_eval/native_worker.py:86-99): writes `input.xlsx` in a fresh temp dir,
  `exec(compile(request["code"], "generated.py", "exec"), {"__name__": "__main__"})`, returns
  `{"status": "available", "output_base64", "reason": "isolated_workbook_generated"}`, or `{"status": "missing_output"}`,
  or size-limit unknown. stdout/stderr are discarded (native_worker.py:110-112) and an exception becomes only
  `"native_exception:" + type(exc).__name__` (native_worker.py:113-114): the program's error message/traceback is never
  available to the host.
- **F14** v3 runtime constants (protocol.py:342-357), verbatim: spreadsheetbench `"image": "sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd"`, `"timeout_seconds": 300`, `"memory_mb": 4096`, `"cpus": 1`, `"code_extraction_version": "explicit-python-fences-v1"`, `"spreadsheet_preview_version": "public-formula-preview-v1"`, `"_stop_on_cleanup_failure": True`, `"spreadsheet_scorer": "qualified_lo_recalc_v7_v1"`, recalculation `{"image": "sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790", "timeout_seconds": 120, "qualification_path": "/root/continual-fivebench-20261003-f-q23/qualification.json", "qualification_sha256": "f5bc90df...", "qualification_hash": "cc4ab804..."}`; alfworld `{"alfworld_data": "/root/continual-alf-prep-20260928/data", "alfworld_split": "train", "max_steps": 50, "timeout_seconds": 60, "seed": 42, "alfworld_trace_version": "alfworld-public-transitions-v1"}`. Verified on dl (ls): both `/root/...` paths and `logic/alfred.pddl` exist. Docker image presence on dl NOT checked (docker is outside the allowed read commands).
- **F15** SpreadsheetBench scoring (backends.py:547-557 -> skillopt/continual_eval/sheet_numeric_adapter.py:87-151):
  revalidates the 23-control qualification offline on every call (sheet_numeric_adapter.py:28-74); needs the host-owned
  `runtime["_score_context"]` that `cells._score` adds (skillopt/coevo5/cells.py:158-161); per case both prediction and
  reference are recalculated in fresh LibreOffice containers (`--network=none`, 1024 MiB, 1 CPU, timeout 120;
  skillopt/continual_eval/sheet_recalc.py:395-499), the reference cache must agree (drift guard), then
  `spreadsheet_compat.evaluate` on `answer_position` (sheet_recalc.py:579-614). Task passes only if EVERY case passes
  (`"qualified_numeric_recalculation_hard_all_cases"`, sheet_numeric_adapter.py:133-139). Result cached as `result.json`
  under the scoring position (sheet_numeric_adapter.py:96-102, 150).
- **F16** Case counts (verified on dl, aggregate only): the two SpreadsheetBench TRAINING panels the v3 manifest pins,
  `/root/continual-spreadsheet-long-20261001-study/baseline/data/panel.json` (80 tasks, partition development) and
  `/root/continual-spreadsheet-20260928-a/prepared/panels/skill_confirmation.json` (40 tasks), have exactly ONE input
  case per task. Test-panel case counts were deliberately not read.
- **F17** QA scoring: searchqa uses `envs/searchqa/evaluator.evaluate` -- last `<answer>` tag, else the LAST NON-EMPTY
  LINE, else the whole text (skillopt/envs/searchqa/evaluator.py:28-40); pass iff `em` (backends.py:524-531).
  officeqa/livemath: strict last `<answer>` tag; no tag -> fail with `invalid_format = 1` (backends.py:491-514); officeqa
  normalised exact match, no numeric tolerance (skillopt/envs/officeqa/evaluator.py:11-21); livemath one letter A-E
  after dropping one trailing `.`, `)` or `:` (backends.py:501-506).

### 2.2 ALFWorld

- **F18** `_solve_alfworld(public, skill_text, call, runtime)` (backends.py:715-783). System:
  `"Act in the text environment. Return a single action inside <action>...</action>."` plus, if the Skill is nonblank,
  `"\nFrozen skill guidance (use only where applicable):\n" + skill_text` (backends.py:730-732) -- one newline, not two as
  in QA; a `prompt_layout` is rejected for alfworld (backends.py:359-361).
- **F19** Per-step user message `json.dumps(view, ensure_ascii=False)` with
  `view = {"initial_observation": str(reset observation), "observation": observations[0], "admissible_commands": infos[0].get("admissible_commands", []), "recent_history": prompt_history[-5:]}`
  (backends.py:739-747); history items `{"observation": str(observations[0])[:12000], "action": action}` (backends.py:757-758).
  One model call per step; the system prompt (with the whole Skill) is resent every step (protocol.py:48 comment).
- **F20** Action: first `<action>(.*?)</action>` (re.S) else the whole reply stripped (backends.py:752-753); empty or
  > 1000 chars -> prediction unknown `"invalid_action_format"` (backends.py:754-756) = MALFORMED fail (outcomes.py:75, 296-297).
  No admissibility check: any string is sent to `env.step([action])` (backends.py:762).
- **F21** Budget: `max_steps` int 1..150, default 50 (backends.py:727-729), also enforced in `_new_alfworld` and copied
  into the vendor TimeLimit (backends.py:684-686, 693-696). Loop stops on `won or dones[0]` (backends.py:768-770). Output
  `{"won": bool, "steps": step + 1}`, reason `"fresh_native_episode_completed"`, costs `{"calls", "usage_by_call"}` (backends.py:771-773).
- **F22** Success: `won = bool(infos[0]["won"])` after every step; a missing key -> unknown `"native_won_signal_missing"`
  (backends.py:765-768); `score` passes iff `output["won"]` (backends.py:558-563). Installed env on dl requests
  `textworld.EnvInfos(won=True, admissible_commands=True, extras=["gamefile"])` and, when `train_eval == "train"`, adds
  `"expert_plan"` (/root/continual-alf-prep-20260928/env/lib/python3.11/site-packages/alfworld/agents/environment/alfred_tw_env.py:254, 263-266).
  v3 runs `alfworld_split: "train"` (protocol.py:355), so `infos` DO carry `extra.expert_plan` and `extra.gamefile`; only
  `admissible_commands` enters the model view (backends.py:743-746).
- **F23** Episode transport: `_new_alfworld` requires `os.environ["ALFWORLD_DATA"] == runtime["alfworld_data"]` (never
  sets it; backends.py:669-673), a `game.tw-pddl` inside that root (backends.py:674-677), and a per-episode config copy
  that restricts the dataset scan to the game's directory (backends.py:687-692). `_AlfSession` = one spawned process
  per episode with `Queue(1)` each way (backends.py:605-620) running `alfworld_envs._worker_loop`
  (skillopt/envs/alfworld/vendor/alfworld_envs.py:53-81); per message timeout `min(120, timeout_seconds)` = 60 s
  (backends.py:698). `reset() -> (observations, None, [info])`, `step([a]) -> (observations, None, scores, dones, [info])`
  where `info` is the batch-1 dict flattened (backends.py:628-640). A failed `close()` returns
  `"alfworld_cleanup_unconfirmed"` from a `return` inside `finally`, overriding any earlier return (backends.py:777-783).
- **F24** Trace (with `alfworld_trace_version == "alfworld-public-transitions-v1"`): per step `{observation[:12000], action, post_observation[:12000], post_observation_status, post_observation_characters, post_observation_reason}`
  (backends.py:757-764, 701-712), returned as `prediction["trace"]` and `trace_version` (backends.py:724-725, 771-773).
  The trace has NO admissible_commands, NO raw model reply, NO step-level request text.

### 2.3 The call contract the solver receives

- **F25** In coevo5 the `call` is a `calls.Recorder` built per cell (skillopt/coevo5/cells.py:132-135,
  skillopt/coevo5/calls.py:261-279). `Recorder.__call__(system, user)`: up to `MAX_RESENDS + 1 = 3` sends of the IDENTICAL
  request while `outcomes.undelivered(receipt)`, sleeping `RESEND_COOLDOWN_SECONDS = 300` between (calls.py:268-275,
  protocol.py:87-88); appends the final receipt to `recorder.receipts`; calls `on_reply()` after EVERY call (calls.py:276-279).
- **F26** `Endpoint.send(system, user, recorder)` (calls.py:150-185): holds one model slot (fcntl file lock) per request
  (calls.py:155); if charged, reserves `CLIENT_ATTEMPTS * (request_bytes + 512 + max_tokens)` (skillopt/coevo5/ledger.py:26-36,
  protocol.py:278-279) under the halt generation of the attempt; calls `self.client.call(system, user)` (calls.py:177);
  records `{request_sha256 = sha256(system + "\x00" + user), request_bytes, model, max_tokens, started, seconds, reserved, charged, assumption_broken, receipt}`
  (calls.py:125-126, 153-154, 198-214). The request TEXT is never stored. It raises `BudgetStop`, `AssumptionBroken`,
  `LedgerFailure` (calls.py:163-174, 183-196); backends turns them into `"model_call_exception:<Name>"` (backends.py:93-94)
  and `outcomes._stops` re-raises them as run stops (outcomes.py:239-245).
- **F27** `ledger.settle` requires `receipt["attempts"]` = list of 1..4 dicts, else ValueError -> `recorder.invalid` ->
  ConfigurationError pause (ledger.py:51-62; calls.py:206-210; cells.py:194-195). Usage is charged on the last attempt;
  the assumption breaks (global halt, `AssumptionBroken`) when `prompt_tokens > request_bytes + 512` or
  `completion_tokens > max_tokens` (ledger.py:63-71; calls.py:183-184, 212-213).
- **F28** Client: `class Client` in scripts/weak_solver_probe.py:227-345, `__init__(self, repo, model, *, proxy, max_tokens, router_env=None, read_timeout=900, transport=None, route=None, route_env=None)`.
  Model must be in `MODELS` (weak_solver_probe.py:76-85, 232-233); proxy must be None or
  `GATEWAY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"` (weak_solver_probe.py:71, 234-235); an explicit
  route only from `ROUTES = {"pjlab_token": {"deepseek-v4-flash": (frozenset({"deepseek-v4-flash"}), "disabled")}}`
  (weak_solver_probe.py:88, 237-243); `httpx.Client(timeout=httpx.Timeout(connect=20, read=read_timeout, write=30, pool=30), trust_env=False, follow_redirects=False)` (weak_solver_probe.py:254-256).
- **F29** Request body (weak_solver_probe.py:259-266): `{"model", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens", "temperature": 0}`
  + `"thinking": {"type": <thinking>}` if set + `"reasoning_effort"` if set. Single turn, no tools, no streaming.
- **F30** Credentials (variable names only): bigmodel -- `<repo>/.env` `BIGMODEL_CHAT_URL` (must be
  `https://open.bigmodel.cn/api/paas/v4/chat/completions`) and `BIGMODEL_API_KEY` (weak_solver_probe.py:63-64, 140-147);
  free_router -- env file `OPENDATALAB_ROUTER_URL` (+ `/v1/chat/completions`, host `free-router.opendatalab.com`) and
  `OPENDATALAB_ROUTER_KEY`, plus a fresh `X-Session-Id` per call (weak_solver_probe.py:65-67, 150-162, 313-315);
  pjlab_token -- fixed `PJLAB_TOKEN_URL = "https://token.pjlab.org.cn/v1/chat/completions"` and `PJLAB_TOKEN_API_KEY`
  from `route_env` (weak_solver_probe.py:68-70, 165-171). URL check `_validated_url`: https, exact host, port None/443,
  exact path, no userinfo/query/fragment (weak_solver_probe.py:126-137). The v3 manifest binds
  `clients = {"repo", "proxy", "deepseek_route": "pjlab_token", "deepseek_env"}` (skillopt/coevo5/manifest.py:84-92; keys
  verified in /data/coevo5-20261019-v3-run-manifest.json); dl holds /root/.config/weak-solver/{pjlab-token.env, router.env, elucid.env} (ls).
- **F31** Retries inside `Client.call` (weak_solver_probe.py:305-345): at most 4 attempts, `BACKOFF = (10, 30, 60)`,
  `RATE_BACKOFF = (30, 90, 180)` for 429, on `httpx.TransportError` and statuses `{429, 500, 502, 503, 504}`
  (weak_solver_probe.py:91-93); other non-200 -> `error_type "http_<status>"` (+ `error_code`); bad JSON -> `"invalid_json"`;
  exhausted transport -> `"transport"`.
- **F32** Receipt fields (weak_solver_probe.py:268-303): `status, attempts [{status | error, seconds}], seconds, ok, response (message.content), finish_reason, usage {prompt_tokens, completion_tokens, total_tokens} or {}, usage_valid, returned_model, reasoning_chars (= len(message.reasoning_content))`;
  `error_type` in `error_payload, malformed_choices, malformed_finish, model_mismatch (+returned_model), thinking_mismatch, finish_<reason>, content_missing, empty_content`.
  `ok True` only for finish "stop", an allowed echoed model id and nonblank content. Thinking handling: when the route
  sends `thinking: disabled`, ANY `reasoning_content` makes the reply `thinking_mismatch` (weak_solver_probe.py:295-296),
  which is "undelivered" and resent (outcomes.py:66-67).
- **F33** Delivery classes (outcomes.py): undelivered = `UNDELIVERED_ERRORS = {"transport", "invalid_json", "error_payload", "malformed_choices", "malformed_finish", "model_mismatch", "finish_network_error", "finish_None", "thinking_mismatch"}` or `http_*` (outcomes.py:66-67, 176-182);
  noncompletion (fail) = `{"finish_sensitive", "finish_content_filter", "finish_length", "finish_max_tokens", "content_missing", "empty_content"}` (outcomes.py:69-70).
  Rows 4-5 read ONLY `receipts[-1]` (outcomes.py:251-263).
- **F34** coevo5 client factory `manifest._clients` caches one Client per `(model, max_tokens, read_timeout)` under a
  `threading.Lock`; deepseek-v4-flash gets `route`/`route_env` (manifest.py:95-113). Solver settings:
  `SOLVER_MAX_TOKENS = {"glm-5.3": 65536, "deepseek-v4-flash": 32768}`, `READ_TIMEOUT_SECONDS = 2400`,
  `DEEPSEEK_ROUTE = "pjlab_token"` (protocol.py:92, 327-330; units.py:97-103). Budget scopes know only two roots:
  `OVERALL` (GLM-5.3) and `DEEPSEEK` (budget.py:38-39, 59-64).
- **F35** The frozen GLM client of the continual-learning stack is a different interface
  (`CachedAPI.call(self, system, user, kind, key, ...)`, skillopt/validator_pilot/api.py:453) that admits only glm-5.3
  (api.py:30, 82, 98); coevo5 solver cells never use it.
- **F36** New endpoint (docs/project-status.md:14, not re-verified by me): settings in the local `.env` and dl
  `/root/.config/weak-solver/elucid.env`; 5 small dl probes delivered, model name correct, usage fields complete; "this
  model via this gateway always carries reasoning (`reasoning_content`; `thinking: disabled` not honoured)", so route B
  registers it as "with reasoning". Verified on dl: elucid.env defines exactly the variable NAMES `ELUCID_CHAT_URL`,
  `ELUCID_API_KEY`, `ELUCID_MODEL`. The probes /data/execskill-probe.py (47 lines) and /data/execskill-probe2.py (42 lines)
  use `urllib.request.urlopen` (which honours environment proxy variables) and tried `thinking` disabled/enabled,
  `reasoning_effort` none/low, `chat_template_kwargs.enable_thinking=False`, `reasoning.enabled=False`, `max_tokens 2`, and
  8 concurrent requests; probe 2 reads `usage.completion_tokens_details.reasoning_tokens` (request lines only, grep).

### 2.4 How coevo5 drives a cell

- **F37** `cells._solve` (cells.py:122-136): SpreadsheetBench -> `on_reply` enters `context.native.hold()` (3 slots) after
  the reply and holds it until `solve` returns (all cases executed inside solve); ALFWorld -> `context.episodes.hold()`
  (6 slots) for the whole episode; then exactly
  `backends.solve(benchmark, deepcopy(task["public"]), skill, recorder, runtime=deepcopy(context.runtime[benchmark]))`.
  `run_cell(context, cell, task, skill)` (cells.py:166) has no solver parameter; it calls the module functions `_solve`,
  `_replay`, `_score` (cells.py:184, 199, 209, 213).
- **F38** `run_cell` loop (cells.py:183-214): store prediction artifact; stop on ledger failure / broken assumption /
  invalid receipt; `preflight` (SpreadsheetBench decided before scoring); `_score` (SpreadsheetBench in a fresh scoring
  directory, native slot held, cells.py:152-163); `classify`; remedies REEXECUTE <= 2 (`_replay`: re-runs
  `backends.solve` with a `call` that asserts `_request_hash(system, user) == recorder.sends[-1]["request_sha256"]` and
  returns `recorder.receipts[-1]`, cells.py:139-149), RESCORE <= 2, RESTART <= 2 (ALFWorld env failed before any call,
  outcomes.py:298-301) (protocol.py:89-91). The record keeps every send with its receipt, the final verdict and token
  (cells.py:221-231).
- **F39** Concurrency: `run_parallel` = `ThreadPoolExecutor(max_workers=workers)` that stops dispatching after the first
  error (cells.py:237-258); v3 manifest `workers = 16` (verified on dl); evaluation launches the five benches as five
  child processes side by side (skillopt/coevo5/chain.py:169-177, 195-224); cross-process caps are file-lock slots
  `SLOTS = {"glm-5.3": 10, "deepseek-v4-flash": 12, "spreadsheet-native": 3, "alfworld-episode": 6}` (protocol.py:331;
  calls.py:39-122).
- **F40** Evaluation identity: `configuration()` = digest of `{benchmark, endpoint.model, endpoint.max_tokens, runtime[benchmark]}`
  (skillopt/coevo5/evaluation.py:308-311); the Skill is bound separately by `skill_sha256`.
- **F41** Skill text: one section per bench in ORDER (searchqa, officeqa, livemath, spreadsheetbench, alfworld;
  protocol.py:13), `"## <Title>\n<Applies when: ...>"` + seed text + `"- "` rule bullets (skillopt/coevo5/skill.py:63-74);
  `MAX_SKILL_BYTES = 20000` (protocol.py:48). The five task cards and their instructions are texts, frozen in the
  manifest (skillopt/coevo5/texts.py:31-96, 118-129).
- **F42** Code identity traps: the coevo5 manifest pins EVERY file under skillopt/ and scripts/ (manifest.py:44-48) and
  `verify_code` refuses to run if a pinned file changed or a loaded repo module is unpinned (manifest.py:71-81).
  `continual_eval.core.source_identity` hashes every `skillopt/continual_eval/*.py` (core.py:89-102) and `load_plan`
  refuses any plan whose rebuilt identity differs (core.py:294-297): ADDING a new .py to skillopt/continual_eval/ changes
  the identity of every continual-eval plan.
- **F43** Snapshot identity (verified on dl, SHA-256): backends.py, weak_solver_probe.py, cells.py, calls.py, protocol.py,
  manifest.py, outcomes.py are byte-identical in the local working tree, /data/skillopt-work and
  /data/coevo5-20261019-v3-source-f; /data/coevo5-20261019-v3-source (first v3 snapshot) differs in backends.py,
  weak_solver_probe.py, protocol.py, manifest.py, outcomes.py. Runs execute from these snapshot copies (protocol.py:1-5
  names the v1/v2 snapshots; v3 ops scripts use /root/continual-alf-prep-20260928/env/bin/python). A /proc scan found no
  running run_coevo5 / weak_solver_probe / cal1 process. Locally `git status`: backends.py modified vs HEAD,
  scripts/weak_solver_probe.py and skillopt/coevo5/ untracked.
- **F44** dl runtime interpreter /root/continual-alf-prep-20260928/env/bin/python: Python 3.11.16, httpx 0.28.1,
  openpyxl 3.1.5 (verified with python -c).

## 3. Interfaces an implementer would call or must replace

### 3.1 Frozen solver and scorer (module of functions: there is no class to subclass)

- `backends.solve(benchmark, public, skill_text, call, *, runtime=None) -> prediction` (backends.py:364).
  Available: `{"status": "available", "output": <str | {"code", "cases": [case]} | {"won", "steps"}>, "costs": {...}, "reason": str, ["code_delivery": {...}], ["trace": [...], "trace_version": str]}`.
  Unknown: `{"status": "unknown", "output": None, "costs": {}, "reason": str, ...}` (backends.py:69-70).
  Never raises for model trouble: exceptions from `call` become `"model_call_exception:<Name>"` (backends.py:93-94);
  QA/Sheet input errors become `"public_input_or_runtime_error:<Name>"` (backends.py:454-455); any ALFWorld exception
  becomes `"alfworld_environment_error:<Name>"` (backends.py:774-776). Side effects: Docker containers (Sheet), one
  spawned process per ALFWorld episode, temp dirs.
- `backends.score(benchmark, public, private, prediction, *, runtime=None) -> {"status": "pass"|"fail"|"unknown", "score", "reason", "metrics", ...}`
  (backends.py:517-566). Hidden audit only; the Sheet v7 scorer needs `runtime["_score_context"]` (cells.py:158-161).
- `backends.readiness(benchmark, runtime=None)` (backends.py:230-282): runs a `probe` container for Sheet.
- Private helpers a route-B solver would import unchanged (all verified by reading):
  `_public_view(benchmark, public)` (L73), `_response(call, system, user) -> (text | None, costs, reason)` (L90),
  `_sheet_preview(path, *, version=None)` (L342), `_xlsx_bytes(path)` (L285), `_native(request, runtime)` (L153),
  `_runtime_limits(runtime)` (L119), `_new_alfworld(public, runtime) -> _AlfSession` (L666), `_alf_post_observation(observations)` (L701),
  `_completed_without_text(receipt)` (L475), `_prediction_unknown(reason, **extra)` (L69), `_layout_supported(benchmark, runtime)` (L359);
  constants `LIVEMATH_CONTRACT`, `SHEET_CONTRACT_V2`, `CONTRACT_FIRST_LAYOUT_V2`, `CODE_EXTRACTION_VERSION`,
  `SHEET_PREVIEW_VERSION`, `ALFWORLD_TRACE_VERSION`, `ALFWORLD_TRACE_OBSERVATION_CHARS`, `MAX_RESPONSE` (L30-56).
  `code_delivery.extract_python(response) -> {"status", "reason", "code", "span", "candidate_kind", ...}` (code_delivery.py:21).
- `_AlfSession(config, game, split, seed, timeout)`: `.reset() -> (observations, None, [info])`,
  `.step([action]) -> (observations, None, scores, dones, [info])`, `.close()` (raises RuntimeError "ALFWorld worker
  cleanup unconfirmed") (backends.py:605-663). `info` holds `admissible_commands`, `won`, `extra.gamefile`, and in train
  mode `extra.expert_plan` (F22): a shell must whitelist.

### 3.2 Call contract (what any shell-side call wrapper must accept and return)

- `call(system: str, user: str) -> receipt: dict` with the fields of F32; at minimum `ok`, `response`, `finish_reason`,
  `usage`, `attempts` (1..4 dicts, else the ledger pauses the cell, F27), `error_type`.
- May raise `outcomes.BudgetStop`, `outcomes.AssumptionBroken`, `outcomes.LedgerFailure` (calls.py:163-196). A shell
  must let them propagate to `_response` unchanged (they are read back by name, outcomes.py:239-245).
- coevo5 side: `calls.Endpoint(client, *, model, max_tokens, slots, budget=None, scopes=(), cooldown=300, sleep=time.sleep)`
  (calls.py:136), `Endpoint.recorder(*, label, on_reply=None) -> Recorder` (calls.py:147), `Recorder(system, user) -> receipt`
  with attributes `receipts, sends, refused, invalid, broken, failed` (calls.py:261-279);
  `cells.Context(*, store, endpoint, runtime, native, episodes)` (cells.py:79); `cells.run_cell(context, cell, task, skill)`,
  `cells.run_cells(context, jobs, *, workers)`, `cells.run_parallel(function, jobs, *, workers)` (cells.py:166, 237, 261);
  `outcomes.classify(benchmark, prediction, score=None, receipts=(), *, refused=False, spent=frozenset()) -> Verdict`,
  `outcomes.preflight(...)`, `outcomes.undelivered(receipt)` (outcomes.py:176-228).
- Client: `weak_solver_probe.Client(...)` (F28) with `body(system, user)`, `_receipt(status, data, attempts, started)`,
  `call(system, user)`; instance attributes used by those methods: `url, _key, backend, model, max_tokens, thinking,
  effort, response_model_ids, http, _transport_errors` (weak_solver_probe.py:243-257, 259-345).

### 3.3 Adding the new endpoint as a NEW explicit backend identity (without touching frozen files)

Verified mechanics; the recipe itself is my proposal:
1. Do not edit `scripts/weak_solver_probe.py` (pinned in every coevo5 manifest, F42; byte-identical to the v3-source-f
   snapshot, F43). Put the new client in a new file outside `skillopt/continual_eval/` (F42), e.g.
   `skillopt/execskill/client.py`.
2. Subclass `weak_solver_probe.Client` but do NOT call `super().__init__` (it refuses any model outside `MODELS`,
   weak_solver_probe.py:232-233). Set the ten attributes listed in 3.2 yourself: `backend = "elucid"` (any value other than
   `"free_router"` sends no `X-Session-Id`, weak_solver_probe.py:314-315); URL from `ELUCID_CHAT_URL` checked with
   `_validated_url(url, "hk.getelucid.com", "/v1/chat/completions", ...)`; key from `ELUCID_API_KEY` via `_read_env`
   (weak_solver_probe.py:115-123, 126-137); require `ELUCID_MODEL == "deepseek-v4.1-flash-1017"`; `thinking = None` and
   `effort = None` so `body` sends neither field, and `_receipt` never marks `thinking_mismatch` (weak_solver_probe.py:262-265,
   295-296); `response_model_ids` = the exact echo set (to be verified, Q1); `httpx.Client(..., trust_env=False,
   follow_redirects=False)` with an explicitly registered proxy decision (Q2). `body`, `_receipt` and `call` (retries,
   receipt shape, attempts list) are inherited unchanged.
3. Optionally override `_receipt` to also record `usage.completion_tokens_details.reasoning_tokens` (the frozen receipt
   keeps only `reasoning_chars`, weak_solver_probe.py:291-294).
4. New protocol constants in the new package: the model's max_tokens and read timeout, a slot pool name (the `Slots`
   name check accepts `"deepseek-v4.1-flash-1017"`: `name.replace("-", "").replace(".", "").isalnum()`, calls.py:41-42),
   a budget scope root (budget.py `rooted` accepts only OVERALL or DEEPSEEK roots, budget.py:59-64), and a client config
   block naming the env-file path and the proxy. `backends.solve` is model-agnostic (it only sees `call`), so nothing in
   backends.py changes for a new model.

## 4. Reusable unchanged vs must be generalized

### Reusable unchanged
- U1 All scorers: `backends.score` (SearchQA EM, strict answer-tag for OfficeQA/LiveMath, v7 qualified recalculation for
  Sheet, ALFWorld `won`) and the ALFWorld/Sheet native machinery (`_native`, native_worker, `_AlfSession`,
  `_new_alfworld`) (F11-F17, F21-F23).
- U2 The frozen-prompt arm: calling `backends.solve` directly with the v3 runtime and a task-card Skill text reproduces
  v3's prompts byte for byte (F2-F7, F18-F19). Route B's "task card only" arm can be exactly this.
- U3 Format guard semantics: the contracts (F3) and extraction/scoring (F10, F17, F20) are fixed code, never learned.
- U4 The receipt contract, Recorder/Endpoint/Slots/ledger and the decision table for one-call-per-request semantics
  (F25-F33); `weak_solver_probe.Client` by subclassing (3.3).
- U5 v3 runtime values (images, timeouts, qualification, ALFWorld data/seed/split) can be copied verbatim (F14).

### Must be generalized (and the assumption each one bakes in)
- G1 QA/Sheet `solve` makes exactly ONE `_response` call (backends.py:417); `costs = {"calls": 1, ...}`. A shell with an
  expression-evaluation round needs a multi-call solve that sums usage per call.
- G2 The client is single-turn: `messages = [system, user]` (weak_solver_probe.py:260). Feeding a computed result back
  needs either re-packing (first reply + result) into one new user string, or a new multi-message call method on a new
  client identity. Both change the request bytes the ledger reserves for (ledger.py:26-36).
- G3 Sheet execution lives inside `solve` after the single reply (backends.py:437-452), the worker hides error text
  (F13), and `on_reply` takes a native slot after EVERY reply (cells.py:127-129, calls.py:277-278). Execution feedback
  cannot be done by wrapping `call`; a multi-call Sheet cell under the frozen `cells._solve` would try to hold several
  native slots at once (3-slot pool) -> deadlock risk (inferred from `Slots.hold` polling forever, calls.py:77-90).
- G4 ALFWorld loop has no hook between action parse and `env.step` (backends.py:752-762); the view keys, the 5-item
  history window, the system prompt and the absence of an admissibility check are hard-coded (F18-F20).
- G5 `cells._replay` assumes one request per cell (request hash of the LAST send, reply = LAST receipt; cells.py:139-149).
- G6 Delivery/noncompletion rows read only `receipts[-1]` (outcomes.py:251-263): with several calls per task the
  protocol must say which receipt decides.
- G7 Model identity is spread over hard allow-lists: `MODELS`/`ROUTES` (weak_solver_probe.py:76-88), thinking-disabled
  mismatch logic (L295-296), `SOLVER_MAX_TOKENS`, `SLOTS`, `DEEPSEEK_ROUTE` (protocol.py:327-331), budget roots
  (budget.py:38-39, 59-64), `units.CHAINS` solver names (units.py:37-46), `manifest._clients` routing only
  `"deepseek-v4-flash"` (manifest.py:108-109).
- G8 Evidence for replay tests: traces lack admissible commands and raw replies (F24); sends keep only request hashes
  (F26). Route B's "replay tests on recorded failures" need a new trace format (per-step view + raw reply + shell
  decisions) or deterministic re-simulation of ALFWorld from game file + seed + action list (re-simulation is inferred
  to be possible, not verified).
- G9 `MAX_SKILL_BYTES = 20000` bounds a TEXT Skill resent every ALFWorld step (protocol.py:48); procedure outputs injected
  into every step need their own size/cost bound.
- G10 `run_cell` hard-wires `_solve`/`_replay`/`_score` (F37): a shell needs a copy of the cell runner with an injectable
  solver (monkeypatching a frozen module is not acceptable for a registered protocol).
- G11 Evaluation identity digests model, max_tokens and runtime only (F40): route B must add the procedure-library hash
  and the shell/router version to its identity.

### Hook points (answer to (c))
Where a copied solver needs explicit hooks (line numbers are the frozen code they would replace):
- QA pre-call: after the system prompt is final (backends.py:391-394) and after the view is final (Sheet: 406-409),
  before `_response` (417). Hook: `pre(benchmark, public_view, system) -> (system, view, log)` -- rewrite/augment the user
  JSON (e.g. a new `"computed_facts"` field) or add a block after the guidance; the contract text must stay fixed.
- QA post-call: after `_response` returns (417-424), before extraction (425-436). Hook: parse an expression tag, compute,
  make a second call (G1-G2), the FINAL reply alone is extracted/scored.
- Sheet post-call: after extraction (433), before/around the per-case `_native` loop (437-450). Running the program on the
  public input and feeding back a result needs its own `_native` call and its own slot policy (G3).
- ALFWorld pre-call: view construction (744-746). Hook: add a state-record field, mark discouraged commands.
- ALFWorld post-call: between parse (752-756) and `env.step` (762): veto/replace the action (record both the model's and
  the executed action), optionally re-query (a second call in the same step). Post-step update after 762-764, where the
  hook sees the new observation and `infos` (whitelist: never `extra.expert_plan`/`extra.gamefile`, F22).
- Wrapping from outside (composition via the `call` argument) is POSSIBLE for QA and ALFWorld pre-call rewrites
  (parse `json.loads(user)`, re-dump with `ensure_ascii=False`, same key order) and for post-call reply rewriting or extra
  calls inside the wrapper, but: costs then under-report (G1), the prediction/trace do not record shell decisions (F24),
  the wrapper never sees `won`/`dones` or the last post-observation, the replay hash check needs a deterministic shell
  (G5), and coevo5's `run_cell` cannot even accept a wrapper without a copied cell runner (G10). It is NOT possible for
  Sheet execution feedback (G3). Recommendation (inferred): a new module (e.g. `skillopt/execskill/solver.py`, outside
  `skillopt/continual_eval/`) that copies `solve`/`_solve_alfworld` with explicit hooks and imports every helper and
  scorer from backends.py unchanged, plus an equivalence test: with no procedure enabled, every `(system, user)` pair
  (compare `calls._request_hash`) and the prediction must equal frozen `backends.solve` for the same task.

### Concurrency (answer to (e))
- `backends.solve` keeps no mutable module state (only `lru_cache(maxsize=2)` on `_sheet_scorer`, backends.py:458) and
  uses uuid4 container names and per-call temp dirs (backends.py:158-162): re-entrant across threads (verified by
  reading; not stress-tested). ALFWorld episodes run in separate spawned processes with private queues (backends.py:610-615).
  `ALFWORLD_DATA` must be set process-wide before launch and is never mutated (backends.py:669-673).
- The Client is shared by all threads of a process (one per (model, max_tokens, read_timeout), manifest.py:102-112);
  its only shared state is `self.http` (an httpx 0.28.1 Client; thread safety of httpx.Client is assumed, not verified
  here). Retries sleep in the calling thread (weak_solver_probe.py:320-329).
- One Endpoint per unit attempt shared by all cells; its latch attributes `halted`/`failed` are set without a lock
  (calls.py:143, 168, 213, 229) -- benign latch races (inferred). One Recorder per cell (not shared).
- Cross-process limits by fcntl file-lock slots (F39); ALFWorld holds an episode slot for the whole episode plus a model
  slot per step; Sheet holds a native slot from the reply until all cases ran, and again for scoring (cells.py:147, 162).

## 5. Gaps and risks for route B in this area

- K1 Reasoning always on (F36): registering the new model like the PJLAB route (`thinking: disabled`) would make EVERY
  reply `thinking_mismatch` -> 2 resends after 300 s each -> unknown (row 4). Use `thinking = None` (or the registered
  setting) and record reasoning tokens.
- K2 Ledger assumption with reasoning: if the gateway reports `completion_tokens > max_tokens` (reasoning outside the cap)
  or `prompt_tokens > request_bytes + 512` (an injected system prompt), the first receipt halts the whole ledger
  (ledger.py:69-71). The PJLAB gateway was seen adding about 90 prompt tokens to a one-sentence request
  (docs/project-status.md:201). Check both bounds in the smoke before any concurrent run.
- K3 Truncation: reasoning consumes `max_tokens`; `finish_reason "length"` is a counted failure (row 5, F33), most costly
  on ALFWorld (up to 50 calls per episode).
- K4 Proxy: the Client accepts only None or the PJLAB gateway (F28); whether hk.getelucid.com is reachable directly from
  dl is unverified (the probes used urllib, which honours environment proxies, F36). AGENTS.md requires explicit review
  of any other proxy destination.
- K5 Leakage through the shell: train-mode ALFWorld `infos` carry the expert plan and game path (F22); Sheet private
  `test_files` and QA private answers must never reach procedures; only `public` and the whitelisted view may.
- K6 Procedure crashes: an exception inside an ALFWorld shell becomes `alfworld_environment_error` (row 8 infrastructure
  unknown; restart only if before any call, outcomes.py:298-303); infrastructure share > 1/10 pauses a unit
  (protocol.py:84, evaluation.py:391-395). Shell code must catch and log procedure failures as their own outcome, and must
  NOT catch BudgetStop/AssumptionBroken/LedgerFailure (F26).
- K7 Sheet multi-call deadlock and missing error text (G3, F13).
- K8 Identity traps (F42): a new module inside skillopt/continual_eval/ silently changes every continual-eval plan
  identity; editing any pinned file breaks `verify_code` for v3 manifests run from that checkout.
- K9 Thin Sheet replay evidence: training tasks have one case each (F16), 120 training tasks in total.
- K10 Per-bench answer-extraction asymmetry: SearchQA falls back to the last line without a tag, OfficeQA/LiveMath do not
  (F17); a shell that adds intermediate tags must leave exactly one final, guarded reply.
- K11 Cost: ALFWorld resends system + Skill every step (F19); an injected state block is paid on every step.

## 6. Open questions for the designer

- Q1 Exact `model` string(s) echoed by hk.getelucid.com for `deepseek-v4.1-flash-1017` (needed for `response_model_ids`);
  whether `completion_tokens` includes reasoning tokens and respects `max_tokens`. (Probe logs not readable by me.)
- Q2 Direct connection from dl or via the PJLAB gateway? Was `proxy_on` active during the 17:0x probes?
- Q3 Does the gateway accept multi-message conversations (assistant turn + user follow-up), and does it inject its own
  system prompt (prompt-token overhead)?
- Q4 Sustainable concurrency / rate limits of the new gateway (probe 2 tried 8 concurrent requests; result unknown to me)
  -> slot count for the new model.
- Q5 Which "repaired v2 scorer" does design-v0 section 2 mean? No scorer by that name exists in skillopt/ or scripts/
  (grep); the current SearchQA scorer still has the last-line fallback (F17).
- Q6 Keep `alfworld_split: "train"` (expert plan present in `infos`, F22) or switch? Where do shell outputs go: a new
  user-JSON field vs the system prompt? Does the "placebo procedure" occupy the same field and add the same calls?
- Q7 Expression-tag grammar, the second-call protocol and how an invalid/failed computation is reported and scored.
- Q8 SpreadsheetBench test-panel case counts (deliberately not read) -- needed for container cost estimates.
- Q9 Max tokens and read timeout for the new model (deepseek-v4-flash used 32768 and 2400 s, protocol.py:92, 327).
- Q10 Docker images `sha256:0a0a5dcb...` and `sha256:f7f6f598...` present on dl? (not checked: docker is outside the
  allowed read commands; the v3 runs used them, which suggests yes -- inferred).
