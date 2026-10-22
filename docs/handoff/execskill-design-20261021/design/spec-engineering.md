# Route B registration-grade specification, angle C (engineering and safety first)

Status: COMPLETE draft for the opposing review (designer C), written 2026-10-21 17:45-18:08 HKT. Read-only on the repo
and on dl (no ssh used); no model call, no pytest, no test-pool item opened. Nothing here is registered yet; every
default marked D<n> is an owner decision (§11).

Inputs read: design-v0.md; understand/map.md (all); understand/{solver-backends, coevo5-infra}.md (all);
understand/{feasibility-prototypes, linux-ops, scorers-and-formats, data-and-pools, coevo5-method}.md (relevant sections);
docs/handoff/related-work-execskill-20261021.md §2, §6-9; docs/handoff/coevo5-registration-v6-20261017.md §1.1, §13.2-13.5;
docs/project-status.md:14; scratchpad execskill/probe/probe_elucid2.py. Citation tags: [SB] solver-backends, [CI] coevo5-infra,
[CM] coevo5-method, [FP] feasibility-prototypes, [DP] data-and-pools, [LO] linux-ops, [SF] scorers-and-formats, [MAP] map.md,
[RW] related-work note. Repo paths are repo-relative; `dl:` = the Linux machine. Number labels: "measured (source)" or
"estimate (assumptions)".

---

## 给负责人的一页摘要（中文；后面的技术正文给实现者，用英文）

这份是三份设计里"工程与安全优先"的一份。核心问题是：模型写的代码（"过程"、检测器、出题程序）要在实验里真正运行，
怎样保证它们**弄不坏实验本身**——不能偷看答案、不能联网、不能改评分、出错时不能把整次运行拖停、重跑必须得到一模一样的结果。

1. **身份**：新协议名 `fivebench-execskill-v1`，新代码包 `skillopt/execskill/`，开发机上全部新目录
   `/data/execskill-20261021-*`。第 3 版（v3）的代码、数据、结果一个字节都不动。
2. **模型写的代码只在"隔离箱"里跑**：隔离箱是开发机上已有的、版本钉死的 Docker 镜像（里面有 sympy、pandas 等计算库），
   断网、只读、无特权用户、限 CPU/内存/时间。每道题（ALFWorld 是每一局）开一个隔离箱，箱内每次调用再单独起一个子进程，
   崩了只影响这一次调用。过程只能看到"做题模型本来就能看到的东西"（题面、表格预览、可选动作），看不到参考答案、
   专家路线、文件系统、账本。
3. **过程出错 = 当作没有这个过程**（"失败即放行"）：这道题照常做，只是少了这一步帮助，并记一次"过程故障"。
   候选版本的故障率超过 2% 就不收。这样模型写的 bug 不会被算成"网络/基础设施故障"而让整次运行暂停。
4. **格式护栏在可学习部分之外**：每个 bench 固定的一句答案格式要求，所有组完全相同；壳保证任何过程都改不了模型的最终回答
   （改了就是"答案修补"，不算学到的 Skill）。ALFWorld 的"动作规范化"（把模型写的动作对齐到可选动作）对所有组都开。
5. **每步八个小步骤**都写成了可编程的规则和阈值（第 4 节）；验收是四组同时段逐题交错（新版本、旧版本、只有任务卡、
   安慰剂过程），外加"随机撤除"对照：在启用了某条新过程的题里随机抽一半，再跑一个"拿掉这条过程"的孪生格，
   这样每条过程的效果是因果的，不只是相关。
6. **新接口**（deepseek-v4.1-flash-1017）：关掉推理（`reasoning_effort: "none"`），每个回执都核对推理 token 为 0；
   网关可能不执行长度上限，所以账本按"2 倍名义上限"预留；另外我发现探查里"`max_tokens: 2` 返回 21 个 token"那一次
   **没有关推理**，所以"网关不执行上限"这个结论还没被干净地验证，冒烟第一项就是复测它。
7. **冒烟**（第 9 节）分四段：零调用检查（含隔离箱逃逸探针）→ 约 40 次的小接口探查 → 五个 bench 各几题的小规模真跑
   （每种钩子都要至少触发一次、故意注入一次过程故障）→ 一个完整小步骤。OfficeQA、SpreadsheetBench、LiveMath 的真题
   冒烟一题都不用（这些题太少），改用程序算答案的"工程夹具题"。
8. **试点**：默认按负责人认可的顺序先 SpreadsheetBench 后 OfficeQA（估计约 4,800 万到 7,200 万 token）。
   但我建议负责人考虑改成 **SearchQA → ALFWorld**：这两个 bench 新题充足；试点最可能暴露工程 bug，而 OfficeQA（74 题）和
   SpreadsheetBench（91 题）的题一旦在试点里用掉就再也没有"没用过的"了。代价是更贵（约 8,100 万到 1.05 亿）且不测程序路径。
9. **实话**：OfficeQA 和 SpreadsheetBench 这么少的题，只认得出约 10 到 12 分以上的效果；代码形式的过程跨任务迁移
   可能比文字差（2026 年一篇对照研究的结论），迁移读数要如实报告，包括"接近零"。
10. 需要负责人定的事列在第 11 节（共 18 项，每项给了默认值和我的建议），术语表在第 12 节。

---

## 0. Identity, boundaries, what is frozen

### 0.1 Names

| Item | Value |
|---|---|
| Protocol VERSION | `fivebench-execskill-v1` (records stamped `fivebench-execskill-v1-<kind>`: cell, unit, package, trajectory, evaluation, test-panel, sheet-qualification, manifest, smoke, chain, report, consumption) |
| Package | `skillopt/execskill/` (outside `skillopt/continual_eval/`, because adding any .py there changes every continual-eval plan identity: core.py:89-102, 294-297 [SB F42]) |
| CLI | `scripts/run_execskill.py` |
| Tests | `tests/test_execskill_*.py`, fakes `tests/execskill_fakes.py` (port of tests/coevo5_fakes.py [CI F45]) |
| Git branch | `research/exec-skill-coevolution` (docs/project-status.md:14); must also carry the untracked v3 files it imports (skillopt/coevo5/, scripts/weak_solver_probe.py) [MAP B9] |
| dl snapshot | `/data/execskill-20261021-source` (rsync copy, sha256-verified; never edited after verification) [LO §7] |
| dl ops | `/data/execskill-20261021-ops` (NOT `/data/execskill-ops/`, which another agent's probe owns [LO F2]) |
| dl pre-launch / smoke | `/data/execskill-20261021-pre` |
| dl pilot run root | `/data/execskill-20261021-pilot` ; full run (later, separate registration delta) `/data/execskill-<date>-run` |
| dl manifest | `/data/execskill-20261021-pilot-manifest.json` |
| dl route-B history (cross-root) | `/data/execskill-history/` (consumption registry spanning smoke, pilot and full run; §2.3) |
| dl slot root for the elucid pool | `/data/execskill-slots/` (machine-wide for all route-B processes; owner decision D16) |
| tmux sessions | `execskill-<chain>`, `execskill-prep`, `execskill-smoke` |

All paths must be real paths with no symlink component (`safe_path`, continual_eval/core.py:35-39 [CI F4]).

### 0.2 What is frozen and must not change

- Every file of the v3 protocol: `skillopt/coevo5/*.py`, `skillopt/continual_eval/*.py`, `scripts/run_coevo5.py`,
  `scripts/weak_solver_probe.py` (pinned in every coevo5 manifest; `verify_code` refuses a changed pinned file:
  manifest.py:44-48, 71-81 [SB F42]). Route B imports some of them unchanged; it never edits them.
- All dl artifacts under `/data/coevo5-*`, `/data/feasibility/*`, `/root/continual-*` (read-only inputs; route B opens only
  the pinned inputs listed in §2 and the manifest).
- The frozen scorers (`backends.score`, env evaluators) and the SpreadsheetBench v7 chain; scorer v2 is a new module (§1.6).

### 0.3 Import-versus-copy (closed-set rule, A14)

Importing any coevo5 module that does `from .protocol import ...` stamps v3 identities (cells.py:222, units.py:154,
evaluation.py:199/367/396, qualify.py:124/136, manifest.py:119, smoke.py:112, chain.py:275 [CI F2]). Therefore:

| Treatment | Modules |
|---|---|
| Import unchanged (protocol-free or universal constants) | `skillopt.coevo5.{budget, ledger, calls, outcomes, stats, checks, roles, leakage(normalize, Corpus, findings, mechanical)}`; `skillopt.continual_eval.{backends (helpers + score), code_delivery, native_worker (not used by the sandbox), sheet_*}`; `scripts.weak_solver_probe.Client` (subclassed) |
| Copy with VERSION `fivebench-execskill-v1` | cells, units (run_unit, complete, unit_path, cell_context), evaluation (multi-arm), qualify (with an importable-version list), manifest, prelaunch helpers, smoke, chain, CLI; step.py primitives (`run_round`, `_order`, `table_of`, `shared_unanswered`, `guard`, `key`, `bench_of`, `pool_tasks`) copied without importing step [CI 3.9] |
| Write new | protocol.py, client.py, solver.py (shell + hooks), router.py, package.py, sandbox/ (host client + in-container worker + AST policy), compute.py, judge.py (scorer v2), trajectories.py, replay.py, detectors.py, generators/ (per bench), roles_code.py (engineer/examiner parsers), registry.py (consumption), acceptance.py, attribution.py (withholding twins), readout.py, budgets.py (scope helpers) |

Exception classes form ONE set: copied cells/units import `BudgetStop, AssumptionBroken, LedgerFailure,
ConfigurationError, CleanupUnconfirmed` from `skillopt.coevo5.outcomes`, because the imported `budget.py` raises exactly
those classes (budget.py:36) and the copied `STOP_KINDS` maps classes (cells.py:45-46, units.py:149) [CI §4 pitfall].
New route-B exceptions (`SandboxUnavailable`, `PackageInvalid`, `ConsumptionConflict`) are defined in
`execskill/errors.py` and added to the copied `STOP_KINDS` as kind `sandbox`, `configuration`, `consumption`.
Unit test (required): a `BudgetStop` raised inside a copied cell is recorded with stop kind `budget`, not `exception`.

### 0.4 Evidence-status labels used in all outputs (AGENTS.md)

Every result record carries `evidence` in {`engineering_fixture`, `smoke`, `pilot_real_run`, `historical_replay`}.
Fixture items and fixture procedures (§9) are never counted as learned Skill or as accepted procedures.

## 1. Objects (procedure package, task cards, router, format guards, shell)

### 1.1 Procedure package (the learnable object)

Canonical JSON, content-addressed: `package_sha256 = digest(package)` with `digest` = sha256 of
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` (validator_pilot/api.py:40-41 [CI F4]).
Stored write-once at `<root>/packages/<sha256>.json`.

```python
@dataclass(frozen=True)
class Procedure:
    id: str                    # "p-<bench_of_origin>-<k>-<n>", [a-z0-9-]{3,48}, unique in the package
    origin: str                # bench where it was accepted (one of ORDER)
    accepted_at: str           # "<chain>/s<k>/t<j>"
    description: str           # <= 600 chars, plain text; leakage-checked
    hooks: tuple[str, ...]     # subset of HOOKS (below); each needs a function of that name in `source`
    source: str                # one Python module, <= 6,000 UTF-8 bytes; must define applies(view) and the hook functions
    max_note_chars: int        # declared cap of any note it emits (<= 1,500)
    requests_second_call: bool # True only for procedures whose after_reply may request the compute round trip
    state_schema_bytes: int    # declared cap of its JSON state (<= 16,384); 0 = stateless
    replay_tests: tuple[dict, ...]  # 1..10 tests, format §1.7
    lineage: dict              # {"parent": id|None, "revises": id|None, "engineer_call": request_sha256}

@dataclass(frozen=True)
class Package:
    version: str = "execskill-package-v1"
    parent_sha256: str | None
    procedures: tuple[Procedure, ...]   # sorted by id; <= 24 procedures; total source <= 64,000 bytes
```

HOOKS (closed set; each bench supports a subset, §1.5):

| Hook | Signature (pure function; all args JSON values) | Allowed effect |
|---|---|---|
| `applies(view) -> bool` | public view of the item (QA/Sheet) or the episode's initial view (ALFWorld) | routing only |
| `before_call(view, state) -> {"note": str, "state": obj}` | QA/Sheet: once before the first call | add one note to `procedure_notes` |
| `after_reply(view, reply, state) -> {"compute": [str], "state": obj}` | QA: after the first reply | request exact computation of <= 8 expressions (compute round trip, §1.5.2) |
| `sheet_feedback(view, run_report, state) -> {"note": str, "request_repair": bool, "state": obj}` | Sheet: after the program ran on the public input | request ONE repair call with a note (§1.5.3) |
| `alf_before_step(view, state) -> {"note": str, "veto": [str], "state": obj}` | ALFWorld: before each step's call | add a note; propose commands to remove from the shown list |
| `alf_after_step(event, state) -> {"state": obj}` | ALFWorld: after `env.step` | update state only |

No hook can (a) change the system prompt, (b) change the contract sentence, (c) change, extract or rewrite the final reply,
(d) choose or substitute an action, (e) see anything outside its arguments. These are structural: the shell has no API
for them.

### 1.2 Task cards (frozen, A5)

- Text per bench = the v3 I-ds seed instruction (the five GLM-written instructions imported for v3,
  `dl:/data/coevo5-20261019-v3-pre/texts/texts.json` key `instructions`; sha256 prefixes searchqa 48b10afcc1dd0dcf,
  officeqa 2e92500a832ee32e, livemath 9cb3d860ec6970b5, spreadsheetbench 48a5df7f745606ba, alfworld 5ae6ea9bffa3902e;
  lengths 1,846 / 2,926 / 2,068 / 2,907 / 2,301 chars, measured ([CM 2.10b])). Pinned by sha256 in the manifest;
  read through a copied `import-texts` path that accepts exactly the version `fivebench-coevolution-v3-texts`.
- Rendering: ONLY the active item's bench card enters the guidance slot: `skill_text = seed_text(card[bench])` (headings
  demoted as `skill.seed_text` does [CM 2.10b]); the other four cards are absent. Reason: the whole-Skill render showed every
  bench's format advice to every task (skill.py:63-74) and answer-format conflicts cost -9.5 to -33 points on OfficeQA
  (E4/E9, measured [FP F51-F52]).
- Rationale for the I-ds instruction over `texts.CARDS`: it is the strongest known text baseline (cal-1 ids-full totals 154.5
  vs seed-only 153.5 vs parent:A 135.75 on 200 SearchQA items x 4 runs, measured [FP F42]); the task-card-only arm is exactly
  this text plus the frozen contract sentence.

### 1.3 Router (fixed code, deterministic)

```python
def route(package, bench, view, *, withhold: frozenset[str]) -> RouteLog:
    # for p in package.procedures (sorted by id): sandbox.call(p.id, "applies", {"view": view})
    # value must be exactly True/False (JSON bool) else fault "malformed"
    # enabled = {p | applies is True and p.id not in withhold}
    # RouteLog = {"package_sha256", "bench", "per_procedure": {id: {"applies": bool|"fault", "enabled": bool,
    #             "withheld": bool, "fault": None|kind}}, "enabled": [ids sorted], "route_sha256"}
```

- Runs once per item (QA/Sheet) or once per episode on the reset view (ALFWorld). Per-step gating is internal to
  `alf_before_step` (it may return an empty note and empty veto).
- A predicate fault (crash/timeout/malformed) = procedure NOT enabled, logged `predicate_fault` (fail-closed for routing =
  fail-open for the cell, A6).
- Routing never depends on outcomes, labels ("general"/"this bench only"), test reads or other items. Labels are reporting
  labels only (§7.4).
- RouteLog is stored inside the prediction dict under key `shell` (stored by hash with the prediction, cells.py:187
  [CI G3]), and a compact copy in the cell record (`enabled`, `withheld`, `route_sha256`).

### 1.4 Format guards (fixed, outside the learnable part)

| Bench | Contract (system prompt, identical in every arm) | Layout | Guarantee |
|---|---|---|---|
| SearchQA, OfficeQA | `"\nReturn the concise final answer inside <answer>...</answer>."` (backends.py:381-382) | contract-first-v2 | reply scored raw |
| LiveMath | `LIVEMATH_CONTRACT` (backends.py:35) | contract-first-v2 | reply scored raw |
| SpreadsheetBench | `SHEET_CONTRACT_V2` (backends.py:53-56) | contract-first-v2 | program extracted by frozen `code_delivery.extract_python` |
| ALFWorld | fixed system `"Act in the text environment. Return a single action inside <action>...</action>."` (backends.py:730) | frozen ALFWorld order | registered action canonicaliser for EVERY arm (§1.5.4) |

- Instruction only; no output transformation for QA/Sheet (A5; [SF R2]). Invariant tested per cell:
  `delivered_reply == model_reply` byte for byte (QA) and `scored_code == extract_python(model_reply).code` (Sheet);
  `guard_changed_answer` is therefore always False for QA/Sheet and is recorded anyway.
- ALFWorld: the canonicaliser is part of the environment interface, identical in every arm; its per-step `how` is logged
  and its rescue share per arm is reported (§10 R5).

### 1.5 Shell (fixed code; `skillopt/execskill/solver.py`)

A copy of `backends.solve` (:364-455) and `_solve_alfworld` (:715-783) with explicit hook points [SB §4], importing every
helper unchanged (`_public_view`, `_response`, `_sheet_preview`, `_xlsx_bytes`, `_native`, `_runtime_limits`,
`_new_alfworld`, `_AlfSession`, `_alf_post_observation`, `_completed_without_text`, `_prediction_unknown`,
`_layout_supported`, the contract constants). Signature:

```python
def solve(bench, public, card_text, package, call, *, runtime, sandbox, withhold=frozenset(), placebo=None) -> dict
# returns today's prediction shapes [MAP 2.5] plus key "shell":
# {"route": RouteLog, "calls": [{"purpose": "first"|"second"|"repair"|"step:<i>", "request_sha256", "receipt_index"}],
#  "procedure_events": [...], "faults": [{"procedure", "hook", "kind", "exc_type", "message"<=500}],
#  "notes_chars": int, "deciding_receipt": int, "fallback": None|reason}
```

**Equivalence test (required, zero-call):** with an empty package and `placebo=None`, every `(system, user)` pair
(`calls._request_hash`) and every prediction equals frozen `backends.solve(bench, public, card_text, call, runtime=...)`
on fixture tasks of all five benches, using a scripted fake `call` [SB §4].

#### 1.5.1 Where notes go

- Notes are appended to the user JSON as the LAST key: `view["procedure_notes"] = [{"id": p.id, "note": text}, ...]`
  (package order), serialized with `json.dumps(view, ensure_ascii=False)` exactly as frozen (backends.py:417). Absent when
  no note. The system prompt (base + contract + card) is byte-identical across S', S and P arms of the same bench.
- Note budget per request (registered): QA/Sheet 4,000 chars total; ALFWorld 1,500 chars per step total. Applied in
  package order; a note that would exceed the remaining budget is dropped whole (`note_budget_skip`, deterministic, not a
  fault). A note over its procedure's own `max_note_chars` = fault `over_cap`.
- Cost anchor: ~250 prompt tokens per 1k chars per ALFWorld step (measured, FD/D14 report §3.2 [FP F17]).

#### 1.5.2 QA compute round trip (A10)

1. First call: `(system, user)` with notes. 2. If any enabled procedure with `requests_second_call` returns `compute` from
`after_reply`, the shell evaluates each expression with FIXED code `execskill/compute.py` (host side; it parses, never
`exec`s): grammar = decimal/integer literals, `+ - * / **` (integer exponent |e| <= 12), parentheses, unary minus,
`abs`, `round(x, n)`, `min`, `max`, `sum([...])`; exact `Fraction` arithmetic (a copy of the `forward.evaluate`/`literals`/
`rounded` kernel, forward.py:196-231 [SF F27]); <= 8 expressions, each <= 300 chars; result rendered as an exact decimal when
terminating, else 12 significant digits, marked `approx`. 3. Second call (at most one per item): user JSON =
`{**view, "procedure_notes": [...], "first_reply": <first reply>, "computed": [{"expr", "value"}], "instruction":
COMPUTE_FOLLOWUP}` with the fixed `COMPUTE_FOLLOWUP = "The expressions above were evaluated exactly. Use these values if
they are relevant and give your final answer in the required format."`. 4. Final reply = second reply if its receipt is
`ok`, finish `stop` and not suspected-truncated (§3.1.4); otherwise the first reply (`fallback: second_call_failed`).
5. `deciding_receipt` = index of the receipt whose reply is final; the copied cell passes ONLY that receipt to
`outcomes.classify(..., receipts=[deciding])` for rows 4-5 (which read `receipts[-1]`, outcomes.py:251-263 [SB G6]); all
receipts are charged by the ledger and stored. 6. A malformed compute request (grammar error, division by zero, over cap)
is not a fault of the cell: the expression's value is `"error: <class>"` and the round trip proceeds.

#### 1.5.3 SpreadsheetBench program path

- `before_call` notes go into the user JSON (as 1.5.1). Procedures receive the view the frozen solver builds (instruction,
  `workbook_preview`, input/output paths, answer position; backends.py:397-409) plus `input_workbook_b64` of the FIRST input
  case only (public; <= `MAX_WORKBOOK_BYTES` = 8 MiB, v3 protocol.py:93, copied), so table-extraction procedures can read cells.
- `sheet_feedback` (optional): after the first reply, the shell runs the extracted program ONCE on the public input in the
  native image (`_native`, a native slot held only for that execution), builds `run_report = {"status", "exc_type",
  "message" (last traceback line, <= 500 chars, from a COPIED worker that returns it, unlike native_worker.py:113-114
  [SB F13]), "answer_cells": values at the required answer position (<= 2,000 chars)}`. If a procedure returns
  `request_repair: True`, ONE repair call is made (user JSON = view + notes + first program + run_report + its note); the
  repair reply's program is final if delivered; else the first program (fallback). Then the frozen per-case execution
  (backends.py:437-452) runs on the final program.
- Slot policy (fixes [SB G3] deadlock risk): the native slot is held only around each `_native` execution, never across a
  model call; the copied cell runner does NOT use v3's `on_reply` slot grab.

#### 1.5.4 ALFWorld per-step loop (A9)

Copied loop, split `"train"`, `max_steps` 50, seed 42, trace version `execskill-alfworld-trace-v1`. Per step i:
1. `view = {initial_observation, observation, admissible_commands, recent_history[-5:]}` exactly as frozen
   (backends.py:744-746). Procedures receive `view` + `{"step": i, "max_steps": 50}`; never `infos` (whitelist removes
   `extra.expert_plan`, `extra.gamefile`, `won`) [SB F22].
2. `alf_before_step` for each enabled procedure: notes (budget 1,500 chars) and veto lists. Shown list =
   `admissible_commands` minus the union of vetoes, in original order; the shell refuses a veto that would leave fewer than
   2 commands (logged `veto_floor`, not a fault); vetoed commands are listed in a fixed note
   `"Not recommended now: ..."` (registered text) so the model can still type them.
3. Model call; reply parsed by the registered canonicaliser (D3 `parse`/`canonical`, ~30 lines,
   pilot_alf_glm.py:165-195 [FP F7, R4]) applied against the FULL admissible list: tag -> whole -> canonical (strip
   `action:` wrappers, case-insensitive match) -> unchanged. `how` logged. Empty or > 1000 chars -> `invalid_action_format`
   (frozen rule, backends.py:754-756).
4. `env.step([action])` with the canonical action (a vetoed command typed by the model is executed; `veto_overridden`
   logged).
5. `alf_after_step(event={"action", "how", "post_observation"[:12000], "admissible_commands_next"}, state)`.
6. Trace step record: `{i, view_sha256, shown_commands, notes, vetoes, reply, action, how, post_observation[:12000],
   procedure_calls: [{id, hook, args_sha256, result_sha256, fault}], state_sha256: {id: sha}}`.
- The ALFWorld arm without procedures (task-card only) runs the same copied loop with the same canonicaliser: the
  canonicaliser can therefore not flip signs between arms (A9; [FP K1]).
- Per-step `max_tokens` M_alf (§3.1) and the fixed system prompt + card are resent every step (cost driver [FP F17]).

### 1.6 Judge record per cell (scorer v2, A2)

New module `skillopt/execskill/judge.py`, VERSION `execskill-judge-v2`. Per cell it stores four blocks:
`official` (frozen `backends.score` + `outcomes.classify`, both kept: official status and completion-aware `final`),
`v2`, `lenient` (descriptive), `format` flags. v2 rule for QA: verdict pass iff official pass OR the last JSON object with
key `"answer"` (string or number; also inside a ```json fence; also a JSON object that is the whole content of the last
answer tag) passes the frozen comparison (SearchQA `exact_match`, OfficeQA `officeqa.evaluator.exact_match`, LiveMath
strict single letter) [SF 3b.2]. SpreadsheetBench and ALFWorld: `v2 = official` written explicitly. Completion-aware:
truncated, filtered, empty, malformed -> fail (outcomes.py:69-72, 261-262 [SF F7]). Unit invariant: for every cell,
`v2.pass >= final.pass` (never a v2 fail where completion-aware official passes). Decision metric = `v2.token`
(completion-aware). Format flags as listed in [SF 3b.4], plus `over_nominal_cap`, `suspected_silent_truncation`,
`compute_round_trip`, `repair_call`, `canonical_rescue_steps`, `veto_overridden_steps`.

### 1.7 Replay tests (format, storage, meaning of "passes")

```json
{"id": "rt-1", "trajectory": "<bench>/<item_id>/<arm>/<run>/<unit_sha16>", "hook": "alf_before_step", "step": 14,
 "property": {"kind": "veto_contains", "value": "go to drawer 1"}}
```

- `trajectory` references a stored trajectory of the CURRENT step's run unit (training items only).
- `property.kind` is a closed set of FIXED checkers (not model code): `applies_true`, `applies_false`, `note_contains`
  (substring <= 200 chars), `note_matches` (regex <= 200 chars, compiled with a 50 ms match timeout), `veto_contains`,
  `veto_excludes`, `compute_contains` (an expression whose exact value equals a given decimal), `repair_requested`,
  `state_equals` (JSON-pointer <= 8 segments, JSON value <= 200 chars).
- A test passes iff the procedure, executed twice in the sandbox on the recorded hook inputs of that trajectory (replaying
  `alf_after_step` from step 0 to rebuild state), returns identical outputs both times and the property holds.
- Replay proves determinism, absence of crashes and that the procedure does what its author claims on the failure. It does
  NOT prove that the solver then succeeds (that needs model calls); acceptance is decided only on the fresh real batch
  ([CM §5.9]).
- Storage: inside the procedure record (package JSON); results in `<engineer unit>/attempt-N/candidates/<n>/replay.json`.

### 1.8 Procedure runtime: the sandbox (A3)

**Threat model.** Model-written code (procedures, predicates, detectors, generators, the engineer's replay helpers) may be
buggy, slow, nondeterministic, or adversarial by accident (reading files, opening sockets, printing to stdout, keeping
hidden state, encoding answers). It must not: reach the network; read anything except its arguments; see `private`,
references, expert plans, game paths, the ledger, keys or the test registry; write outside a tmpfs; outlive its call;
desynchronize the shell; make a cell nondeterministic. The security boundary is the CONTAINER. The AST policy and the
import whitelist are hygiene and determinism layers, not the boundary (D6's host-process `sandbox_runner.py` keeps
exec/eval reachable and is not a boundary [FP F33, G5]).

**Substrate.** The pinned native image `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd`
(tag `evolve-skill-native:smoke-20260928`; python with sympy 1.13.3, pandas 2.2.3, numpy 1.26.4, openpyxl 3.1.5,
build import-checked; present on dl, measured [LO F29-F30, SF F25]). No new image is built. sympy for host-side code is
NOT needed: all model-written code, including generators that use sympy, runs in this image.

**Container command** (copied from `backends._native` hardening, backends.py:169-178 [SB F12], tightened):

```
docker run -i --pull=never --name execskill-sbx-<uuid4> --network=none --read-only --user=65534:65534
  --cap-drop=ALL --security-opt=no-new-privileges=true --pids-limit=64 --memory=<M>m --memory-swap=<M>m --cpus=<C>
  --ipc=private --shm-size=16m --no-healthcheck --log-driver=none --ulimit=nofile=64:64 --ulimit=core=0:0
  --env EXECSKILL_SANDBOX=execskill-worker-v1 --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 --workdir=/tmp
  --mount type=bind,source=<host dir with worker.py + policy.json only>,target=/runner,readonly
  --entrypoint=python <image> -I -B /runner/worker.py
```

- `M`/`C`: QA/Sheet cell worker 384 MiB / 0.5 CPU; ALFWorld episode worker 384 MiB / 0.5 CPU; examiner generator worker
  1024 MiB / 1 CPU. Idle workers use no CPU; resident memory of a loaded worker is estimated at 100-200 MB (not measured;
  S2 measures it). Registered; ranges validated like `_runtime_limits` (backends.py:119-129).
- Cleanup: `docker rm --force` bounded at 10 s, then `docker ps -a --filter name=execskill-sbx-` must not list it; an
  unconfirmed cleanup raises `CleanupUnconfirmed` (outcomes row 3: the cell stops, the unit pauses), exactly the v3 rule for
  native containers (backends.py:188-198 [SB F12]).
- No `--env` carries anything but the fixed marker; the docker CLI subprocess is started with a scrubbed environment
  (`env={"PATH": "/usr/bin:/bin"}`), so ambient `OPENAI_API_KEY`/proxy variables of `bash -i` shells (.bashrc:148-150
  [LO §5]) never reach the CLI or the container.

**Lifetime (A3: long-lived worker per cell or episode).** One container per QA/Sheet cell that has >= 1 procedure or the
placebo (task-card-only cells start none); one per ALFWorld episode; one per examiner job. Inside, the worker loads the
package once, then serves calls; EVERY call runs in a freshly `os.fork()`ed child (copy-on-write of the loaded modules) with
`RLIMIT_CPU` 2 s, `RLIMIT_AS` 384 MiB (ALFWorld 256 MiB), wall alarm 3 s, and returns through a pipe. Consequences:
(i) a crash, OOM or infinite loop kills only that child; (ii) module-level state mutated in one call vanishes, so hidden
state is impossible and state must travel in the explicit `state` argument held by the host; (iii) the worker can be
restarted at any time without losing information.
Rejected alternatives (with cost): container per call — an ALFWorld episode makes ~35 steps x (2-4 hook calls) = 70-140
container starts; at an estimated 0.5-1.5 s per `docker run` on dl (estimate: not measured on dl [LO §5]) that is
35-210 s of extra wall time and CPU per episode, while 6 episodes already compete for 7 CPUs [LO F1]; in-process restricted
runner — no security boundary, and the host process holds the ledger, key paths and test access.

**Worker protocol** `execskill-worker-v1`, line-delimited JSON on stdin/stdout, one response line per request, max line
65,536 bytes; stderr discarded inside the container.

```
-> {"op":"load","protocol":"execskill-worker-v1","package_sha256":..,"procedures":[{"id","source","hooks"}],"policy_sha256":..}
<- {"op":"load","ok":true,"loaded":[ids],"rejected":[{"id","reason"}]}      # reason: syntax|policy:<rule>|missing_hook
-> {"op":"call","seq":n,"proc":id,"fn":hook,"args":{...}}
<- {"seq":n,"ok":true,"value":<JSON>,"cpu_ms":int,"value_sha256":hex}
<- {"seq":n,"ok":false,"fault":"exception|timeout|memory|malformed|over_cap|forbidden","exc_type":str,"message":str<=500,"line":int|null}
-> {"op":"ping"}  <- {"op":"pong","worker_sha256":..}
```

- Output serialization in the child: `json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)`; non-JSON
  values, NaN, > cap -> `malformed`/`over_cap`. Caps: note <= `max_note_chars` (<= 1,500); veto <= len(admissible);
  compute <= 8 x 300 chars; state <= `state_schema_bytes` (<= 16,384); whole value <= 32,768 bytes.
- Host client (`sandbox/client.py`): per-call host timeout 6 s (child wall 3 s + margin). On worker death, EOF, a
  malformed line or a `seq` mismatch: restart the container ONCE, reload the package, retry the SAME call once (safe:
  calls are pure and deterministic). If the retried call returns a fault -> procedure fault. If the restart itself fails
  (image missing, docker error, cleanup unconfirmed) -> `SandboxUnavailable` -> cell stop, unit pause (kind `sandbox`),
  owner recovery as in v3 §13.4.

**AST/import policy** (`sandbox/policy.json`, hashed into the manifest; applied at load time in the worker AND at
engineer-check time on the host by fixed code):
- Allowed imports: `re, math, cmath, fractions, decimal, statistics, itertools, functools, collections, operator, string,
  json, difflib, unicodedata, heapq, bisect, dataclasses, typing, enum, numbers, copy, textwrap, datetime, sympy, mpmath,
  numpy, pandas, openpyxl` (pandas/openpyxl only in Sheet-scoped code; `datetime` without `now/today/utcnow`).
- Forbidden names/calls: `exec, eval, compile, open, input, __import__, globals, locals, vars, getattr, setattr, delattr,
  breakpoint, exit, quit, help, memoryview, id, hash` (hash is salted per process: nondeterministic); any attribute whose
  name starts with `__`; any `time`, `random`, `os`, `sys`, `subprocess`, `socket`, `importlib`, `ctypes`, `pickle`,
  `marshal`, `threading`, `multiprocessing`, `signal`, `inspect`, `gc`, `io`, `pathlib`, `shutil`, `tempfile`, `urllib`,
  `http` usage; `while True` without a `break` (cheap static guard; the CPU limit is the real one); module-level code other
  than imports, constants (literals <= 2,000 chars) and function/class definitions.
- Iteration over `set`/`frozenset` whose order matters is a determinism risk: caught by the double-run check, not statically.

**Determinism check.** Every replay and every zero-crash call is executed twice in separate children; differing
`value_sha256` -> fault `nondeterministic`. At run time, the shell logs `(proc, fn, args_sha256, value_sha256)` per call;
re-execution of a cell (REEXECUTE remedy, cells.py:139-149) re-runs the shell, and a request-hash mismatch is recorded as
fault `nondeterministic` for the cell: the candidate's cell token becomes `unknown` and is scored by the L/H rule (fail for
the judged arm, pass for comparators, stats.py:3-6 [CM F38]); it counts toward the fault cap and never pauses the unit.

**Escape probe (fixed test code, smoke §9 S0).** Inside the same container command, a registrar-written probe must observe:
`socket.connect(("1.1.1.1", 53))` fails; writing `/runner/x` and `/x` fails; `os.getuid() == 65534`; `os.environ` contains no
key other than the fixed list recorded at the first smoke (expected: docker's defaults PATH/HOSTNAME/HOME plus
`EXECSKILL_SANDBOX`); `/proc/1/cmdline` is the worker; no file under `/`
matches `*.env`, `*key*`, `consent*`, `ledger*`; a fork bomb stops at `--pids-limit`; a 2 GiB allocation dies at the memory
limit. Any deviation blocks the launch.

### 1.9 Trajectories and enable logs

- Every cell writes ONE trajectory record `fivebench-execskill-v1-trajectory` at `<attempt>/trajectories/<cell_id>.json`
  (write-once), containing: cell key, `package_sha256`, RouteLog, all requests as TEXT for training-side units (system +
  user; v3 stored only hashes [SB F26]; route B needs text for replay), all replies, receipts summary, shell events,
  procedure calls with args/results hashes, the ALFWorld step records (§1.5.4), the judge blocks and the decision token.
- Test-side cells (evaluation units) store hashes only (no request text), in the sealed evaluation store, so no test text
  ever reaches a role or a replay set.
- Enable log = per cell `{"enabled": [...], "withheld": [...], "applies": {id: bool|fault}}`, indexed by
  `(unit, arm, bench, item, run)` in `<unit>/enable_log.jsonl` (append-only, written after the cell record).

### 1.10 Cell record and new decision-table rows (A6)

Copied `cells.run_cell` with VERSION stamp, an injectable solver (`solve` above), and record keys = v3's
(cells.py:221-230 [CI F18]) plus `package_sha256`, `arm_kind` in {`candidate`, `parent`, `card`, `placebo`, `withhold:<id>`},
`enabled`, `withheld`, `faults` (count by kind), `deciding_receipt`, `judge` (§1.6), `evidence`.
Rows added in front of the imported `outcomes.classify` (in `execskill/outcomes_ext.py`; the frozen table is not edited):

| New row | Condition | Outcome | Effect |
|---|---|---|---|
| P1 procedure fault | crash, timeout, memory, malformed, over_cap, forbidden, nondeterministic (at first execution) in any hook | the cell proceeds WITHOUT that procedure from that point (fail-open to parent behaviour); verdict by the normal rows | counted in `faults`; arm fault rate feeds the 2% cap (§4.6) |
| P2 predicate fault | `applies` faults | procedure not enabled | as P1 |
| P3 nondeterminism at re-execution | request hash mismatch during REEXECUTE | token `unknown` (L/H rule) | counted as fault; no pause |
| P4 sandbox unavailable | container cannot start / restart / clean up | stop (row 3 analogue) | unit pause, owner decision |
| P5 second/repair call failed | undelivered or truncated follow-up | final = first reply (`fallback`) | deciding receipt = first; usage of both charged |
| P6 reasoning mismatch | receipt has `reasoning_tokens > 0` or non-empty `reasoning_content` | receipt `error_type = "thinking_mismatch"` (existing undelivered class, outcomes.py:66-67) -> resend <= 2, then infrastructure unknown | `reasoning_mismatch` subtype recorded |
| P7 over nominal cap | `completion_tokens > M` and `<= B` | normal scoring; flag `over_nominal_cap` | counted per arm; not a halt (A4) |

Faults therefore never become infrastructure unknowns (A6); only P4/P6 and the frozen rows do.

### 1.11 Concurrency and ledger wiring

- Threads: `workers = 16` per unit (v3 value [SB F39]); one Endpoint per unit attempt per role (halt generation,
  calls.py:145 [CI F7]).
- File-lock slot pools (calls.Slots): `deepseek-v4.1-flash-1017` 8 (probe delivered 8/8, docs/project-status.md:14) under
  the machine-wide root `/data/execskill-slots/`; `glm-5.3` 10; `spreadsheet-native` 3; `alfworld-episode` 6 (each episode
  slot includes its sandbox worker); `execskill-sandbox` 16 (= workers, so a cell worker held across its model calls never
  throttles throughput); `execskill-examiner` 2 (generator jobs). Pool names pass the
  `Slots` name check (calls.py:41-42 [SB 3.3]).
- CPU arithmetic on 7 CPUs (measured [LO F1]): 6 ALFWorld env processes (mostly waiting) + 6 x 0.5 CPU episode sandboxes +
  3 x 1 CPU native + active QA/Sheet sandboxes (bursts) + recalc 1 = up to ~9-10 CPU-equivalents at peak (estimate):
  oversubscribed only in bursts. Memory limits are bounded by scheduling: SpreadsheetBench and ALFWorld units never run
  concurrently, including in test reads, which run in two waves (wave 1: SearchQA, OfficeQA, LiveMath, SpreadsheetBench
  children side by side; wave 2: ALFWorld). Arms stay interleaved WITHIN each bench, which is what the contrasts need.
- Ledger: one `budget.Budget` at `<root>/shared/ledger` (imported unchanged). Scopes (new helper `execskill/budgets.py`,
  keeping `rooted`, budget.py:59-64 [CI F11]):
  - solver (deepseek root): `deepseek`, `deepseek:xs`, `deepseek:xs:<bench>:<k>:<kind>` with kind in
    {`run`, `examiner`, `selftest`, `accept`, `test`, `smoke`};
  - GLM (overall root): `overall`, `role:engineer`, `role:examiner`, `step:xs:<bench>:<k>:glm`.
  - The examiner's SOLVER usage (saturation band, shortcut probes, self-test on generated sets) is charged to
    `...:examiner`/`...:selftest`, never to `...:accept`, so examiner probing cannot starve acceptance.
- Reservation: Endpoint for the elucid client is constructed with `max_tokens = B` (the registered completion bound, §3.1),
  while the client sends the nominal `M` in the body. Reservation = 4 x (request bytes + 512 + B) (ledger.py:26-36) and the
  breach check compares completion against B (ledger.py:67): the ledger module is unchanged (A4).

### 1.12 Run-directory layout (pilot root shown)

```
/data/execskill-20261021-pilot/
  shared/consent.json                       owner consent (new wording, §7.5)
  shared/ledger/{.lock,events.jsonl,state.json}
  shared/test/<bench>.json (+ .lock)        write-once test-panel registry (copied evaluation._registry)
  shared/consumption-mirror/<bench>.jsonl audit copy; the authoritative registry is /data/execskill-history (§2.3)
  shared/host_only/diagnostics/*.log, host_only/specs/*.json
  packages/<sha256>.json                    content-addressed, write-once
  <chain>/chain.json, .runner.lock, chain-complete.json | chain-terminated.json
  <chain>/s<k>-<bench>/t<j>/
     run/        unit: attempt-N/{cells/, artifacts/, trajectories/, enable_log.jsonl, status.json, recovery.json}
     diagnose/   unit: detectors/<id>/{source.py, validation.json}, roles.json, failure_counts.json
     generate/   unit: generators/<id>/{source.py, items.jsonl, gates.json}, roles.json
     engineer/   unit: candidates/<n>/{package.json, static.json, leakage.json, zero_crash.json, replay.json}, roles.json
     selftest/   unit: cells/, sieve.json
     accept-b<m>/ unit per block: cells/, trajectories/, enable_log.jsonl
     decision/   unit (zero calls): decision.json, validity.json (generator strikes)
     freeze/     unit (zero calls): package.json pointer, labels pending
  <chain>/final/evaluation/<bench>/          multi-arm test unit (sealed store; hashes only)
```

### 1.13 Manifest pins (`fivebench-execskill-v1-manifest`)

`FIELDS = {version, root, history_root, slot_root, data (pins of every supply file and items file), sheet_qualification
(imported v3 record + re-verification), cards (5 sha256), contracts (5 strings + sha256), runtime (per bench, incl. the
images), sandbox {image_id, worker_sha256, policy_sha256, limits}, clients {solver: {backend "elucid", model, url_host,
env_path, proxy, reasoning_effort, M_by_bench, B, read_timeout_by_bench, slots, response_model_ids}, roles: {model glm-5.3,
max_tokens 16384, read_timeout 900, reasoning low}}, seeds, sizes (§2), thresholds (§4-§6), caps (§8), placebo corpus
sha256, fixture sha256s, code (pin_code over skillopt/ and scripts/), loaded_code (skillopt/execskill/*.py, the imported
coevo5 and continual_eval modules, scripts/run_execskill.py, scripts/weak_solver_probe.py), environment (python 3.11.16,
openpyxl 3.1.5, docker 26.1.3, image digests native 0a0a5dcb..., recalc f7f6f598...), provenance, record_hash}`.
`verify_code` before every unit (copied `_verified` pattern, chain.py [CI §4]); a mismatch writes
`chain-terminated.json`.

### 1.14 Pauses and recovery

- Nothing resumes automatically (v3 §13.4). Owner chooses: terminate, or authorize the paused unit to be redone in a new
  `attempt-N` (recovery.json `{"by":"owner","date","decision"}`).
- A redone unit re-runs ALL its cells (no splicing of cells across attempts: splicing breaks co-scheduling, and serving
  regimes drift by up to 22-24 points between windows, measured D11 [FP F45]). To bound the waste, acceptance on
  ALFWorld runs in 4 blocks (`accept-b1..b4`, ~34 games each, all arms interleaved inside a block); a pause redoes one block.
  The decision pools blocks (stratified bootstrap, §5).
- Items of a paused attempt stay consumed by THAT unit; the redo uses the same items (same decision, same batch); paused
  partial results are never shown to any role and never read before the redo completes.
- Cleanup-unconfirmed pauses additionally require: no `execskill-sbx-*`, `continual-eval-*` or
  `skillopt-sheet-recalc-*` container in any state, and no route-B ALFWorld worker process (the leftover D3/D14 workers are
  excluded by command-line match and listed separately [LO F39]).

### 1.15 CLI (`scripts/run_execskill.py`, subcommands)

`probe` (endpoint, §9 S1) · `sandbox-selftest` (zero calls, §9 S0) · `import-texts` · `import-sheet-qualification`
(zero-call re-verification of the pinned v3 hashes) · `make-items --bench alfworld|searchqa` (supply files) ·
`exclude-tests` (runs with test access; writes counts and the exclusion hash only) · `smoke-make` / `smoke` /
`smoke-summary` · `make-manifest` · `consent` · `run --manifest M --chain C` · `step-unit` / `evaluate-unit` (children) ·
`replay --package P --trajectories DIR` (zero tokens) · `show-package` · `monitor` (counts, never scores) · `recover` ·
`terminate` · `resume-ledger` · `report`. Every run script does `unset OPENAI_API_KEY OPENAI_BASE_URL`,
`export PYTHONDONTWRITEBYTECODE=1`, runs from the snapshot with `python -B` [LO §7, FP F34].

## 2. Data (pools, fresh batches, seeds, test isolation)

### 2.1 Freshness definition (A1, registered rule)

"Fresh" = never consumed in route B's own history (smoke, pilot, full run), as recorded by the write-once consumption
registry (§2.3). Prior use by the v1 baselines, v3 chains, cal-1 and the 10/20-21 feasibility studies is DISCLOSED in the
registration and in every report table ("method-side prior use: yes, by ..."), not hidden. Under the absolute definition
every pool item is used (0 fresh everywhere [DP §5]).

### 2.2 Supplies, slices and sizes (pilot and full run)

One seeded order per bench: `order_b = data.ranked(supply_b, seed=20261021, tag="execskill-v1:order:" + b)`
(data.py:173-176, imported unchanged; pure, input-order independent [DP §4]). The order is cut into CONSECUTIVE slices in
the fixed sequence below; each slice is consumed once. Independent tags are forbidden for slicing (they overlap by chance:
29/18/60 items [DP F6]).

| Bench | Supply (route-B fresh) | Slices per step (items x runs) | Steps possible | Acceptance MDE (1-sided 5%, power .8) | Source of MDE |
|---|---|---|---|---|---|
| SpreadsheetBench | 91 qualified of the 120-item pool (v3 training qualification [CI F33]) | run 45 x 2 ; accept 46 x 2 | 1 | 12.2 pts (measured design value: D1 smallest certifiable effect at 46 x 2 [FP F40]); ~13-15 with the placebo intersection (estimate, x1.1-1.2) | D1 |
| OfficeQA | 74 (pool; no other training supply: upstream 246 = 50+24+172 [DP §5]) | run 37 x 2 ; accept 37 x 4 | 1 | 10.3 pts (D1 at 37 x 4 [FP F40]); ~11-12.5 with the intersection (estimate) | D1 |
| LiveMath | 283 (pool) ; owner option: eval blocks e03-e08, 150 (D2) | run 83 x 1 ; accept 200 x 1 | 1 (2 with e03-e08: 2 x (run 40, accept ~176)) | 7.9-8.7 pts at n=200 (estimate: DP scaling `MDE_test x sqrt(n_test/n)`, 1 run, two-sided; x0.89 one-sided) | DP §5 |
| SearchQA | 600 pool + never-sampled HF validation rows (11,380 before exclusion [DP §5]) | run 200 x 1 ; accept 1,000 x 1 | 3 (supply ~11,900) | 2.5-3.2 pts at n=1,000 (estimate, DP scaling) | DP §5 |
| ALFWorld | 3,514 unused train games (+ the 57-game pool, used only as step-1 run slice) | run 57 x 1 (step 1: the pool) / 57 new games (later steps) ; accept 134 new games x 1 in 4 blocks | 3 (supply 3,514) | 9.0-10.0 pts at 134 (estimate, DP scaling) | DP §5 |

Stated plainly (A1): OfficeQA and SpreadsheetBench can certify only effects of about 10-12 points or more; LiveMath about
8-9; ALFWorld about 9-10; SearchQA about 3. A smaller true effect will usually be rejected on these benches. Reports must say
"not detectable at this size", never "no effect".

Supply construction (zero model calls):
- **SearchQA**: re-run the deterministic order of `scripts/make_searchqa_fresh_sample.build` (sorted keys +
  `random.Random("searchqa-fresh-20261012").shuffle`, lines 61-62 [FP F57]) with a larger count; extending `--count` keeps
  the first 4,000 unchanged [DP F15], so rows at positions >= 4,001 are disjoint from blocks A-D BY CONSTRUCTION, and
  blocks C/D never have to be opened. Additionally exclude, by id and by normalized question
  (`re.sub(r"\W+"," ", q.lower()).strip()`): the 600 pool items, the native train/val/test ids (the script already does),
  and the 1,000-item reserve (sealed: its ids are read by `exclude-tests` under test access; the command prints counts and
  an exclusion hash only). Output `supply/searchqa.jsonl` under `/data/execskill-history/supply/`, pinned by sha256.
- **ALFWorld**: items file `{id: "xs-alf:" + sha256(rel_gamefile)[:12], gamefile (relative to ALFWORLD_DATA), task_type,
  initial_observation (public; filled by one zero-call reset per game, only for games of the next slice before its
  pre-routing, not for the whole supply: a reset of all 3,514 games would take hours, estimate)}`
  for every `json_2.1.1/train/**/game.tw-pddl` not in the 57-game pool (3,514 expected [DP F13]); task type from the
  directory name prefix (6 types). `exclude-tests` (test access) verifies that the test panel's game paths are all under
  `valid_unseen` and that none is in the supply (counts only); if the test split is NOT valid_unseen, the launch stops
  (verify-with-code requirement, A1). Order: stratified — within each task type ranked by the seeded hash, then interleaved
  round-robin over types, so every consecutive slice is balanced by type. Optional zero-call qualification: each selected
  game loads and resets within 60 s (no expert run: that would read the expert plan).
- **SpreadsheetBench**: the v3 training qualification record `/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json`
  is imported through `qualify.load` copied with `IMPORTABLE_VERSIONS = ("fivebench-coevolution-v3-sheet-qualification",)`
  and a zero-call re-verification that the pinned engine qualification hashes and image digests match (A14, owner D11).
- **OfficeQA, LiveMath**: `data.pool` (imported unchanged; its `_refuse_tests` firewall applies [CI F29]).

### 2.3 Consumption registry (write-once, exactly-once)

- `/data/execskill-history/consumption/<bench>.jsonl` (+ `.lock`, fcntl). Record:
  `{version: "fivebench-execskill-v1-consumption", bench, item_id, item_hash, slice: "<step>:<purpose>", purpose in
  {smoke, run, accept, withhold, detector_holdout}, unit, run_root, ts, record_hash}`.
- Written and fsynced BEFORE the first cell of the unit is dispatched. A reader refuses (raises `ConsumptionConflict`,
  unit pause) when an item is already registered for a different `(run_root, unit, purpose)`. A redo attempt of the same
  unit re-uses its own registrations (same decision, §1.14).
- Withholding twins and detector hold-outs use items of the SAME slice (no extra supply); they are tagged, not consumed
  twice.
- A slice that is never dispatched (e.g. no candidate survived the sieve) is recorded `skipped` and is available to the next
  decision on the same bench in the same chain; it is never returned to the pool after any cell ran on it.
- Pilot-consumed items are consumed for the full run as well (A1 history spans run roots); owner decision D9 can only make
  the pilot the PREFIX of the full run, never re-use its items for a new decision.

### 2.4 Seeds (registered)

| Purpose | Seed / tag |
|---|---|
| Bench order of supply | `seed 20261021`, tag `execskill-v1:order:<bench>` |
| Cell dispatch order (interleaving) | `_order(jobs, "execskill-v1:round:" + unit)` (copy of step._order, step.py:79-80) |
| Detector write/hold split of run trajectories | tag `execskill-v1:detsplit:<unit>` (50/50 by item) |
| Withholding twin selection | tag `execskill-v1:withhold:<unit>:<procedure_id>` |
| Generator randomness | seed passed as an argument `seed = int(sha256("execskill-v1:gen:<generator_id>:<step>")[:8], 16)`; generators may use only this seed (no global RNG: `random` is forbidden; numpy `default_rng(seed)` allowed) |
| Bootstrap | `seed 20261021`, 10,000 resamples (stats.bootstrap, stats.py:56) |
| ALFWorld env | seed 42 (frozen runtime) |

### 2.5 Test sets (read only by the evaluation step)

- Only the copied evaluation unit creates `data.TestAccess(unit)` (evaluation.py:231; data.py:232-239) and only with
  `shared/consent.json` whose wording names route B, the arms and the twin control (§7.5) [CI F23].
- Sizes (frozen v3 panels): SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 279 qualified (test-side
  qualification re-run zero-call under the new root or imported, D11), ALFWorld 134.
- Test-side cells store request hashes only; no role, detector, generator, replay set or report table sees a test item's
  text, trajectory or per-item result before `unseal` after chain completion (copied `unseal`, re-keyed by
  `(arm, task_id, run)` instead of task_id only [CI F26]).
- Generators read only the training pool of their own bench (OfficeQA train and test share 40 bulletins
  (current-workflow.md:56 [MAP 3.1]); perturbing a bulletin page that also backs a test item is forbidden: the generator
  receives only pages of training items, filtered by the copied `_refuse_tests`).

## 3. Roles (inputs, outputs, schemas, ceilings, fallbacks)

### 3.1 Solver: deepseek-v4.1-flash-1017 through the "elucid" client (A4)

`skillopt/execskill/client.py`:

```python
class ElucidClient(weak_solver_probe.Client):      # subclass; does NOT call super().__init__ (MODELS check, :232-233)
    def __init__(self, env_path, *, proxy, max_tokens, read_timeout, transport=None):
        env = weak_solver_probe._read_env(env_path)          # names ELUCID_CHAT_URL, ELUCID_API_KEY, ELUCID_MODEL [LO F17]
        self.url = weak_solver_probe._validated_url(env["ELUCID_CHAT_URL"], <registered host>, "/v1/chat/completions", ...)
        self._key = env["ELUCID_API_KEY"]; assert env["ELUCID_MODEL"] == "deepseek-v4.1-flash-1017"
        self.backend = "elucid"; self.model = "deepseek-v4.1-flash-1017"; self.max_tokens = max_tokens  # nominal M
        self.thinking = None; self.effort = "none"          # body sends reasoning_effort "none", no thinking field
        self.response_model_ids = frozenset(<echo set fixed by smoke S1>)
        assert proxy == weak_solver_probe.GATEWAY          # approved PJLAB gateway; trust_env=False
        options = {"transport": transport} if transport is not None else {"proxy": proxy}   # as parent :254
        self.http = httpx.Client(timeout=httpx.Timeout(connect=20, read=read_timeout, write=30, pool=30),
                                 trust_env=False, follow_redirects=False, **options)
        self._transport_errors = ...                         # as parent
    def _receipt(self, status, data, attempts, started):
        r = super()._receipt(status, data, attempts, started)
        rt = usage.completion_tokens_details.reasoning_tokens (missing -> None); rc = len(message.reasoning_content or "")
        r["reasoning_tokens"] = rt; r["reasoning_chars"] = rc
        # parent marks thinking_mismatch only when thinking == "disabled" (weak_solver_probe.py:295-296); checked first here
        if (rt or 0) > 0 or rc > 0: r.update(ok=False, error_type="thinking_mismatch", subtype="reasoning_mismatch")
        r["over_nominal_cap"] = usage.completion_tokens > self.max_tokens
        return r
```

Registered settings (owner D6 can change them before launch):

| Setting | Value | Justification |
|---|---|---|
| reasoning | `reasoning_effort: "none"`, verified per receipt (row P6) | 0 reasoning tokens in probe 2 (docs/project-status.md:14, measured); comparable with v3's no-reasoning deepseek; cheaper |
| nominal `max_tokens` M | QA and SpreadsheetBench 8,192; ALFWorld 1,024 per step | estimate: v3 deepseek-v4-flash QA cells averaged 3.9-7.9k tokens including prompts (measured [FP F32]); truncation at 32,768 was rare in cal-1 (8 of 8,800 cells, measured [FP F45]); an ALFWorld step needs one action |
| ledger completion bound B | 2 x M (16,384 / 2,048), CONDITIONAL on smoke S1-b showing enforcement | the gateway's non-enforcement evidence is confounded (see contradiction note below) |
| read timeout | QA/Sheet 600 s; ALFWorld 180 s | v3's 2,400 s turned one stall into a 51-minute smoke unit (measured [LO F37]); 8,192 tokens at an assumed >= 30 tok/s is <= 273 s (estimate); must be >= 3 x the p99 latency of complete replies observed in S1/S2, else revised before launch |
| client attempts | <= 4 (inherited BACKOFF, weak_solver_probe.py:91-93) | ledger requires 1-4 attempts (ledger.py:59-60) |
| resends | <= 2 after 300 s (Recorder, calls.py:268-275) | unchanged |
| slots | 8 (machine-wide pool) | 8/8 concurrent delivered (measured, probe 2); raise only by a recorded deviation after S2's 429 share < 1% |
| proxy | `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128` explicit | approved credential-free gateway (AGENTS.md); bound into manifest + identity |
| temperature | 0 | as v3 |

**Contradiction / refinement note (flagged, not silently resolved).** A4 states that the gateway does not enforce
`max_tokens` because `max_tokens: 2` returned 21 tokens with finish "stop". The probe script
(scratchpad execskill/probe/probe_elucid2.py, the `max_tokens_2` line) sent that request WITHOUT `reasoning_effort`, i.e.
with reasoning ON by default. The 21 completion tokens may therefore be reasoning tokens counted outside the visible cap, and
enforcement with reasoning OFF is untested. I keep A4's conservative design (B = 2M, flag above M) but make smoke S1-b a
launch blocker that measures enforcement with `reasoning_effort: "none"`: if any probe returns `completion_tokens > B` or
does not finish within the read timeout, the endpoint is not launched and the owner decides (raise B to a measured ceiling,
or accept the global-halt risk).

Truncation handling: `finish_reason in {"length","max_tokens"}` -> truncated (frozen). Additionally the judge flags
`suspected_silent_truncation` = `completion_tokens >= M - 16` and an unclosed `<answer>`/`<action>`/code fence; such replies
fail on format under the completion-aware metric anyway, so the flag is descriptive.

### 3.2 Engineer (GLM-5.3; writes and revises procedures)

- Settings: v3 role settings (temperature 0, reasoning low, `max_tokens` 16,384, read timeout 900 s, input budget 220,000
  bytes via `roles.fit`) [CM F1-F5]. Endpoint scopes `("overall", "role:engineer", "step:xs:<bench>:<k>:glm")`.
- Call: `Roles.plain(...)` + `execskill/roles_code.parse_engineer` (the JSON-only `Roles.ask` contract cannot carry code
  robustly: the v3 analyst needed a second attempt in 3 of 10 stages and 21 of 49 v3 proposals died of small format faults
  (measured [CM §5.2, FP F47])).
- Reply format: exactly one ```json fence (the manifest) followed by one ```python fence per new or revised procedure whose
  first line is `# file: <procedure_id>.py`. Manifest:
  `{"changes": [{"op": "add"|"revise"|"remove", "id", "revises"?, "description", "hooks", "max_note_chars",
  "requests_second_call", "state_schema_bytes", "claimed_failures": [trajectory ids], "replay_tests": [...]}],
  "rationale": "<= 1,500 chars"}`. <= 3 changes per step.
- Input payload: bench; its task card and contract; the fixed hook API document (hooks, view schema per bench, policy,
  caps); the current package with sources; detector counts on the run slice; up to 12 failed and 6 passed run-slice
  trajectories (seeded selection within detector-flagged groups; ALFWorld steps compressed to action/how/post_observation
  [:300]); for failed QA/Sheet run items the reference answer (as v3's diagnosis role saw references [CM 2.11]); earlier
  rejection reasons of this step. NEVER: ALFWorld expert plans or game paths (owner D13), acceptance-slice anything, other
  benches' references, test anything.
- Attempts: <= 2 parse attempts per call (the second carries the parse/validation errors, <= 2,000 chars); <= 2 fix rounds
  after checks fail (§4.4) -> at most 6 calls per step.
- Fallback: no valid candidate -> `engineer_failure`; the step skips selftest and acceptance; the acceptance slice is
  recorded `skipped` (§2.3).
- Ceiling: 1.5M GLM tokens per step (estimate: 6 calls x (<= 60k input + <= 16k output) ~ 0.46M, 3x margin; the D3 tracker
  came from one call of 4,986 tokens, measured [FP F1]).

### 3.3 Examiner (GLM-5.3; detectors, generators, generation policy)

- Same role settings; scopes `("overall", "role:examiner", "step:xs:<bench>:<k>:glm")`; its SOLVER probes are charged to
  `deepseek:xs:<bench>:<k>:examiner`.
- `detector_write`: input = detector counts, uncovered failed trajectories of the WRITE half (public parts only: views,
  replies, actions, observations, enabled procedures; no reference, no verdict per trajectory beyond the pass/fail bit),
  the mechanical-category definitions. Output: <= 3 detectors, each `{"id","description","source"}` with
  `detect(trajectory_view) -> bool` (sandboxed, no reference at run time).
- `generator_write` (not for SearchQA): input = bench item schema, 3-5 public training items of the run slice as
  material, the truth-check contract; output <= 2 generators `{"id","description","source","params"}` with
  `generate(seed, material, params) -> [item]`, each item carrying the bench's frozen schema plus `truth` (OfficeQA:
  `formula` over table literals; LiveMath: `truth_expr` in a sympy-restricted grammar + options; SpreadsheetBench: input
  and reference workbooks with LITERAL answer values; ALFWorld: a selection filter over the supply's public initial views).
- `policy_revise`: one call per generator per step after the band measurement: new `params` only (no new code).
- Ceiling: 2.5M GLM tokens per step (estimate: <= 8 code calls x ~80k = 0.64M plus model-assisted LiveMath items at
  2,585 GLM tokens per valid item (measured, D6 [FP F32]) x <= 300 items = 0.78M).
- Fallback: invalid twice -> no new detectors/generators this step; persisting accepted ones continue.

### 3.4 Judge (fixed code)

`judge.py` (§1.6) over frozen scorers: SearchQA EM, OfficeQA strict EM, LiveMath single letter, SpreadsheetBench v7
recalculation, ALFWorld `won` within 50 steps [MAP 3.8]; generated items: program/simulator truth (§6.2). No model vote is
ever acceptance evidence.

### 3.5 Registrar (fixed code)

Consumption registry (§2.3), slicing and seeds (§2.4), interleaved rounds (copied `run_round`, arms = `{arm: (card,
package, withhold, placebo)}`), twins (§5.4), statistics (§5), ledger scopes (§1.11, §8), enable logs (§1.9), manifest pins
(§1.13), sealed decisions. The registrar never shows acceptance-slice per-item outcomes to any role; roles of later steps
receive at most the accept/reject bit and the aggregated difference (D1 rule "at most the accept/reject bit" [FP F41],
relaxed to the aggregate so the engineer can learn from a rejection; owner D10).

## 4. One step (bench b, step t, parent package S): the eight sub-steps

Each sub-step is one unit (`run_unit`, write-once `unit.json`); units run strictly in this order; the step identity hashes
`(chain, bench, t, parent package_sha256, manifest record_hash)`.

### 4.1 Run (unit `run`)
- Arm S only, on the step's run slice (§2.2 sizes), runs as registered. Every cell writes a trajectory (§1.9).
- Guard: infrastructure-unknown share > 1/10 -> pause (copied `step.guard`, step.py:150-157).
- Recorded: S's procedure fault rate on b (if > 2%, the step is flagged `parent_faulty` in the report; S is not changed
  except through an accepted `remove`).

### 4.2 Diagnose (unit `diagnose`; examiner evolution, half 1)
- Split the run trajectories 50/50 by item (tag `detsplit`): WRITE half and HOLD half.
- Fixed mechanical detectors (code, registered; no reference access): QA `no_answer_tag`, `multiple_answers`
  (tag count > 1 or list separators), `json_answer_untagged`, `truncated_or_suspected`; SpreadsheetBench `no_program`,
  `excel_formula_only`, `fence_glued`, `program_exception_on_public_input`; ALFWorld `step_budget_exhausted`,
  `revisit_empty_receptacle >= 3`, `nothing_happens_share > 0.2`, `inadmissible_share > 0.2`, `canonical_rescue_share`.
- Accepted model-written detectors from earlier steps of the same bench run on all trajectories.
- New detectors (<= 3 per step, one `detector_write` call, <= 2 attempts) are written from the WRITE half and accepted only
  on the HOLD half (A7): `n_fired >= 10` cells; precision = failed share among fired; base = failed share on the hold half;
  accept iff Wilson 90% lower bound of precision > base, AND precision / base >= 1.2, AND recall (fired-and-failed /
  failed) >= 0.10, AND zero faults and identical double-run results on all hold trajectories.
- Re-validation: an accepted detector whose precision on a later run slice of the same bench is not above base twice in a
  row is retired.
- Output `failure_counts.json`: per detector, fired / fired-and-failed / recall on all run trajectories. Categories are
  descriptions; only pass/fail is anchored. Model-written labels are never acceptance evidence.

### 4.3 Generate (unit `generate`; examiner evolution, half 2)
- Persisting generators of bench b plus <= 2 new ones (`generator_write`); SearchQA: none (detectors only; optional
  paraphrase probes are descriptive and never gate anything).
- Gate G1 (truth by program), per item, FIXED checker code: OfficeQA-type: the shell's exact kernel recomputes the
  item's `formula` over the perturbed table literals; the generator's stated answer must equal it exactly (Fraction), and
  the reference value must not appear verbatim in the question or context (D6 found 2 of 7 items stating the answer
  [FP F30]); every numeric literal of the formula must occur verbatim in the perturbed context; optional filter: an
  independent formula written from (context, question) by a copied `forward_check` call (GLM, examiner scope) must evaluate
  to the same value — a filter that can only drop items, never truth. LiveMath-type: a fixed truth checker inside the sandbox evaluates `truth_expr` with sympy at 50 digits; exactly
  one option equals it; integrals/series that stay unevaluated are dropped [SF G6]; key letters follow a balanced schedule
  (item index mod 5); the `STRONGER_OPTION` meta sentence is forbidden (A8: no training-label regularities; the D6 mirror
  form made the meta option always the key [FP F31]). SpreadsheetBench-type: literal answer values (formulas without caches
  are unscorable [SF R5]); the item must pass `qualify.qualify` (two v7 scorings of the reference as the answer, zero model
  calls [SF F24]). ALFWorld-type: a selection filter over the supply's public reset views; truth = simulator `won`.
- Gate G2 (not saturated): S's pass rate on the generator's items (<= 60 items per generator, 2 runs, charged to
  `...:examiner`) must lie in [0.20, 0.80]. Outside: one `policy_revise` call (new params), one re-measurement; still
  outside -> the generator is not used for screening this step (kept, recorded).
- Shortcut check (QA types): options-only (LiveMath) / question-only without context (OfficeQA) solver probe, 2 runs; an
  item is flagged if correct 2 of 2 (chance for 5 options = 4%); a generator whose flagged share > 0.25 is not used this
  step.
- ALFWorld "generated" sets are real unused games selected by the examiner's filter (<= 30 games), consumed with purpose
  `examiner` (supply is ample, §2.2).
- Templates the registrar provides (reuse, [FP R5]): D6's `gen_livemath2.build` drop reasons and item shape
  (dl:/data/feasibility/D6/v2/gen_livemath2.py) as the starting template for LiveMath-type generators, with the D6 critic's
  fix built in (the FIXED truth checker is always one side of any agreement [FP F27]); D3's tracker contract and replay
  verifier for ALFWorld procedures and fixtures [FP F10, R1-R3].
- G3 (predictive validity) is evaluated at 4.6/4.7 (§6.3).

### 4.4 Engineer (unit `engineer`; Skill-side evolution)
- One `engineer` call (§3.2), <= 3 changes. Fixed checks, in order, per change:
  C1 parse; C2 AST/import policy (§1.8); C3 caps (source <= 6,000 B, package <= 24 procedures and <= 64,000 B, notes,
  state); C4 leakage: `leakage.findings`/`mechanical` [CM 2.8] over the description, every string literal and every numeric
  literal (AST-extracted) against a Corpus of the run slice's references and answer values; a finding goes to
  `leakage.adjudicate` (1 GLM call, `role:engineer`); a veto drops the change; C5 sandbox load; C6 zero crash: every hook
  of the procedure on EVERY stored route-B run trajectory so far (this bench and earlier benches; ALFWorld state replayed
  from step 0), each call twice; any fault or mismatch fails; C7 replay tests all pass (§1.7); C8 format guard untouched:
  on every stored trajectory, the re-rendered requests with the change enabled have the parent's system-prompt sha256 and
  the reply channel is untouched (structural invariant asserted); C9 notes within declared caps on all trajectories.
- <= 2 fix rounds (the engineer receives check id, exception class, message <= 500 chars, trajectory id); still failing
  changes are dropped. S' = S + surviving changes; none -> `engineer_failure` (skip 4.5-4.6).
- Zero solver tokens; replay cost anchor: 2.8 s for 7,524 ALFWorld steps (measured, D3 [FP F14]).

### 4.5 Self-test (unit `selftest`; a sieve, never acceptance)
- Arms S', S on (a) bench b's G2/shortcut-eligible generated items (<= 120, 2 runs) and (b) each earlier bench's
  persisted eligible generated set (<= 60 items, 1 run), interleaved.
- Pass iff: Delta_b(S' - S) >= 0 on (a) (vacuous if no eligible set), AND Delta >= -0.05 on every set in (b), AND S'
  fault rate <= 2%. Fail -> one more engineer fix round within the <= 2 budget (it may see per-item generated outcomes:
  generated items are not scarce); still failing -> skip 4.6, slice recorded `skipped`.

### 4.6 Acceptance (units `accept-b<m>` + zero-call `decision`)
- Four arms S', S, C, P interleaved per block, on the acceptance slice (§2.2), plus withholding twins (§5.4). Decision rule
  §5.3. One decision per batch; the batch is never used again.

### 4.7 Freeze (zero-call unit `freeze`)
- Accepted: S' sealed as the new parent (`packages/<sha>.json`); each new procedure gets `origin = b`,
  `accepted_at`; labels "general"/"this bench only" are assigned LATER from twin evidence (§7.4) and never change routing.
- Rejected: S stays; S' archived; the next step's engineer receives the aggregate result (difference and CI, no per-item
  outcomes) and the fault summary.
- Generator strikes and credits updated (§6.3).

### 4.8 Test read (evaluation units)
- Pilot: once at the end of the pilot (A12), arms F, C, P (+ optional F_desc, owner D8) + twins (§7). Full run: owner D7.

### 4.9 Stage end
- A bench's stage ends after its registered number of steps, when its supply is exhausted, or when its step ceiling is
  reached (budget stop = pause, owner decides). The parent package then moves to the next bench in ORDER.

## 5. Acceptance statistics

### 5.1 Arms

| Arm | System prompt | Package | Notes / calls |
|---|---|---|---|
| S' candidate | base + contract + card(b) | S + changes | as produced |
| S parent | same bytes | S | as produced |
| C task card only | same bytes | empty (no sandbox started) | none; at the first step of the chain C == S, so C doubles as the same-text duplicate (noise floor), like cal-1's parent:B [FP F60] |
| P placebo | same bytes | S + placebo procedure P0 | see 5.2 |
| S'-p twins | same bytes | S' with procedure p withheld on that item | only when S' has >= 2 changes (with one change S'-p == S) |

### 5.2 Placebo procedure P0 (fixed registrar code, run in the sandbox like any procedure, for latency parity)
- Fires on exactly the items (ALFWorld: episodes) where any NEW or REVISED procedure of S' applies (router computes this
  before dispatch from the view; zero model calls).
- Note: for each request, P0 emits text drawn deterministically (by item hash) from the registered irrelevant-text corpus
  (`PLACEBOS_SCREEN` + `PLACEBOS_CONFIRM`, protocol.py:105-124 [CM 4.3]), cut to the SAME character length that S''s new
  procedures would emit on that request; the length is obtained by running S''s procedures in shadow mode (sandbox,
  deterministic, not shown to the model) on P's own trajectory.
- Calls: if any new procedure has `requests_second_call`, P0 makes one second call on EVERY fired QA item with the fixed
  text "Here is your previous reply. Give your final answer in the required format." and no computed values (controls the
  "second look" effect; P therefore makes at least as many second calls as S' — conservative). SpreadsheetBench: one repair
  call on fired items with "Check your program once more." and no run report. ALFWorld: never vetoes (the veto effect is not
  placebo-able; reported separately).
- Placebos are not inert: cal-1 placebos moved SearchQA by -9.8 to +3.6 points (measured [CM F47]), mostly through JSON
  scoring, which scorer v2 removes; D1's rule accepted a placebo (+0.036) on the empty scaffold [FP F37]. P is therefore an
  arm of the DECISION, not only a report.

### 5.3 Decision rule (one per batch; intersection-union test)
Per item i and arm a, the item score is the mean over runs of the v2 completion-aware token, with the L/H rule
(`stats.bounds`: unknown = fail for S', = pass for S and P [CM F38]). `d_i = S'_i - S_i`, `e_i = S'_i - P_i`. Bootstrap:
one-sided 95% percentile lower bound of the mean over items, 10,000 resamples, seed 20261021, stratified by block.

Accept S' iff ALL hold:
1. LB95(mean d) > 0;
2. LB95(mean e) > 0;
3. mean d >= 0.02 (D1 minimum [FP F41]);
4. S' procedure-fault cells <= 2% of S' cells (A6);
5. the sieve (4.5) passed.

Pause (not reject) if any arm's infrastructure-unknown share > 1/10 (guard). Secondary, reported, not gating: exact sign
test on discordant items for d and e; mean(S' - C) with CI; format flags and the v2-minus-official gap per arm; the
`over_nominal_cap` share per arm; ALFWorld canonical-rescue share per arm.

Multiplicity: requiring both (1) and (2) is an intersection-union test, so the false-accept rate is <= 5% without
correction. Across steps there is one decision per fresh batch; no cross-step correction; the report states the number of
decisions and the expected number of false accepts under the null (0.05 per decision).

### 5.4 Withholding twins in acceptance (A11)
- For each new/revised procedure p of an S' with >= 2 changes: among acceptance items where p is enabled in S' (known
  before dispatch), select f_acc = 0.5 by seeded hash (`withhold:<unit>:<p>`); add `S'-p` cells (same runs), interleaved in
  the same block. Effect of p = mean(S' - (S'-p)) on those items, with bootstrap CI: causal for "p on items where it fires",
  because withholding is randomized among fired items (FlowEvo's matched withholding [RW §2]).
- Descriptive (not gating). Cost: 0.5 x |fired items of p| x runs cells per p (§8).
- With exactly one change p, `S'-p` equals S on every item, so the causal per-procedure effect is `S' - S` restricted to
  p's fired items (no twins needed; reported as such). Removal-only candidates: P = S (condition 2 equals condition 1;
  recorded).
- Pre-routing: before dispatch the registrar routes every acceptance item for S' in the sandbox (zero model calls; ALFWorld
  routes on the `initial_observation` stored in the items file by `make-items`, one zero-call reset per game). Fired sets
  for P0 and the twins come from this pass; each cell re-routes and must reproduce the same RouteLog (else fault
  `nondeterministic`).

### 5.5 MDE (registered at the sizes of §2.2)
SpreadsheetBench 12.2, OfficeQA 10.3 (D1 measured design values [FP F40]); LiveMath 7.9-8.7, SearchQA 2.5-3.2, ALFWorld
9.0-10.0 (estimates from DP scaling [DP §5]); the intersection with the placebo contrast raises these by about x1.1-1.2
(estimate, both contrasts must clear); serving drift can double or triple discordance between windows [DP §5], which
interleaving controls for the contrast but not for the variance. The report gives the MDE next to every decision.

### 5.6 What the decision does NOT use
Generated items (sieve only), other benches' training items, any test item, model votes, enable rates. No role sees
per-item acceptance outcomes.

## 6. Examiner evolution

### 6.1 Detectors (validation rule restated)
Accepted iff on held-out trajectories not used to write it: n_fired >= 10, Wilson-90% LB(precision) > base failure rate,
lift >= 1.2, recall >= 0.10, zero faults, deterministic (4.2). Their use: grouping failures for the engineer, selecting
trajectories, and targeting generator parameters. Their record per step is the examiner-side measurement (precision,
recall, lift with intervals). E1 found model-written reply checks reached balanced accuracy 0.47-0.55 on held-out items and
"only form checks transfer" (measured [FP F49]); a likely outcome is that only mechanical and form detectors pass.

### 6.2 Generators: three gates and the shortcut check
G1 truth by program/simulator (fixed checkers, 4.3); G2 saturation band [0.20, 0.80] on S with one policy revision;
shortcut check (flagged share <= 0.25); G3 predictive validity (6.3). A generator may use only the item's own content and
program/simulator truth (A8): balanced keys, no meta-option regularity, references never in the question.

### 6.3 Predictive validity (the examiner's primary metric)
- At every acceptance on bench b, for each eligible generator g of b: `Delta_gen = S' - S` on g's items (from 4.5),
  `Delta_real = mean d` (5.3). If |Delta_real| >= m_b with m_b = 0.5 x MDE_b (SpreadsheetBench 0.061, OfficeQA 0.052,
  LiveMath 0.042, SearchQA 0.015, ALFWorld 0.048): agreement iff `Delta_gen x Delta_real > 0` -> credit; otherwise strike
  (a saturated Delta_gen = 0 is a strike). |Delta_real| < m_b -> no information.
- Two consecutive strikes retire g (A8). Benches with one step (OfficeQA, SpreadsheetBench, LiveMath by default) can give
  at most one check per generator: one strike there marks g `unvalidated`, it cannot retire it; the report says so.
- Selection limit (stated plainly): because the sieve lets only candidates with Delta_gen >= 0 reach acceptance, G3 can
  only catch generators that PASS harmful candidates; it cannot see generators that BLOCK good ones. Owner option D12: on
  ample benches (SearchQA, ALFWorld), run acceptance on one sieve-rejected candidate per stage as a validity audit (costs one
  acceptance batch).
- E1's precedent: +13 points on generated OfficeQA-style items vs 0 on real items (measured [FP F50]); E9's generated panel
  was saturated (0.891) and missed a real -9.5 harm [FP F52]. These are exactly what G2/G3 are built to expose.

### 6.4 What "examiner accepted" means
- A detector is "accepted" when it passes 6.1; "retired" after two failed re-validations.
- A generator is "validated" when it has >= 1 credit and no strike, "unvalidated" when it has no informative check or one
  strike on a one-step bench, "retired" after two consecutive strikes.
- An examiner-side claim in any report must quote these counts and the underlying precision/recall and Delta pairs. If no
  generator is ever validated, the report says "the examiner side evolved detectors only; generator validity not
  established" (design-v0's own risk) — never "the examiner improved".

## 7. Transfer and test readout

### 7.1 Multi-arm test unit (new; v3 evaluation ran one arm per unit [CI F24])
- One unit per bench, all arms and twins in one seeded interleaved order; five bench children side by side (copied
  chain/child pattern with sealed stdout [CI §4]). Cell key `(unit, arm, task_id, run)`; `unseal` keyed the same way.
- Arms: F (final package), C (task card only), P (placebo: P0 firing where any procedure of F applies, length-matched notes,
  matched extra calls), optional F_desc (owner D8: the card plus the accepted procedures' DESCRIPTIONS as plain guidance text,
  no code executed: the direct code-versus-text contrast of Break It Down [RW §2]); twins `F-p`.
- Reuse of an earlier evaluation only if `(package_sha256, card sha256s, contract sha256s, shell/router/judge/sandbox code
  hashes, client config, runtime)` are all identical (v3 reused on the Skill-text digest alone [CI G5]).

### 7.2 Enable logs (descriptive)
Per procedure x bench: applies rate, fault rate, enabled cells, mean note length, extra-call rate; per bench the share of
items with >= 1 enabled procedure. Enable logs alone never support a transfer claim (correlational).

### 7.3 Random withholding control in test reads (A11; causal per-procedure effects)
- For procedure p and bench b with fired set F_pb (known before dispatch from routing), twins on
  `n_pb = min(|F_pb|, 100, max(20, ceil(0.25 x |F_pb|)))` items selected by seeded hash (`withhold:<unit>:<p>`); arm `F-p`
  runs those items in the same interleaved order.
- Effect `tau_pb = mean(F - (F-p))` on the twin items with 95% bootstrap CI. Precision: at 100 twins and discordance
  0.08-0.21 [DP §5 implied pi], the two-sided MDE is about 2.8 x sqrt(pi/n) = 8-13 points; at 20 twins 18-29 points
  (estimates). Per-procedure transfer is therefore coarse; it is reported, not tested for significance across procedures.
- Interactions: withholding p keeps every other enabled procedure; `tau_pb` is the effect of p given the rest of F.

### 7.4 Labels (reporting only; never change routing)
- "general": fires on >= 2 benches; on at least one non-origin bench with >= 20 twins, `tau` point estimate > 0 and 95% LB >
  -Delta_NI.
- "this bench only": fires on < 5% of items of every non-origin bench, or every non-origin `tau` point estimate <= 0.
- "harmful elsewhere": some non-origin bench has 95% UB(tau) < 0.
- "unresolved": fewer than 20 twins on every non-origin bench.

### 7.5 Pre-registered readouts (fixed order; owner 10/17 style)
- Similarity table (owner 10/17, coevo5-registration-v6 §1.1): sim(SearchQA) = {OfficeQA}; sim(OfficeQA) = {SearchQA,
  LiveMath, SpreadsheetBench}; sim(LiveMath) = {OfficeQA}; sim(SpreadsheetBench) = {OfficeQA}; sim(ALFWorld) = {}.
- Per bench: F - C and F - P with 95% CIs (v2 completion-aware; official and lenient alongside).
- Origin benches (where procedures were accepted): in-domain gain, F - C.
- Similar benches of the origins: descriptive (F - C, per-procedure `tau`).
- Dissimilar benches (neither origin nor similar): pooled non-inferiority, item-weighted mean of F - C over those benches,
  one-sided 95% LB > -Delta_NI with Delta_NI = 0.05 (owner's "about 4-5 points"; D6's critic: 200 items x 2 runs support
  about 5 points, a 3-point margin needs ~550 x 2 [FP F32]). For the alternative pilot (origins SearchQA, ALFWorld) the
  dissimilar set is {LiveMath 125, SpreadsheetBench 279} = 404 items x 1 run: supports about 5-6 points (estimate).
- Code-form risk (pre-stated, required by [RW §6.6]): "Executable procedures may transfer worse than text guidance
  (Break It Down, arXiv 2608.20274), and acceptance gates may lift only in-domain scores (GRASP, arXiv 2605.29668). The
  readout reports every bench's F - C and every procedure's tau with CIs whatever their sign; near-zero or negative transfer
  is reported as such; with F_desc, F - F_desc is the direct code-versus-description contrast."
- Consent (new wording, `shared/consent.json`, `by == "owner"`): names the protocol and run root, the arms (F, C, P,
  [F_desc]), the twin rule, the five test sets and sizes, read once at the end of the pilot.

### 7.6 Positioning against the closest prior work [RW §2]
| | FlowEvo (arXiv 2607.21596) | CoEvoSkills (arXiv 2604.01687) | GRASP (arXiv 2605.29668) | Route B |
|---|---|---|---|---|
| Learned object | callable skills with preconditions | multi-file skill packages | bounded text skills | executable procedures with code predicates in a fixed shell |
| Admission | interface/preconditions, replay + held-out checks, banned imports | best snapshot by oracle bit | net gain on a training-split probe, parent re-run, regression budget | one-shot fresh batch, four interleaved arms incl. placebo and card-only, IUT |
| Verifier side | none | surrogate verifier co-evolves, in-sample | none | detectors (held-out precision/recall) + generators with program truth and a predictive-validity gate |
| Per-skill effect | matched withholding within one benchmark | none | none | randomized withholding twins, per procedure, ACROSS benchmarks |
| Transfer | none across benchmarks (empty bank per benchmark) | cross-model only | in-domain only | one cumulative package across five benchmarks |
Novelty claims are limited to: the examiner's predictive-validity gate; one-shot fresh-batch acceptance with placebo and
card-only arms; per-procedure cross-benchmark attribution with randomized withholding. Never "first executable skill
library" or "first co-evolving verifier".

## 8. Budgets (tokens; estimates unless marked measured)

### 8.1 Per-cell anchors
| Bench | Measured anchor | Route-B estimate, C arm | Package arms (S, S', P) |
|---|---|---|---|
| SearchQA | E-ds 1,236/cell; D1 fresh pilot 1,531/cell (measured [FP F32, F35]) | 1,700 (E-ds + card 1,846 chars at ~4 chars/token) | ~2,200 (notes; compute rarely fires) |
| OfficeQA | E-ds 4,690 (measured [FP F32]) | 5,420 | ~7,600 (x1.4: notes + compute round trip on ~40% of items) |
| LiveMath | E-ds 1,251 (measured) | 1,770 | ~2,300 |
| SpreadsheetBench | E-ds 2,010 (measured) | 2,740 | ~3,800 (notes + repair call on fired items) |
| ALFWorld (episode) | E-ds 28.5k, 807 prompt tokens/step; I-ds 105.7k (measured [FP F17]); D3 tracker arm 33.3k (measured [FP F2]) | 42k (807 + ~575 card tokens per step x ~30 steps) | ~50k (+ <= 375 note tokens per step) |
Assumptions: deepseek-v4-flash anchors carry over to deepseek-v4.1-flash-1017 with reasoning off (unverified; S2 measures
the new model's per-cell cost and every cap below is re-derived if S2's per-cell cost exceeds the estimate by > 50%).

### 8.2 Pilot envelopes
| Item | Default pilot SpreadsheetBench -> OfficeQA | Alternative pilot SearchQA -> ALFWorld (recommended, D1) |
|---|---|---|
| Step 1 (run / examiner / selftest / accept incl. twins) | Sheet: 0.25 / 0.66 / 1.6 / 1.5 = 4.0M | SearchQA: 0.34 / 0 / 0 / 8.8 = 9.1M |
| Step 2 | OfficeQA: 0.48 / 1.8 / 3.8 / 4.9 = 11.0M | ALFWorld: 2.4 / 1.3 / 2.8 / 32.2 = 38.7M |
| End-of-pilot test read (F, C, P + twins) | ~33M (route-B estimate; ALFWorld ~19M of it) ; ~57M with v3 I-ds anchors [MAP §4.10] | same |
| Solver total | ~48M (up to ~72M with v3 anchors) | ~81M (up to ~105M with v3 anchors) |
| GLM (engineer + examiner + leakage) | <= 8M at ceilings; likely 2-4M (v3 spent 7.8M for two five-stage chains, measured [CI F13]) | same |
| Wall time | ~1-2 days | ALFWorld acceptance 536 episodes / 6 slots x ~320 s (median under contention, measured [LO F36]) ~ 8 h (+ twins ~2 h); SearchQA acceptance 4,000 cells ~5-7 h at 8 slots (D1: 1.4 h per 1,200 cells at 12 slots, measured [FP F41]); test read ~6-8 h: ~2-3 days |
The alternative pilot can exceed the 100M cap if the v3 anchors hold; stop rule: the end-of-pilot test read starts only if
the deepseek remainder covers its estimate x 1.3; otherwise pause and owner decision.

### 8.3 Registered hard caps (ledger scopes; A13)
| Scope | Cap |
|---|---|
| `deepseek` (pilot root) | 100M |
| `overall` (GLM, pilot root) | 30M |
| `role:engineer` / `role:examiner` per step | 1.5M / 2.5M |
| per step, solver: run / examiner / selftest / accept | Sheet 0.5/1.5/3/3M; OfficeQA 1/3/6/8M; LiveMath 0.5/3/2/3M; SearchQA 1/0.5/0.5/14M; ALFWorld 4/3/5/50M |
| test read (one) | 60M |
| smoke (pre-launch ledger `/data/execskill-20261021-pre/ledger`) | solver 5M, GLM 2M |
| full run (later delta) | ~200-450M estimate (learning ~165M with 1/1/1/3/3 steps + 1 to 5 test reads); v3's 1.44B envelope does not apply |
Reservation per elucid call = 4 x (request bytes + 512 + B) (§1.11): with B = 16,384 and ~6 KB requests ~ 92k tokens per
QA call in flight, x 8 slots ~ 0.74M reserved at most; caps are therefore not blocked by reservations.
Who pays: GLM roles -> `overall` + `role:*` + step scope; examiner-triggered solver probes -> `deepseek:xs:<b>:<k>:examiner`;
self-test -> `...:selftest`; acceptance -> `...:accept`; test reads -> `deepseek:xs:test`.

## 9. Smoke-test specification (tiny real run on dl with the new gateway)

Run from the verified snapshot under `/data/execskill-20261021-pre/smoke/`, pre-launch ledger
`/data/execskill-20261021-pre/ledger` (caps: solver 5M, GLM 2M), sealed spec = smoke run id [CI 3.12]. Real items only from
the smoke slices: SearchQA 80 (head of the SearchQA order, purpose `smoke`), ALFWorld 4 unused games. NO real OfficeQA,
LiveMath or SpreadsheetBench item is used (their supply is 74 / 283 / 91); those benches use ENGINEERING FIXTURES:
OfficeQA 8, LiveMath 8, SpreadsheetBench 6 registrar-written items with program-computed truth, frozen by sha256 and
labelled `engineering_fixture`, never counted as evidence (AGENTS.md).

### S0 Zero-call checks (all must pass)
1. pytest on the snapshot: `tests/test_execskill_*.py tests/test_weak_solver_probe.py`, `-p no:cacheprovider`, exit 0.
2. Solver equivalence: empty package => identical `(system, user)` hashes and predictions to frozen `backends.solve` on
   fixtures of all five benches (scripted fake call).
3. Exception-class test: `BudgetStop`/`AssumptionBroken`/`LedgerFailure` inside a copied cell -> stop kinds budget /
   assumption / ledger.
4. Ledger wiring with fake receipts: completion in (M, B] -> `over_nominal_cap`, no halt; completion > B -> `AssumptionBroken`;
   reasoning tokens > 0 -> `thinking_mismatch` -> resend path.
5. Sandbox self-test: container command, load/call/ping; fault suite (exception, infinite loop -> timeout, 2 GiB
   allocation -> memory, NaN -> malformed, 40 kB note -> over_cap, `import socket` -> forbidden at load, nondeterministic
   `hash()` -> rejected by policy, set-order nondeterminism -> caught by the double run); worker kill mid-call -> one restart,
   same result; image absent -> `SandboxUnavailable`; cleanup confirmed.
6. Escape probe (§1.8): network unreachable, root and /runner read-only, uid 65534, environment = the recorded fixed list,
   no `*.env`/key/ledger/consent file visible, pids and memory limits bite.
7. Replay runner: D3's 228 v3 stage-5 training traces (dl:/data/feasibility/D3/r3/lt/traces.json, 805,018 B [FP F11]) are
   converted to the new trajectory format; the ported fixture tracker runs on all 7,524 steps with zero faults (D3 measured
   0 exceptions [FP F1]).
8. Supplies: SearchQA supply built (counts printed, no text), ALFWorld items file built (3,514 expected), both pinned.
9. Test exclusion (test access, ids/paths only, owner D3): ALFWorld test panel paths all under `valid_unseen` and disjoint
   from the supply; SearchQA supply disjoint from test, reserve, blocks A-D and pool. Counts and exclusion hash only.
10. SpreadsheetBench: v3 training qualification imported via the importable-version list and the pinned engine
    qualification hashes re-verified (zero calls); the 6 fixture workbooks pass `qualify.qualify` (two v7 scorings).
11. Consumption registry: a second registration of an item for another unit raises `ConsumptionConflict`.

### S1 Endpoint probe (`probe` subcommand; <= 40 calls; estimate <= 60k tokens)
a. 3 tiny calls with `reasoning_effort: "none"`: echoed model id(s) recorded -> `response_model_ids`; usage complete;
   `reasoning_tokens == 0`, no `reasoning_content`; prompt overhead `prompt_tokens - request_bytes` recorded (the PJLAB
   gateway added ~90 tokens once [SB K2]) and must be <= 512.
b. Enforcement (launch blocker, §3.1 note): 3 calls with M in {16, 64, 256} asking for a 3,000-word essay, reasoning off.
   Pass iff every `completion_tokens <= 2M` (then B = 2M is registered); record whether finish is `length`.
c. 1 call, M = 8,192, long-output prompt: tokens/s and wall time -> read-timeout check (>= 3 x p99 of S1+S2 complete replies).
d. 8 concurrent tiny calls: 8/8 delivered, latency spread.
e. 1 call WITHOUT `reasoning_effort` through the client: must be classified `reasoning_mismatch` (detection path works).
f. All through the explicit PJLAB gateway with `trust_env=False`; first real response confirmed before anything concurrent
   (AGENTS.md).

### S2 Solver smoke (estimate <= 3M tokens; 1 run)
- Items: SearchQA 20 real, ALFWorld 4 real, fixtures OfficeQA 8 / LiveMath 8 / SpreadsheetBench 6.
- Arms: C (card only); X (fixture package of registrar-written fixture procedures: `fx-note` before_call note; `fx-compute`
  after_reply compute requests; `fx-sheet` sheet_feedback with repair on exception; `fx-alf-tracker` = D3's tracker logic
  ported to the pure-function state API, with a revisit veto; `fx-crash` that crashes on a registered 1-in-5 subset of
  items); P (placebo of X); twin arm `X-fx-note` on 4 SearchQA items.
- Format check: C arm on the 20 real SearchQA items: required-format share >= 9/10 (smoke.format_check pattern [SF U3]);
  fixtures descriptive.
- Must be observed, else the smoke fails:
  1. every hook kind fired >= 1 time with its effect visible in the trajectory (note in the user JSON; second call carrying
     computed values; repair call; shown command list shortened by the veto; state updated every step);
  2. `fx-crash` faults logged as P1 exactly on the registered items, cells completed, no pause;
  3. every call's usage summed into its cell; reservations == settlements; no breach;
  4. RouteLog in every prediction, enable logs written, the twin cells paired with their X cells;
  5. offline re-render of 5 stored cells reproduces identical request hashes;
  6. 0 reasoning tokens on every receipt;
  7. per-cell cost per bench x arm, latency p50/p99, HTTP 429 share (< 1% to keep 8 slots);
  8. ALFWorld: 12 episodes complete, one sandbox worker per episode, all cleaned up; canonicaliser `how` shares per arm and
     the wrapper-form share of the new model (deepseek-v4-flash showed 29-65% non-plain actions [FP F20]);
  9. SpreadsheetBench: native slot never held during a model call (slot-lock trace); v7 scorer ran;
  10. after the run: no `execskill-sbx-*` container in any state, no route-B ALFWorld worker.

### S3 Role smoke (GLM, estimate <= 0.5M)
One `engineer` call on S2's SearchQA and ALFWorld trajectories -> checks C1-C9 run end to end (the result need not pass);
one `detector_write` + hold-half validation; one LiveMath-type `generator_write` -> G1 checker on >= 5 items; one leakage
adjudication on a fixture literal that collides.

### S4 Mini-step with a recovery drill (estimate <= 1.5M)
One full step (4.1-4.7) on SearchQA smoke items (run 20, accept 40 x 4 arms); if no engineer candidate survives, the
fixture package is used as S' (labelled fixture). A registered fault-injection flag raises a Pause after 50 acceptance cells:
`status.json` paused -> `recover` -> attempt-2 redoes the whole unit -> `unit.json` complete; the registry shows the same
items for both attempts; attempt-1 cells archived, unread by any role.

Pass = S0 all, S1 a-f (b fixes B), S2 1-10, S3 ran, S4 complete; `summary.json` status complete; `changed_since` empty
before `make-manifest`.

## 10. Risks and failure modes, each with its honest reporting rule

| # | Risk | Mitigation in this spec | Reporting rule |
|---|---|---|---|
| R1 | Code-form procedures transfer worse than text (Break It Down [RW §2]); gates lift in-domain only (GRASP) | per-procedure twins; optional F_desc arm (D8) | report every bench's F - C and every tau with CIs whatever the sign; "near zero" and "negative" are stated as results |
| R2 | Nothing is accepted: MDEs of 10-12 points on OfficeQA/SpreadsheetBench, ~9-10 ALFWorld, ~8-9 LiveMath | sizes registered; pilot option D1 | "no procedure was accepted at an MDE of X points" — never "no effect" or "the method fails" |
| R3 | Generators never pass G2/G3 (E1: +13 generated vs 0 real; E9 saturated [FP F50, F52]) | gates; strikes; selection limit stated (6.3) | "examiner evolved detectors only; generator validity not established" |
| R4 | Sandbox escape or leakage of private data to procedures | container boundary, whitelisted inputs, escape probe, scrubbed env, no reference in any procedure argument | any probe failure blocks launch; any later evidence of leakage voids the affected decisions (reported, rerun under a new version) |
| R5 | The ALFWorld canonicaliser, not the procedure, drives a gain (D3: 41% vs 13% rescued steps [FP F7]) | same canonicaliser in every arm | report the rescue share per arm; if S' - S in rescue share > 10 points, label the gain "interface-mediated" |
| R6 | Gateway ignores max_tokens -> completion > B -> global ledger halt | S1-b launch blocker; B = 2M; flag above M | every halt and every over-cap reply is listed with counts per arm |
| R7 | Serving-regime drift (terse share 5-96% per 15-min bin; +22-24 points between windows [FP F45]) | all arms interleaved per block; blocks stratified | report block-wise differences; a contrast whose sign flips across blocks is flagged |
| R8 | Placebos are not inert (cal-1 -9.8 to +3.6 [CM F47]) | P is a decision arm; scorer v2 | report S' - P and P - S both |
| R9 | "Learning" is transcription of a dictated spec (D3 critic [FP F8]) | the hook API document is generic and contains no procedure; the engineer sees failures, not designs | report each accepted procedure's lineage (engineer call hash, input digest) and the share of proposals that passed each check |
| R10 | Answers leak through code literals | leakage check on all literals; acceptance on fresh items | leakage findings and vetoes counted per step |
| R11 | In-sample hindsight (D14's 55/57 from walkthrough metadata [FP K3]) | engineer never sees expert plans (D13) | if D13 is changed, every ALFWorld procedure is labelled "built with expert-plan access" |
| R12 | Fail-open faults bias the candidate toward the parent (toward null) | 2% fault cap; faults counted | report fault rates per arm and per procedure; a decision made with faults > 1% is flagged |
| R13 | Nondeterministic procedures break replay and pairing | fork per call, double runs, determinism faults | count nondeterminism faults; any at acceptance time is listed |
| R14 | CPU contention on 7 CPUs -> timeouts, slow ALFWorld (p90 1,929 s [LO F36]) | separate pools, no Sheet/ALFWorld concurrency, measured in S2 | wall times and timeout counts reported; timeouts of procedures are faults, of model calls undelivered |
| R15 | Identity/pinning traps (adding files to continual_eval; editing pinned files; .pyc in snapshots [SB F42, FP F34]) | new package outside continual_eval; `-B`; verify_code before every unit | any pin mismatch terminates the chain and is reported |
| R16 | Leftover D3/D14 workers make "no leftover worker" checks ambiguous [LO F39] | route-B workers identified by command line | listed separately in every cleanup confirmation |
| R17 | The pilot burns the only OfficeQA/SpreadsheetBench supply | owner D1 (recommendation: SearchQA -> ALFWorld) | items consumed per bench and remaining supply in every report |
| R18 | Per-procedure attribution is coarse (MDE 8-13 points at 100 twins, 18-29 at 20) | registered sizes | taus reported with CIs; no ranking of procedures by point estimate |
| R19 | The new model behaves differently (wrapper actions, terse JSON replies) | S2 measures; scorer v2 counts JSON answers | format flags per arm; v2 - official gap per arm |
| R20 | Predictive validity is one-sided under the sieve | stated in 6.3; optional audit D12 | "G3 cannot detect generators that block good candidates" printed under every validity table |
| R21 | Multi-call cells misclassified (rows 4-5 read the last receipt [SB G6]) | deciding-receipt rule (1.5.2) | fallback counts per arm |
| R22 | Prior use of every pool item by v1/v3/older learners | A1 disclosure | each table carries "method-side prior use" per bench |

## 11. Owner decisions (负责人需要决定的事；每项给默认值和我的建议)

1. **D1 试点顺序。** 默认：负责人认可的顺序的前两个 bench，SpreadsheetBench → OfficeQA（约 4,800 万 token，最多约 7,200 万；
   两个 bench 只认得出 10 到 12 分以上的效果）。我的建议：改成 **SearchQA → ALFWorld**（约 8,100 万，最多约 1.05 亿）。
   理由：试点最可能暴露工程问题，而 OfficeQA（74 题）和 SpreadsheetBench（91 题）的题在试点里用掉后就没有"没用过的"了；
   SearchQA 和 ALFWorld 新题充足，ALFWorld 余量最大（失败几乎全是"50 步打转"），最可能出现能被认出的效果。代价：贵、
   不测程序路径（程序路径由冒烟用工程夹具题测）。正式运行仍按负责人认可的五个 bench 顺序。
2. **D2 LiveMath 评测块 e03–e08（150 道，至今未读）** 能否改作训练侧验收题。默认：不用（验收 200 道，约 8 到 9 分）。
3. **D3 只读编号的测试集访问**：为了排除重复，程序需要读 SearchQA 预留集（1,000 道）的编号、ALFWorld 测试集的游戏路径，
   只输出计数，不看题目内容。默认：同意。SearchQA 封存的 C/D 块完全不用打开（新抽的题按构造就和 A–D 不重叠）。
4. **D4 SpreadsheetBench 完整数据集（all_data_912）下载。** 默认：不下载。
5. **D5 开发机上遗留的 D3/D14 工作进程（约 2.7 GB）。** 默认：不动，只在清理确认时单独列出。
6. **D6 新接口设置。** 默认：关推理（`reasoning_effort: "none"`，每个回执核对）；名义长度上限问答/表格 8,192、ALFWorld 每步
   1,024；账本按 2 倍上限预留（前提是冒烟 S1-b 通过）；读超时 600 秒/180 秒；8 路并发；走 PJLAB 代理网关。
7. **D7 正式运行是否每步都读测试集。** 每读一次约 3,300 万到 5,700 万 token（ALFWorld 占六到七成以上）。默认：试点只在最后读一次；
   正式运行由负责人届时决定。
8. **D8 测试读数加不加"只给过程说明文字"组（F_desc）**：把收下的过程的说明文字当普通提示给模型、不执行代码，
   直接比较"代码形式"和"文字形式"。约多一组的费用（约 900 万到 1,100 万）。我建议加，因为文献里"代码形式迁移更差"
   正是我们最大的风险。
9. **D9 试点是否作为正式运行的开头。** 默认：是（试点用掉的题在正式运行里也算用过，不能再用来做新的决定）。
10. **D10 验收被拒后工程师能看到什么。** 默认：只看到总体差值和区间，看不到每道题的结果。
11. **D11 复用第 3 版 SpreadsheetBench 的判分引擎与题目合格记录。** 默认：复用，零调用重新核对钉死的哈希。
12. **D12 预测效度"审计"**：在新题充足的 bench 上，偶尔对被筛子拦下的候选也做一次正式验收，检查生成题有没有"误拦好候选"。
    默认：试点不做（多花一批题）。
13. **D13 工程师能否看 ALFWorld 训练局的专家路线。** 默认：不能（避免"事后诸葛亮"式的过程）。
14. **D14 新题充足的 bench 每个做几步。** 默认：试点每个 bench 1 步；正式运行 SearchQA、ALFWorld 各最多 3 步。
15. **D15 预算上限。** 默认：试点做题模型 1 亿、GLM 3,000 万，每步、每角色的上限见 §8.3；第 3 版的 14.4 亿总额不适用。
16. **D16 并发槽位放在整机共用的目录**（所有路线 B 的进程共享 8 路并发）。默认：是。
17. **D17 新协议身份的做法**（整套复制、换新版本号，不改第 3 版任何文件）。默认：是。
18. **D18 测试集授权的新措辞**（写明组别、随机撤除对照、五个测试集与题量）。默认：负责人在读测试集前签一次。

## 12. 术语表（给负责人）

- **路线 B**：这次的方案。学到的 Skill 不是一段文字，而是一组能运行的小程序（"过程"），外加冻结的任务卡。
- **过程（procedure）**：模型写的小程序，在做题前后帮做题模型：往提示里加一段整理好的信息、做精确计算、或者把明显没用的动作标成"不建议"。
- **适用条件（predicate）**：每个过程自带的判断程序，读题面判断"这道题要不要用我"。
- **路由器（router）**：固定代码，对每道题把所有适用条件跑一遍，决定启用哪些过程，并记日志。
- **壳（shell）**：包在做题模型外面的固定代码，负责在合适的时刻运行被启用的过程、组装请求、记录一切。
- **隔离箱 / 沙盒（sandbox）**：运行模型写的代码的 Docker 容器：断网、只读、限 CPU/内存/时间、看不到答案。
- **失败即放行（fail-open）**：过程崩了或超时，就当它不存在，题照常做，只记一次"过程故障"。
- **格式护栏（format guard）**：每个 bench 固定的一句答案格式要求；所有组完全一样；壳保证最终回答原样交给评分。
- **动作规范化（canonicaliser）**：ALFWorld 里把模型写的动作对齐到可选动作的固定代码（例如去掉"action:"前缀）；所有组都开。
- **任务卡（task card）**：每个 bench 一段冻结的说明；这里用的是第 3 版 I 链的五段起点说明，只给当前 bench 的那一段。
- **工程师（engineer）**：GLM-5.3 扮演的角色，读失败记录写过程。
- **考官（examiner）**：GLM-5.3 扮演的角色，写"检测器"和"出题程序"。
- **检测器（detector）**：判断"这次做题是不是某类失败"的小程序，看不到答案；只有在没用来写它的那一半记录上查得准，才收下。
- **出题程序（generator）**：生成练习题的小程序，答案必须由程序或模拟器算出来，不能由模型说了算。
- **饱和带**：当前版本在生成题上的通过率必须在 20% 到 80% 之间，太容易或太难的题集不用。
- **预测效度**：生成题上"新版好还是旧版好"的方向，必须和真实新题上的方向一致；连续两次不一致，这个出题程序作废。
- **捷径检查**：只给选项不给题干（或只给问题不给材料），模型仍然答对的题算"有漏洞"。
- **裁判（judge）**：固定代码判对错（参考答案、模拟器、程序算出的答案），绝不用模型投票。
- **登记员（registrar）**：固定代码，管理题目消耗、分组交错、统计、账本。
- **四组 / 臂（arm）**：验收时同时跑的四种做法：S′（候选新版本）、S（旧版本）、C（只有任务卡）、P（安慰剂过程）。
- **安慰剂过程（placebo）**：占同样的提示位置、做同样多的调用，但只给无关文字，用来排除"多了点东西就变好"的假象。
- **同时段逐题交错**：所有组的题打乱后混在一起发出，避免服务端不同时段的风格变化造成假差异。
- **随机撤除对照（withholding twins）**：在启用了某条过程的题里随机抽一部分，再跑一个"拿掉这条过程"的孪生格；两者之差就是这条过程的因果效果。
- **一次性新题批**：每次验收用一批路线 B 从没用过的训练题，用完作废；记在"题目消耗登记"里，先登记后发出。
- **MDE（最小可检出效果）**：在给定题量下，有八成把握认出来的最小提升，单位是百分点。
- **不劣检验（non-inferiority）**：检验"不比任务卡差超过 5 分"，用于不相似的 bench。
- **L/H 规则**：无法判定的格，对候选算错、对对照算对，保守处理。
- **v2 评分**：在官方评分之外，把写成 JSON 的答案也认出来；保证 v2 不低于官方；截断算错。
- **账本 / 预留**：每次调用前先按上界预留 token，回来再结算；超过上限就停。B 是账本假定的单次回答长度上界。
- **冒烟（smoke）**：正式试点前的小规模真跑，专门检查每个机制都按设计工作。
- **工程夹具题（engineering fixture）**：为测试机制手写的题，答案由程序算出，不算任何实验证据。
- **SearchQA / OfficeQA / LiveMath / SpreadsheetBench / ALFWorld**：五个测试集：检索问答 / 财政公报数字问答 / 数学选择题 /
  表格操作（写 Python 程序） / 文字家务环境（一步步选动作）。
- **FlowEvo / CoEvoSkills / GRASP**：三篇最接近的 2026 年论文（见 §7.6）。
