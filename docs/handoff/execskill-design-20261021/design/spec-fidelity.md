# fivebench-execskill-v1 — registration-grade specification (designer A: fidelity and reuse)

Status: DRAFT for the opposing review, complete in sections 0-12, written 2026-10-21 17:44-18:10 HKT by one of three
independent designers (angle A: fidelity to design-v0 and reuse of the reviewed coevo5 infrastructure).
Read-only work: no model/API call, no pytest, no test-pool access, nothing edited in the repository or on dl
(on dl I only listed and read the two probe logs in `/data/execskill-ops/`).

**Conventions.**
- `[M: source]` = measured, with its source; `[E: assumptions]` = my estimate, with its assumptions; `[R]` = a rule this
  document registers; `[A1]`..`[A15]` = the main agent's working assumptions this rule implements.
- Paths are repo-relative unless absolute. `SP/` = `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/`.
  Map tags: [MAP] SP/understand/map.md, [SB] solver-backends.md, [CI] coevo5-infra.md, [CM] coevo5-method.md,
  [FP] feasibility-prototypes.md, [DP] data-and-pools.md, [LO] linux-ops.md, [SF] scorers-and-formats.md, followed by
  the fact number the reader gave. [RW] = docs/handoff/related-work-execskill-20261021.md, [V6] =
  docs/handoff/coevo5-registration-v6-20261017.md, [DR] = docs/handoff/direction-recommendation-20261021.md,
  [CAL] = docs/handoff/cal1-registration-20261020.md, [DV0] = SP/design-v0.md.
- Sections 0-10 are technical (English, for implementers and critics). The owner summary (below), section 11 and
  section 12 are in plain Chinese.

## 给负责人的一页摘要（白话）

1. **这份文件是什么**：把您 16:4x 认可的"路线 B"设计（Skill 变成一包可执行的小程序；考官一侧也进化；不用验证集）
   写成可以直接照着编程、也可以让反方逐条挑错的登记稿。新协议名 `fivebench-execskill-v1`，新代码包、新输出目录；
   第 3 版（v3）的代码、结果、文件一律不动。
2. **Skill 长什么样**：一个"过程库"。每条过程 = 一小段判断"该不该启用"的程序（适用条件）+ 一小段干活的程序 + 一句说明
   + 几条回放测试。固定代码"路由器"在每道题上把所有适用条件跑一遍，成立的才启用，并记日志。过程只能做三类事：
   往做题模型看到的内容里加一段笔记、替模型做精确计算、在 ALFWorld（文字家务游戏）里把"不建议的动作"标出来。
   过程**不能改模型的最终答案**，答案格式那句话固定不学（防止 E4/E9 那种格式冲突）。
3. **每一步怎么走**：跑题 → 考官诊断（写"检测器"程序找失败类型）→ 考官出题（写"出题程序"，答案由程序或模拟器算出）
   → 工程师改过程 → 在生成题上自测（只当筛子）→ 在一批没用过的真题上验收（四组同时段交错：新包、旧包、只有任务卡、
   安慰剂过程）→ 冻结 → 最后读测试集。
4. **验收怎么判**：新包必须同时比旧包好、比安慰剂好（两个单侧检验都过，且平均至少高 2 分）；每批真题只做一次决定，
   用过就记入"已用登记簿"，再不用。另外在一半启用了新过程的题上，同时段再跑一次"拿掉这条过程"的对照，这样每条过程
   的作用是因果的，不只是相关（FlowEvo 论文的做法）。
5. **诚实的限制**：OfficeQA 只有 74 道、SpreadsheetBench 只有 91 道合格训练题，每个 bench 只够走一步，验收只认得出
   约 10–15 分以上的效果；LiveMath 约 6 分；SearchQA 用新抽的 1,000 道题约 3 分；ALFWorld 134 局约 9–10 分。
   代码形式的过程跨 bench 迁移很可能接近零（文献 "Break It Down" 发现代码技能比文字技能迁移差），读数会照实报告。
6. **默认的试点**：按您定的顺序先走 SpreadsheetBench、再走 OfficeQA，最后同时段读一次五个测试集。估计做题约
   2,800 万 token（账本上限 1 亿，按 2 倍预留），GLM 约 250 万（上限 3,000 万）。**我的建议**（决定 1）：试点改为
   ALFWorld → SpreadsheetBench，因为 ALFWorld 有 3,514 局从没被任何方法用过的新局、验收最有力、失败（找东西打转）
   最像程序能修的类型，而且是唯一能走多步、让考官的淘汰规则真正生效的 bench；代价是估计约 1.1 亿 token，上限需提到 1.6 亿。
7. **需要您拍板的事**列在第 11 节，每条都写了默认做法。

## 0 Identity: name, package, outputs, what is frozen

0.1 [R] Protocol `VERSION = "fivebench-execskill-v1"` in `skillopt/execskill/protocol.py`. Every record kind is
stamped `fivebench-execskill-v1-<kind>` (cell, unit, round, firing-plan, notes-plan, package, registry, test-panel,
evaluation, qualification, manifest, smoke, chain, report). Branch `research/exec-skill-coevolution` (docs/project-status.md:14)
carries the v3 files that are still untracked (`skillopt/coevo5/`, `scripts/run_coevo5.py`, `scripts/weak_solver_probe.py`)
unchanged, so the import list below resolves [MAP B9].

0.2 [R][A14] Closed-set copy. Importing a coevo5 module stamps v3 constants into records [CI F2; MAP §2.0].
- **Import unchanged** (protocol-free or universal constants only): `skillopt.coevo5.{budget, ledger, calls, outcomes,
  stats, checks, roles, leakage}`; `skillopt.continual_eval.{backends (score, _public_view, _response, _native,
  _runtime_limits, _image_ready, _new_alfworld, _AlfSession, _alf_post_observation, _sheet_preview, _xlsx_bytes,
  contract constants), code_delivery, sheet_numeric_adapter, sheet_recalc, spreadsheet_compat}`; `scripts.weak_solver_probe`
  (Client base, `_read_env`, `_validated_url`, `GATEWAY`). Exception classes (`BudgetStop`, `AssumptionBroken`,
  `LedgerFailure`, `Pause`, `ConfigurationError`) are imported from `skillopt.coevo5.outcomes`, never redefined, so
  `STOP_KINDS` in the copied cells/units maps the same classes [CI §4 pitfall].
- **Copy with the new VERSION** into `skillopt/execskill/`: `cells.py`, `units.py`, `evaluation.py` (made multi-arm),
  `qualify.py`, `manifest.py`, `prelaunch.py` (helpers only), `smoke.py`, `chain.py`, `data.py` (pin/ranked/TestAccess
  logic; plus the new registry), and the round primitives of `step.py` (`run_round`, `_order`, `table_of`,
  `shared_unanswered`, `guard`, `violations`, ~100 lines; importing `step` would pull the whole v3 method stack, [CI 3.9]).
- **New**: `solver.py` (shell; copied from `backends.solve` :364-455 and `_solve_alfworld` :715-783 with hooks),
  `package.py`, `router.py`, `sandbox.py` + `execworker.py`, `scorer_v2.py`, `roles_exec.py` (engineer, examiner prompts
  and validators), `detectors.py`, `generators/` (one module per bench), `accept.py`, `registry.py`, `client_elucid.py`,
  `readout.py`, CLI `scripts/run_execskill.py`.
- `core.source_identity` hashes `skillopt/continual_eval/*.py`, so nothing new is placed there [SB F42].

0.3 [R] Outputs (real paths, no symlink component; `safe_path` refuses symlinks [LO F45]); `<D>` = launch date:
`/data/execskill-<D>-source` (snapshot S, sha256 list compared with `cmp` against the Mac list), `/data/execskill-<D>-ops`
(scripts, logs, EXIT markers), `/data/execskill-<D>-pre` (pre-launch ledger, smoke, qualification, data builds),
`/data/execskill-<D>-run` (the chain), `/data/execskill-<D>-run-manifest.json`. tmux sessions `execskill-<chain>`.
Run layout = v3's [MAP §1] plus `shared/registry/<bench>.jsonl` (consumption registry, §2.4),
`shared/packages/<sha>.json` (write-once package store), `shared/generators/<bench>/<gen_id>.json`,
`shared/detectors/<bench>/<det_id>.json`. `/data/execskill-ops/` and `/data/execskill-probe*.py` belong to the probe
and are not reused [LO F2].

0.4 [R] Frozen and untouched: all of `skillopt/coevo5/`, `skillopt/continual_eval/`, `scripts/run_coevo5.py`,
`scripts/weak_solver_probe.py`, the v3 snapshot `/data/coevo5-20261019-v3-source-f`, the v3 run, cal-1, the feasibility
directories, and every frozen scorer (`_score_answer_tag`, env evaluators). Every run script sets
`PYTHONDONTWRITEBYTECODE=1` and runs Python with `-B` (pilots wrote nine .pyc files into snapshot f [FP F34]) and does
`unset OPENAI_API_KEY OPENAI_BASE_URL` after `proxy_on` [LO F18-F19].

0.5 [R][A14] SpreadsheetBench engine and qualification reuse: `IMPORTABLE_QUALIFICATION_VERSIONS =
("fivebench-coevolution-v3",)`; the copied `qualify.load` accepts a v3 record only if (a) its version is in that list,
(b) a zero-call re-verification recomputes the pinned sha256 of the qualification file, the 23-control qualification
(`/root/continual-fivebench-20261003-f-q23/qualification.json`, sha prefix `f5bc90df` [SB F14]) and both image digests,
and (c) the copied record is re-stamped as an execskill import record that names the source. Owner decision 11.D14
(default: reuse). Generated SpreadsheetBench items are always qualified anew (§6.3).

0.6 [R] Disclosure (registered text for the report): "Route B's freshness is method-side: an item is fresh if route B's
own consumption registry has no entry for it. Pool items of OfficeQA (74/74), SpreadsheetBench (91/91 qualified),
ALFWorld pool (57/57), LiveMath (142/283) and SearchQA (555/600) were inputs to the v1 baselines, older learners, v3 or the
10/20-21 feasibility studies [DP §5]; the task cards were written after the development data had been viewed
([DP §6.2]; V6 §2.2). Absolutely fresh sources are used where they exist (SearchQA new HF-validation block; ALFWorld train
games outside the pool)."

0.7 **Contradiction paragraphs** (working assumptions or design-v0 statements against hard facts; I did not deviate
silently).
- **C1, max_tokens "not enforced"**. The fixed fact says "max_tokens 2 still returned 21 tokens with finish stop". The
  probe-2 log shows that request was sent WITHOUT `reasoning_effort: "none"`: completion 21, of which reasoning 19,
  content `'391'` [M: dl /data/execskill-ops/probe-20261021-2.log, line `max_tokens_2 200 ... stop 21 19 63 '391'`]. So the
  visible content (2 tokens) stayed within the cap; the log is equally consistent with "reasoning tokens are not counted
  against max_tokens". Whether the cap binds with reasoning off is untested. A4's rule (reserve and halt against
  2 × max_tokens; flag replies above the nominal cap) is safe either way and is kept; smoke S1 adds the decisive test, and
  truncation detection does not rely on `finish_reason` alone (3.1).
- **C2, "reasoning_tokens = 0"**. With `reasoning_effort: "none"` the field was absent (printed `None`) and
  `reasoning_content` was empty [M: same log, first line]; the per-receipt check therefore treats absent/None/0 as "off".
- **C3, similarity cluster**. design-v0 calls SpreadsheetBench, OfficeQA and LiveMath "the owner-confirmed similar
  cluster"; the registered table has OfficeQA–LiveMath and OfficeQA–SpreadsheetBench but NOT LiveMath–SpreadsheetBench
  [M: V6 §1.1]. Default: the registered table (11.D19).
- **C4, generator retirement**. A8's "two consecutive sign disagreements retire the generator" cannot fire on
  SpreadsheetBench, OfficeQA or LiveMath, where the supply allows one step each (6.2 structural limit, R17).
- **C5, design-v0 minimum effects** (SpreadsheetBench 7, LiveMath 5, OfficeQA 10, ALFWorld 10) are not reachable on
  route-B-fresh items; replaced by the measured/estimated MDEs of 2.1 [DP §5].
- **C6, ALFWorld "new environments sampled in the simulator"**: no environment generator exists; generators select unused
  existing games [M: SF R9, DP F13].
- **C7, "veto actions"**: implemented as a soft veto annotation; a removal or replacement would alter the reply (A5), and a
  veto re-ask would exceed A10's one extra call per item (= per episode on ALFWorld).
- **C8, "answer normalisation checks" on the SearchQA examiner side**: not adopted as a scorer change (that would be answer
  repair or a scorer edit); only reference-free surface-form detectors are built.
- **C9, task-card-only arm**: it equals "card + frozen contract" for QA/Sheet, but on ALFWorld every arm (including C) runs
  in the new loop with the canonicaliser (A9), so arm C there is not v3's frozen loop; and on every bench it is a single
  card, not v3's five-card I-ds prompt (12,681 B [M: CAL frozen arms]).
- **C10, test-read cost**. design-v0/A12 quote ≈ 52–57M per five-bench read with ALFWorld ≈ 75%; that figure is derived
  from v3 I-ds per-cell costs with the five-card Skill [MAP §4 #10]. With single-card prompts my estimate is ≈ 15M without
  ALFWorld and ≈ 47M with it (8.3); the smoke replaces both.
- **C11, D3 "zero errors"**: zero exceptions and property failures over 7,524 steps, but 7,350/7,524 agreement with the
  hand tracker, an induction that transcribed a dictated spec, and an episode gain that is confounded [M: FP F1, F6-F9];
  route B uses the hand tracker only as a smoke fixture, not as evidence.

## 1 Objects

### 1.1 Procedure

```python
@dataclass(frozen=True)
class Procedure:
    id: str            # "p-<origin_bench>-s<step>-<n>", stable across revisions; revision -> version += 1
    version: int
    hook: str          # one of HOOKS below
    applies_src: str   # defines `def applies(view: dict) -> bool`
    body_src: str      # defines the hook's entry point (table below)
    description: str   # <= 600 UTF-8 bytes, plain text, no format directives (lint 1.4)
    replay_tests: tuple[ReplayTest, ...]   # 1..8
    targets: tuple[str, ...]               # failure category ids it claims to address (detector or mechanical ids)
    scope: str         # "all" (router evaluates on every bench) | "<bench>" (origin bench only), set at freeze (4.7)
    origin: dict       # {bench, step, engineer_call_sha256, parent_version_sha256 | None}
    sha256: str        # sha256 of canonical JSON of all fields above except sha256 and scope

HOOKS = {
  "note":    "QA + SpreadsheetBench; body `def run(view) -> str` (<= 2,000 B); pure function of the public view",
  "compute": "QA only; body `def evaluate(expr: str) -> str` (<= 200 B per result); see 1.6.1",
  "repair":  "SpreadsheetBench only; body `def advise(error: dict, view) -> str` (<= 1,000 B); see 1.6.2",
  "state":   "ALFWorld only; body `class State: __init__(self, initial_observation: str); update(self, action: str,
              observation: str) -> None; render(self) -> str` (<= 1,500 B, the D3 bound [FP F10])",
  "advise":  "ALFWorld only; body `def advise(view, state_text: str) -> list[str]` returning <= 10 admissible
              commands to mark as not recommended (soft veto; never removes or replaces an action)",
}

@dataclass(frozen=True)
class ReplayTest:
    trace_ref: str      # cell id of a recorded run-batch trajectory (route B's own records only)
    expect_fires: bool  # applies() must return this on that trajectory's view(s)
    property_src: str   # defines `def check(inputs: dict, outputs: dict) -> bool`, run on the host-side replay record
```

Code rules [R] (checked statically before anything runs; AST pass in `package.py`):
- Allowed imports: `math, fractions, decimal, re, itertools, functools, collections, statistics, string, json, typing`;
  plus `sympy` for `compute` and for generators; plus `openpyxl, pandas, numpy` for SpreadsheetBench `note`/`repair`
  (read-only access to the public input workbook bytes). Forbidden names: `open, exec, eval, compile, __import__,
  globals, locals, vars, getattr/setattr on dunder names, input, breakpoint`, module `os, sys, subprocess, socket,
  time, random, pathlib, importlib, ctypes, pickle, threading, multiprocessing`. Source <= 20,000 B per field.
- Determinism: the worker sets `PYTHONHASHSEED=0`; no clock, no randomness, no I/O; a re-execution of the same request
  must return byte-identical output (checked twice per replay test; a mismatch rejects the procedure).
- Leakage (copied principle of leakage.py [CM F48-F50]): the mechanical checks run on the description, every string the
  procedure EMITS on the replay inputs, and every string/number literal, regex and dict key extracted from the AST;
  compared against the active bench's training pool surfaces and references; any non-`answer_word` hit drops the
  procedure; then one `leak_adjudicate` call per procedure on {description, literals, sample emissions}.
- Inputs whitelist: procedures receive only `public` filtered by the frozen view keys (`_PUBLIC`, backends.py:57-62)
  plus, for SpreadsheetBench, `input_workbook_base64` of the first public input file, and for ALFWorld the step view
  `{initial_observation, observation, admissible_commands, recent_history}`. Never `private`, the reference, the
  verdict, `infos.extra.expert_plan`, `infos.extra.gamefile`, file paths, the ledger [SB F22; CM F10].

### 1.2 Package

```python
@dataclass(frozen=True)
class Package:
    version: str = "execskill-package-v1"
    procedures: tuple[Procedure, ...]   # sorted by id; at most MAX_PROCEDURES = 24 accepted procedures in all
    cards_sha256: str                   # the five frozen card texts (1.3)
    guard_sha256: str                   # the five contract sentences (1.4)
    code_sha256: dict                   # sha256 of solver.py, router.py, sandbox.py, execworker.py, scorer_v2.py
    parent_sha256: str | None
    sha256: str                         # canonical JSON of all fields above
```
Every identity site that hashes Skill text in v3 (cells.py:222, evaluation.py:356/366, step.py:825, chain.py:290 [FP F13])
hashes `Package.sha256` instead; `evaluation.configuration()` additionally digests `code_sha256`, the card and guard
hashes, the canonicaliser version and the sandbox image digest [MAP §2.8].

### 1.3 Task cards [R][A5]

The frozen card of bench b is the v3 I-ds seed instruction (GLM-5.3-written from `texts.CARDS`), read from
`/data/coevo5-20261019-v3-pre/texts/texts.json` and pinned by full sha256 at manifest time (sha256 prefixes [CM 2.10b]:
searchqa `48b10afcc1dd0dcf` 1,846 chars, officeqa `2e92500a832ee32e` 2,926, livemath `9cb3d860ec6970b5` 2,068,
spreadsheetbench `48a5df7f745606ba` 2,907, alfworld `5ae6ea9bffa3902e` 2,301) [M: CM 2.10b]. It is the strongest known text
baseline (cal-1 ids-full +0.094 over the scaffold [M: CAL; DR S1]). The router shows **only the active bench's card**:
E4/E9 measured format conflicts of −9.5 to −33 points when other benches' format advice reached OfficeQA [M: FP F51-F52].
The card text is used verbatim (no `seed_text` heading demotion), so the "task-card only" arm C is exactly:
- QA/Sheet: `system = "Solve the supplied task using only the supplied public information." + CONTRACT[b] +
  "\n\nFrozen skill guidance (use only where applicable):\n" + CARD[b]`, `user = json.dumps(public_view, ensure_ascii=False)`
  (contract-first-v2 layout, backends.py:379-394, 417 [SB F2-F5]).
- ALFWorld: `system = "Act in the text environment. Return a single action inside <action>...</action>." +
  "\nFrozen skill guidance (use only where applicable):\n" + CARD["alfworld"]` (backends.py:730-732 [SB F18]),
  per-step user = the frozen view JSON (backends.py:744-746), in the NEW loop of 1.6.3 (canonicaliser on for every arm).
Contradiction noted: in v3 the I-ds arm rendered all five seeds (12,681 B, [CAL] frozen arms); the C arm here is a single
card, so route B's C arm is NOT v3's I-ds prompt. This is intended [A5].

### 1.4 Format guard [R][A5]

- The fixed per-bench contract sentence, verbatim: SearchQA/OfficeQA `"\nReturn the concise final answer inside
  <answer>...</answer>."`; LiveMath `LIVEMATH_CONTRACT`; SpreadsheetBench `SHEET_CONTRACT_V2`; ALFWorld the fixed
  system opening (backends.py:35, 53-56, 381-390, 730 [SB F3]). Instruction only; no output transformation exists
  anywhere in the shell (a transformer would be answer repair [SF R2]).
- Shell guarantees, enforced by code and by the equivalence tests (1.7): (i) the final reply that is scored is a
  verbatim model reply (QA/Sheet: the last solver reply of the cell; ALFWorld: each step's reply goes through the
  registered canonicaliser of 1.6.3, identically in every arm); (ii) a procedure can add text only inside the `notes`
  key of the user JSON (or `not_recommended` for ALFWorld `advise`); (iii) procedures never see or edit the system prompt.
- Emission lint [R]: any emitted string (and the description) matching, case-insensitively,
  `<\s*/?\s*(answer|action)\b|```|\bjson\b|\breturn only\b|\bformat\b|\bletter\b|\bpython code block\b|\boutput\.xlsx\b`
  is a lint failure: on replay it rejects the procedure; at run time the emission is dropped (procedure_fault 12a).

### 1.5 Router [R]

Fixed code, `router.py`. Inputs: the package, the active bench b, and the item (QA/Sheet) or the step view (ALFWorld).
1. Candidate set = procedures with `scope in ("all", b)` whose hook is legal on b (1.1 HOOKS), in id order.
2. For QA/Sheet, firing and notes are **planned before dispatch** (`firing-plan` record): one sandbox batch job per
   round evaluates `applies(view)` and, where it fires, `run(view)` for every (procedure, item); output
   `{item: [{proc_id, proc_sha, fired: bool, note_sha256, note_bytes, fault: null|reason}]}`, sealed with its sha256 before
   the first cell is dispatched. Because predicates and `note` bodies are pure functions of the public view, the plan
   is exact; it also lets the registrar draw the withholding subsets (§5.5) before dispatch.
3. Caps: at most `MAX_FIRED = 6` procedures per item/step and `MAX_NOTES_BYTES = 6,000` per prompt; excess procedures in
   id order are logged `suppressed_cap` and not run.
4. Composition: `notes = [note_1, ..., note_k]` in id order, each prefixed only by `"note <i>: "` (no procedure ids or
   descriptions reach the solver, so placebo twins are indistinguishable by label). If k = 0 the user JSON has no
   `notes` key and is byte-identical to arm C.
5. ALFWorld: `applies(step_view)` is evaluated at every step inside the episode worker (1.6.3); a `state` procedure's
   `update` runs after every step from step 0 whether or not it fires, so its state is complete when it starts firing.
6. Logs (stored inside the prediction dict, because cells store the whole prediction by hash [CI G3]):
   `activation = [{step|None, proc_id, fired, withheld: bool, shadow_fired: bool|None, emitted_bytes, fault}]`.
   `withheld` procedures (§5.5 twins) are evaluated (`shadow_fired`) but their bodies are not run.

### 1.6 Shell per benchmark [R]

`solver.solve(bench, public, package, arm_spec, call, runtime, plan)` returns today's prediction shapes so that
frozen `backends.score` works unchanged [SF U1]: QA = the scored reply string; Sheet = `{code, cases}`; ALFWorld =
`{won, steps}` + trace. `arm_spec = {procedures_enabled, withheld, placebo_twins}`. Costs = `{"calls": n,
"usage_by_call": [...]}` summed over every solver call of the cell [A10; SB G1].

**1.6.1 QA (SearchQA, OfficeQA, LiveMath).**
- Call 1: `system` = arm C's system prompt (1.3); `user` = `json.dumps({**public_view, "notes": notes}` (notes only if
  non-empty)). Hook location: after backends.py:391-394, before `_response` (:417) [MAP §1].
- `compute` (at most one fired compute procedure per item; if several fire, the lowest id wins, others `suppressed_cap`):
  when it fires, the shell adds the **fixed** invitation as the last note: `"note <i>: You may write arithmetic you want
  evaluated exactly as <calc>EXPRESSION</calc> (at most 8). If you do, you will receive the exact results and be asked
  for your final answer."` If reply 1 contains >= 1 well-formed `<calc>` tag (<= 8 tags, each <= 200 chars), the
  sandbox evaluates each with the procedure's `evaluate`; call 2 is sent with `user = json.dumps({**public_view,
  "notes": notes, "previous_reply": reply1, "calc_results": [{"expression", "result"}]})` (single-turn client
  [SB G2]); the scored reply is reply 2. No tag in reply 1 → reply 1 is scored and no second call is made. Any
  evaluator fault (exception, timeout, output > 200 B, non-string) → no second call, reply 1 is scored,
  `compute_fault` logged (row 12b) [A6, A10].
- Post-call extraction and scoring: unchanged (backends.py:425-436 for the reply-string path).

**1.6.2 SpreadsheetBench.**
- Call 1: arm C's system prompt + `user = json.dumps({**sheet_view, "notes": notes})` where `sheet_view` is the frozen
  rebuilt view (backends.py:397-409 [SB F7]); notes may come from `note` procedures that read the public input workbook.
- `repair` (at most one per item, at most ONE extra call [A10]): after extraction (`code_delivery.extract_python`), the
  shell runs the program once in the route-B sandbox on the single public input case (every training task has exactly one
  case [M: SB F16]); if it raises (the route-B worker returns exception class + the first 500 B of the message, unlike
  `native_worker.py` which drops messages [SB F13]) or writes no output, the procedure's `advise(error, view)` text is sent
  in call 2 (`user` adds `"previous_program"`, `"execution_error"`, `"advice"`); the final program = the program of reply 2
  if one is extracted, else of reply 1. The frozen per-case `_native` execution and the v7 scoring then run on the final
  program exactly as today (backends.py:437-452). The native slot is taken only after the FINAL reply, never between
  calls, to avoid the 3-slot deadlock [SB G3].

**1.6.3 ALFWorld (new copied loop) [A9].**
- Per step t: view = `{initial_observation, observation, admissible_commands, recent_history[-5:]}` (backends.py:739-747);
  `state` procedures' `render()` and fired `note`-like outputs go to `view["notes"]`; fired `advise` outputs (filtered to
  admissible commands) go to `view["not_recommended"]`. Hook locations: pre-call = view construction (:744-746); post-step
  = after :762-764 (state `update(action, post_observation)`).
- **Action canonicaliser, every arm** (D3 `parse/canonical`, pilot_alf_glm.py:165-195 [FP F7]): first `<action>` tag,
  else the whole reply; strip a leading `action:`/`action<|>` wrapper; if the result equals an admissible command after
  case-folding and whitespace collapse, send that admissible string; otherwise send the stripped string. Empty or > 1000
  chars → `invalid_action_format` (as frozen). Its per-step `how` is logged; the per-arm rescued-step share is a
  registered diagnostic (D3: 41% vs 13% rescued steps confounded the tracker effect [M: FP F7]).
- Episode: `_new_alfworld` + `_AlfSession` unchanged, split `"train"`, `max_steps = 50`, seed 42 (protocol.py:355-356);
  `ALFWORLD_DATA` set by the run script, asserted by the backend [LO F33]. The episode worker of 1.8 lives for the whole
  episode. A `state`/`advise` fault disables that procedure for the rest of the episode (row 12d).
- Trace `execskill-alfworld-trace-v1`: per step `{view_sha256, notes, not_recommended, raw_reply, canonical_action, how,
  admissible_commands, post_observation[:12000], activation}` (today's trace lacks raw reply and admissible commands
  [SB F24]).
- ALFWorld procedures make **no** extra solver calls (A10's one extra call per item would be one per episode, too few
  for a veto re-ask; soft veto is pre-call only). Contradiction with design-v0's "否决动作" wording: here a veto is an
  annotation, never a removal, because the shell must not alter the reply [A5].

### 1.7 Equivalence and invariance tests (unit tests, zero model calls) [R]
1. With an empty package and canonicaliser off, `solver.solve` and frozen `backends.solve` produce identical
   `(system, user)` sequences (`calls._request_hash`, calls.py:125) and predictions for every bench, on recorded fakes
   (`tests/coevo5_fakes.py` patterns [CI F45]) [SB §4].
2. With an empty package, arm C of route B equals the same requests with `skill_text = CARD[b]`.
3. No code path writes the scored reply other than the solver's own text (property test over 1,000 random packages
   of fake procedures that try to emit/return anything).
4. Scorer v2 ≥ official on every cell (3.3), and v2 == official for SpreadsheetBench and ALFWorld.
5. Re-execution of any cell from stored replies reproduces identical request hashes (cells.py:139-149) including the
   firing plan and the sandbox outputs.

### 1.8 Sandbox [R][A3]
- Image: the pinned native image `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd`
  (`evolve-skill-native:smoke-20260928`; sympy 1.13.3, pandas 2.2.3, numpy 1.26.4, openpyxl 3.1.5 [M: LO F29-F30, SF F25]).
- Command (copied from `_native`, backends.py:169-178, D3 replay limits [FP F10]): `docker run -i --rm --pull=never
  --name execskill-<uuid> --network=none --read-only --user=65534:65534 --cap-drop=ALL
  --security-opt=no-new-privileges=true --pids-limit=64 --memory=1024m --memory-swap=1024m --cpus=1 --ipc=private
  --log-driver=none --ulimit=nofile=64:64 --ulimit=core=0:0 --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m --workdir=/tmp
  --env PYTHONHASHSEED=0 --mount type=bind,source=<worker dir>,target=/worker,readonly --entrypoint=python <image>
  -I -B /worker/execworker.py`; forced `docker rm --force` bounded at 10 s; unconfirmed cleanup = sandbox infrastructure
  failure (row 12c).
- Lifetime: one long-lived worker per firing-plan batch job, per QA/Sheet cell that needs post-call execution
  (`compute`/`repair` only), and per ALFWorld episode. Protocol: line-delimited JSON over stdin/stdout,
  request `{op: "load"|"applies"|"run"|"evaluate"|"advise"|"state_init"|"state_update"|"state_render"|"detect"|
  "generate", proc_id, input}`, response `{ok, output | error: {class, message[:500]}, cpu_ms}`; response line cap
  65,536 B; per-request CPU limits (RLIMIT_CPU inside the worker): applies 2 s, run/advise/state ops 5 s, evaluate
  10 s, detect 30 s per trajectory, generate 60 s per item; per-worker wall limit 900 s (episode) / 300 s (cell).
  Each `load` execs the procedure source in a fresh module namespace; the worker refuses a second `load` of a different
  package within one lifetime (no cross-cell state).
- Slots: a new slot pool `execskill-sandbox` of 6 file-lock slots (calls.Slots [LO F12]) shared by every process of the
  run root; dl has 7 CPUs and 15 GiB [M: LO F1]; ALFWorld episode slots 6, sheet native 3 as in v3. The smoke measures
  container start latency (unmeasured today [MAP §2.2]); if its p90 exceeds 3 s the registered fallback is one worker per
  round per process (still `load`-isolated) — a container-per-call alternative is rejected because ALFWorld would
  start ~35 containers per episode [E: 34 steps × 1 container].

### 1.9 New decision-table rows (copied `outcomes.classify`, rows 1-11 unchanged [CI F34]) [R][A6]
Procedure faults never become infrastructure unknowns (today they would fall into row 11 and pause a unit above 1/10
[MAP B5]). New rows, evaluated before row 11:

| row | condition | cell outcome | counted as |
|---|---|---|---|
| 12a `procedure_fault` | a predicate/body raises, times out, returns a wrong type, exceeds its byte cap, or fails the emission lint (plan time or run time) | the cell proceeds WITHOUT that procedure (parent behaviour for that procedure); scored normally | fault of that procedure (D3 cap, 5.4) |
| 12b `compute_fault` / `repair_fault` | the post-call evaluator/adviser faults | no second call; reply 1 (program 1) is scored | fault of that procedure |
| 12c `sandbox_unavailable` | container start fails, worker protocol breaks without a procedure-attributable error, or cleanup is unconfirmed | one retry of the sandbox request; then `Pause("sandbox_unavailable")` — a configuration stop, never a fail, never a procedure fault | infrastructure (stop) |
| 12d `state_fault` | an ALFWorld `state`/`advise` operation faults mid-episode | that procedure is disabled for the rest of the episode; the episode continues | fault of that procedure |
| 12e `reasoning_mismatch` | receipt shows reasoning while `reasoning_effort: "none"` was sent (3.1) | undelivered → resend ≤ 2 after 300 s; then row 4 (infrastructure unknown) | delivery |

The activation log records every fault with `{proc_id, op, error_class, message[:500]}`; the engineer receives these
messages only for run-slice trajectories, never for acceptance cells.

## 2 Data

### 2.1 Supplies, orders, slices [R][A1]
One seeded order per bench: `order_b = data.ranked(supply_b, DATA_SEED_EXEC = 20261021, "execskill-order:" + b)`
(sha256 of `[seed, tag, task_id]`, data.py:173-176 [CI F30]); slices are **consecutive** cuts of that one order (never
separate tags: independent tags overlap by chance, 29/18/60 items [DP F6]). Where a bench has a method-side-never-used
tier, the order is computed within tiers and tier 1 is placed first. At the start of every step the registrar
reserves the acceptance slice A as the next |A| unconsumed items of the order (ids only; no role ever sees A's public
views or outcomes before the decision), then cuts the run slice R as the following |R| items; so acceptance slices get
the freshest items, and items of A left unconsumed (5.4a, or no candidate) stay at the front for the next cut.

| bench | supply (route-B fresh at start) | tiers | per step: run slice R × runs (arm S) | acceptance slice A × runs (per arm) | steps possible | MDE of A (S′−S, 80% power) |
|---|---|---|---|---|---|---|
| SpreadsheetBench | 91 qualified pool items (v3 training qualification, reused per 0.5) [M: CI F33] | one (all used method-side) | 45 × 2 | 46 × 2 | 1 | ≈ 12 pts [E: D1's computation from measured same-text noise, 0.122 at 46×2, FP F40] |
| OfficeQA | 74 pool items (50+24) [M: DP §5] | one | 37 × 2 | 37 × 4 | 1 | ≈ 10 pts [E: same, 0.103 at 37×4] |
| LiveMath | 283 pool items | tier 1 = 141 method-side never used, tier 2 = 142 [M: DP §5] | 83 × 2 (tier 2, cut after A) | 200 × 2 (141 tier 1 + 59 tier 2) | 1 (2 with e03-e08, owner 11.D3) | ≈ 6 pts [E: D1 0.056 at 233×2 × √(233/200)] |
| SearchQA | new HF-validation block of 4,000 never-sampled rows (of 11,380 [M: DP §5]) | one (absolutely fresh) | 200 × 2 | 1,000 × 1 | ≤ 3 | ≈ 2.5–3.2 pts [E: DP MDE table, single window] |
| ALFWorld | items file of the 3,514 train games outside the pool [M: DP F13] | REAL region = first 2,000 of the order; GEN region = the rest (for selection generators) | 60 × 1 | 134 × 1 | ≤ 3 | ≈ 9–10 pts [E: DP §5] |

Honest consequence (registered wording): "On OfficeQA and SpreadsheetBench route B can take one step each and its
acceptance certifies only effects of about 10–12 points or more (≈ 12–15 with the two-test intersection rule, §5.4)."
The design-v0 minimum effects of 7 (SpreadsheetBench) and 5 (LiveMath) are not reachable on route-B-fresh items
[E: DP §5 table]; they are replaced by the MDEs above.

### 2.2 Special supplies (no owner release needed; exclusion runs under test access) [R][A1]
- **SearchQA new block**: builder `execskill/data_searchqa.py` (logic of `make_searchqa_fresh_sample.build`,
  scripts/make_searchqa_fresh_sample.py:39-101 [DP F15]) draws 4,000 rows from the HF validation split in one seeded order,
  excluding test ∪ reserve (1,000) ∪ blocks A–D (4,000) ∪ the 600-item pool. The exclusion reads sealed ids, so it runs
  inside code that holds `TestAccess` and emits only `{count, ids_sha256, excluded_counts}` to the operator; blocks C/D
  stay sealed (their ids are used for exclusion only) [DP §4.2]. New ids `execskill-sq:<sha12>`.
- **ALFWorld items file**: `{id: "execskill-alf:<sha12 of gamefile path>", gamefile, task_type}` for train games outside
  the pool; a test-identity check under `TestAccess` asserts that every test-panel game path lies under `valid_unseen`
  and none under `train` (today this identity is only inferred, 134 = TEST_SIZES [DP F13]); `valid_seen` is not used
  (242 task dirs vs 140 games unexplained [MAP §4.3]). Order stratified by the six task types (round-robin within the
  hash order), so every slice is type-balanced.
- **Owner releases** (11.D3, 11.D4): LiveMath evaluation blocks e03–e08 (150 unread), SpreadsheetBench all_data_912
  download — not used by default.

### 2.3 Generated items [R][A8]
Ids `gen:<bench>:<gen_id>@v<n>:<draw_tag>:<k>`; two independent draws per admitted generator per step: `G_self`
(self-test sieve, 4.5) and `G_acc` (predictive validity, interleaved in acceptance, 4.6; never shown to any role before
the decision). Generators read only the public view of their own bench's training supply (never test items, never
other benches' items, never labels except through program/simulator truth) [DP F11]. Generated items never enter the
consumption registry as acceptance material and never decide acceptance.

### 2.4 Consumption registry [R][A1]
`shared/registry/<bench>.jsonl`, append-only (O_APPEND + fsync), one line per item `{item_id, item_sha256, slice:
"run"|"accept", bench, step, unit, ts}` written for the WHOLE slice (for an acceptance slice: its decision subset A*, 5.4a) before the first cell of the
slice is dispatched.
Readers refuse an item already registered; the registry is never reset. A slice is consumed at dispatch; if a step
ends without a candidate (4.5), the acceptance slice is not dispatched and stays unconsumed for the next step on that
bench. Re-attempts after a pause re-use the same slice only to complete undecided cells of the same unit (one
decision per batch). Pilot-consumed items are never reused by a later full run (11.D12 default).

### 2.5 Test sets [R][A12]
Read only by the evaluation unit through `TestAccess` (evaluation.py:231; data.py:232-239) after `shared/consent.json`
with the NEW wording (§7.1): SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 279 (test-side qualification
keeps only qualified items), ALFWorld 134 [M: protocol.py:65]. No role, procedure, detector or generator ever
receives a test item.

## 3 Roles

### 3.1 Solver [R][A4]
- Model `deepseek-v4.1-flash-1017` via a NEW client identity `elucid` (`execskill/client_elucid.py`): subclass of
  `weak_solver_probe.Client` that does not call `super().__init__` (which rejects models outside `MODELS`,
  weak_solver_probe.py:232-233 [SB F28]); URL, key and model read by path from `/root/.config/weak-solver/elucid.env`
  (`ELUCID_CHAT_URL`, `ELUCID_API_KEY`, `ELUCID_MODEL`, mode 600 [M: LO F17]) with `_read_env`/`_validated_url`; the
  manifest stores only the sha256 of the URL string. `httpx` with `trust_env=False` and the explicit approved
  `GATEWAY = http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`. The probes went through environment proxies via
  `urllib` [M: SP/probe/probe_elucid2.py], so the smoke's first call is the check that the explicit gateway reaches this
  host (AGENTS.md: other proxy destinations need review).
- Request: `{"model", "messages": [system, user], "max_tokens", "temperature": 0, "reasoning_effort": "none"}`; no
  `thinking` field. Echoed model must be `deepseek-v4.1-flash-1017` [M: probe logs].
- **Reasoning verification per receipt**: `reasoning_mismatch` iff `usage.completion_tokens_details.reasoning_tokens > 0`
  or `len(message.reasoning_content or "") > 0`. Measured with `reasoning_effort: "none"`: completion 1, the
  reasoning_tokens field absent (printed None), reasoning_content 0 chars [M: dl /data/execskill-ops/probe-20261021-2.log
  line 1]; so absent/None/0 counts as "off". `reasoning_mismatch` joins `UNDELIVERED_ERRORS` (resend ≤ 2 after a 300 s
  cooldown, then infrastructure unknown), like v3's `thinking_mismatch` (outcomes.py:66-67).
- `max_tokens` (nominal, sent): QA 8,192; SpreadsheetBench 16,384; ALFWorld 1,024 per step. `COMPLETION_BOUND = 2 ×
  max_tokens`. The Endpoint reserves and settles against the bound (reservation `4 × (bytes + 512 + bound)`; global halt
  only if `completion_tokens > bound`); `max_tokens < completion ≤ bound` is flagged `over_nominal_completion` and counted.
  Implementation note: if `calls.Endpoint` takes its accounting max_tokens from its own constructor, pass the bound there
  and the nominal value to the client, keeping ledger.py unchanged; otherwise copy `calls.Endpoint` (unit test either way).
- Truncation (completion-aware): `finish_reason ∈ {length, max_tokens}` OR (`completion_tokens ≥ max_tokens` AND the reply
  lacks the bench's closing delimiter: `</answer>` QA, a closed ```python fence Sheet, non-empty action ALFWorld) → truncated
  = fail under the decision metric; reported per arm.
- Read timeout 600 s (probe latencies 2.4–7 s for tiny prompts [M: probe logs]; v3's 2,400 s made one stall a 51-minute
  unit [M: LO F37]; 16,384 tokens at an assumed ≥ 30 tok/s need ≤ 550 s [E]). Client attempts ≤ 4 (unchanged).
- Slots 8 [M: 8/8 delivered in 3.5–4.3 s, probe-2 log]; cell workers 12.

### 3.2 Method roles (GLM-5.3 via BigModel) [R]
Settings as v3: temperature 0, reasoning low, `ROLE_MAX_TOKENS = 16384`, read timeout 900 s, `ROLE_INPUT_BYTES = 220000`,
slots 10, reply = exactly one JSON object through `roles.Roles.ask` (roles.py:92-117 [CM F1-F5]); payloads shrunk with
`roles.fit`; per-row validation (invalid rows dropped with a reason, the call is not failed for one bad row); each role
has ATTEMPTS = 2 where the second attempt is made only if the whole reply was invalid and carries the parse error.
Prompts are frozen verbatim at implementation time and pinned by sha256 in the manifest.

| role | input payload | output schema (JSON) | validator | ceiling per step | fallback |
|---|---|---|---|---|---|
| `engineer_propose` | `{bench, card, package:[{id, version, hook, description, applies_src, body_src, targets, scope}], categories:[{id, name, definition, kind, held_out:{fired_fail, fired_pass, base_fail}}], failures:[≤ 40 trajectory excerpts with verdict, reference, category hits, trace_ref], passes:[≤ 10 excerpts], rejected:[{proc_sha, reason}], api:{hooks, view_keys, limits, imports}}` | `{"procedures":[{"action":"add"\|"revise"\|"retire","id":str\|null,"hook":str,"description":str,"applies":str,"body":str,"targets":[str],"replay_tests":[{"trace_ref":str,"expect_fires":bool,"property":str}]}],"rationale":str}` | exact keys; ≤ 3 add/revise rows; hook legal for the bench; `ast.parse`; static rules 1.1; trace_refs from the provided list | 1 call (+1 retry) | no candidate this step (`method_failure`) |
| `engineer_fix` | failing procedures + exact replay/lint/leak/crash messages + self-test numbers on GENERATED sets only | same schema, ids restricted to the failing ones (fix or `retire`) | same | 1 call (+1 retry) | failing procedures dropped |
| `detector_write` | `{bench, categories, uncovered:[≤ 40 failed WRITE-half trajectories with verdict and reference], passes:[≤ 20], api}` | `{"detectors":[{"name":str,"definition":str≤300,"detect":str,"category":str}]}` (≤ 3) | `ast.parse`, static rules, must not read keys outside the trajectory view | 2 calls (+1 retry each) | mechanical library only |
| `generator_write` | `{bench, card, truth_kinds, api, weak_categories, generators:[gate history]}` | `{"generators":[{"name":str,"description":str,"code":str,"target_category":str}]}` (≤ 2) | `ast.parse`, static rules, smoke instantiation of 3 items in the sandbox | 1 call (+1 retry) | existing generators only |
| `generator_revise` | generators that failed the band gate + their pass rates | same schema, same ids | same | 1 call | generator not admitted this step |
| `generator_crosscheck` (OfficeQA, LiveMath) | one generated item's public text (never the generator code) | OfficeQA `{"formula"}` (forward.CHECK_SYSTEM["officeqa"] reused [CM 4.3]); LiveMath `{"code"}` defining `RESULT` | evaluated by `forward.evaluate` / the sandbox | ≤ 1 per generated item | item dropped (`crosscheck_invalid`) |
| `leak_adjudicate` | `{rule: description + literals + sample emissions, colliding_items?, answer_values?}` | `{"verdict","reason"}` (leakage.py:73-90) | as v3 | 1 per procedure (and per fix) | procedure dropped |

The engineer sees reference answers of run-slice failures (as v3's analyst saw evidence); the leakage pipeline (1.1)
and the input whitelist keep them out of procedure code and inputs. **No role ever sees acceptance-batch outcomes**;
it sees only the accept/reject bit of earlier steps (the D1 rule [FP F41]).

### 3.3 Judge (fixed code) [R][A2]
`execskill/scorer_v2.py`, version `execskill-scorer-v2`, never edits frozen scorers. Per cell it records four blocks
[SF 3b]: (1) `official` = `backends.score` + `outcomes.classify`; (2) `v2` = official pass OR JSON-extracted pass (QA: if
no `<answer>` tag, the last JSON object with key `"answer"` (string or number, also inside a ```json fence); a JSON object
inside the tag is unwrapped as a second channel; comparison = the bench's frozen rule; SpreadsheetBench and ALFWorld:
`v2 = official`, written explicitly); unit-test invariant v2 ≥ official on every cell; (3) `lenient` (descriptive, plus
OfficeQA `numeric_equal_but_em_fail`); (4) format flags (`answer_tag_present`, `tag_count`, `json_answer_present`,
`json_inside_tag`, `boxed`, `bare_letter_no_tag`, `last_line_fallback_used`, `program_delivered`, `excel_formula_only`,
`fence_glued`, ALFWorld `action_tag_present` per step and `inadmissible_actions`, `canonicalised_steps`, `truncated`,
`over_nominal_completion`, `reasoning_mismatch_resends`, `reply_chars`, `completion_tokens`). **Decision metric** = the
v2 verdict, completion-aware (truncation/filter/empty = fail; infrastructure unknown stays unknown). Also recorded:
`first_reply_v2` for cells with a second call (descriptive within-cell effect of `compute`/`repair`), and
`guard_changed_answer` (always False under an instruction-only guard; asserted).

### 3.4 Registrar (fixed code) [R]
Owns the slices and registry (2.4), the firing/notes plans (1.5), the twin assignment (5.5), the one seeded interleaved
shuffle of every job of a round (copied `run_round`/`_order`, step.py:79-80, 105-121 [CM F42]), the statistics (§5), the
ledger scopes (§8) and the decision records. It is the only component that reads acceptance outcomes before the
decision; it writes `decision.json` (write-once) and exposes to roles only `{accepted: bool}`.

### 3.5 Prompt drafts (frozen verbatim at implementation time; the implementer may fix wording, not content) [R]
- **engineer_propose (system)**: "You improve a solver by writing small deterministic Python procedures that a fixed shell
  runs around the solver's model calls. You never write the answer and you cannot change the solver's reply. Hooks
  available on this benchmark: {hooks with signatures and byte caps}. A procedure has: `applies(view) -> bool`, decided
  only from the public view keys {view_keys}; a body for its hook; a description (≤ 600 bytes); replay tests that name
  recorded trajectories (`trace_ref`), whether `applies` must fire there, and a `check(inputs, outputs)` property. Allowed
  imports: {imports}; no I/O, clock or randomness; the same input must give the same output. Your procedures may depend
  only on what the solver sees: never on reference answers, on whether an answer is correct, on scores, or on facts about
  particular items (literal answers, item-specific strings). Do not give answer-format instructions; the format is fixed
  elsewhere. Address the failure categories listed; prefer procedures whose predicate is narrow and checkable. Return one
  JSON object: {schema}. At most 3 rows with action add or revise." User = the payload of 3.2, JSON with sorted keys.
- **engineer_fix (system)**: "Each listed procedure failed a check; the exact messages are given. For each, return a fixed
  version under the same id or `retire`. Same rules and schema."
- **detector_write (system)**: "Write Python predicates `detect(traj) -> bool` that recognise one kind of failure from the
  trajectory alone. The trajectory has these keys: {keys}; it does not contain the reference answer or the verdict, and
  your code will be tested on other trajectories whose outcomes you have not seen. A good detector fires mostly on failed
  attempts and on a meaningful share of them. Return {schema}, at most 3 detectors."
- **generator_write (system)**: "Write `generate(source_public, rng) -> item | None` that turns one public training item
  of {bench} into a NEW item whose correct answer your code computes exactly ({truth kind}). Use only the source item's
  own content and computation; do not use regularities of answer keys or labels; for multiple choice, place the key at the
  letter given by `rng` and never use the sentence '{STRONGER_OPTION}'. Target this weakness: {category}. Aim for items
  the current solver solves 20–80% of the time. Return {schema}, at most 2 generators."
- **generator_crosscheck (system)**: OfficeQA = `forward.CHECK_SYSTEM["officeqa"]` unchanged [CM 4.3]; LiveMath =
  "Write a Python program that computes the exact value asked for in this problem and assigns it to RESULT; use sympy or
  fractions; no options are shown to you."

## 4 One step on bench b (parent package S, k-th step on b)

Each sub-step is one unit (`units.run_unit` copy: lock, attempt-N, write-once `unit.json`, Pause semantics [CI F21]);
unit names `s<g>-<b>-k<k>/<substep>` with g the global step index.

**4.1 Run** (`run`). Register the run slice R (2.4), then run arm S on R × runs (2.1) in one seeded interleaved round.
Record full trajectories (1.5 activation log, 1.6 traces, all receipts). When S contains procedures that fire on b
(carried from earlier benches), arm C also runs on R × 1 run: the descriptive "entry reading" of S − C on b before b is
learned (no decision uses it). Guard: an infrastructure-unknown share
> 0.10 pauses (copied `guard`, step.py:150-157). Split R by item (not by cell) into WRITE and CHECK halves:
`ranked(R, 20261021, "execskill-half:<b>:k<k>")`, first ⌈|R|/2⌉ items = WRITE.

**4.2 Diagnose** (`diagnose`; examiner, first half).
- Mechanical detectors (fixed code, reference-free, registered; validated like model-written ones but never counted as
  examiner evolution) [A7]: QA `no_answer_tag`, `json_answer_only`, `multiple_answers_in_tag`, `truncated`,
  `empty_reply`, `long_reply` (> 2,000 chars); Sheet `no_program`, `excel_formula_only`, `fence_glued`,
  `program_crash_precheck`, `no_output_written`; ALFWorld `step_budget_exhausted` (steps = 50), `revisit_empty ≥ 3`
  (a `go to X` where X was already reached and nothing new was observed there), `repeated_action_loop` (one action ≥ 3
  times in the last 6 steps), `invalid_action_share ≥ 0.2`, `wrapper_actions ≥ 1`.
- Run every accepted detector of b and the mechanical library on all R trajectories; uncovered failures = WRITE-half
  failures on which no detector fires. If uncovered ≥ 8 cells and ≥ 20% of WRITE-half failures: `detector_write`
  (≤ 2 calls, 3.2).
- **Detector acceptance** (6.1) on the CHECK half. Accepted detectors persist per bench; a detector whose lift falls
  below 0.05 on the run batches of two consecutive steps is retired.
- Output: `diagnosis.json` = per category {definition, kind, WRITE counts, CHECK stats, ≤ 5 example trace_refs}.

**4.3 Generate** (`generate`; examiner, second half; skipped on SearchQA [A8]).
- Re-gate every persisted generator of b on the current S (band, 6.2 G2) using a new `G_self` draw; at most one
  `generator_write` call when fewer than 2 generators are admitted; at most one `generator_revise` call for generators
  outside the band.
- Policy [R]: generators target the two most frequent failure categories of the run batch that have an accepted or
  mechanical detector; the examiner sets difficulty only through generator code and its parameters.
- Gates G1 (truth by program/simulator), G2 (band), G3 (shortcut) as in 6.2, with v3's drop accounting copied
  (`DROPS`, forward.py:53-54).
- Output: admitted generators with frozen code sha256 and their `G_self` and `G_acc` draws (G_acc sealed, unseen).

**4.4 Engineer** (`engineer`; Skill side).
- `engineer_propose` (3.2) with the diagnosis, ≤ 40 failure excerpts (WRITE and CHECK halves; references included,
  host-side), ≤ 10 passes, the package, earlier rejection reasons.
- Pipeline per proposed row, in order: static AST rules → sandbox `load` → replay tests → zero-fault sweep → emission
  lint → mechanical leakage → `leak_adjudicate`.
  - Replay test passes iff `applies` returns `expect_fires` on the referenced trajectory's view(s), `check(inputs,
    outputs)` is True, and a second execution is byte-identical.
  - Zero-fault sweep: `applies` (and the body where it fires) runs without fault on EVERY recorded trajectory of b's run
    batches so far, and — if the procedure would get scope "all" — on every recorded run trajectory of earlier benches
    (a predicate is evaluated everywhere, so it must not crash anywhere) [DV0 step 4].
  - Replay proves determinism and absence of crashes, not repair [CM §5.9]; repair is measured only in 4.6.
- Any failure → one `engineer_fix` call with the exact messages; re-run the pipeline; still failing → dropped.
- Candidate `S′ = S + surviving adds/revisions − retirements`. If `S′ == S`: no candidate; the step ends, the
  acceptance slice stays unconsumed (2.4).

**4.5 Self-test** (`selftest`; sieve only, never acceptance).
- Arms S′ and S, 1 run, interleaved, on the `G_self` draw of every admitted generator of b and on the persisted `G_self`
  sets of earlier benches. A set on which no procedure of `S′ ∖ S` (or retired by S′) can fire is skipped: the two arms
  are identical by construction (hook legality, 1.1).
- Pass iff, on every set with ≥ 20 items, `mean(S′ − S) ≥ −0.05`; S′'s procedure-fault share ≤ 0.02; S′'s format-flag
  rate (no tag, JSON only, no program, invalid action) exceeds S's by ≤ 0.05.
- Fail → one `engineer_fix` with the generated-set numbers, a new `G_self` draw, one re-run; fail again → no candidate.
- With no generated set (SearchQA; or every generator failed its gates) the self-test is recorded as "replay and
  zero-fault only".

**4.6 Accept** (`accept`; version level, §5). Compute the decision subset A* of the acceptance slice A from the firing
plan (5.4a), register A*, then one interleaved round with arms S′,
S, C, P(S′), the withholding twins (5.5) and, for each admitted generator, its sealed `G_acc` draw under arms S′ and S
(for predictive validity only). The registrar computes the decision (5.4) and writes `decision.json` once; generators'
predictive-validity records are updated (6.2 G4).

**4.7 Freeze** (`freeze`). `S_next = S′` if accepted, else `S`. Scope of each newly accepted procedure p: `"<b>"` if, on
some earlier bench's `G_self` set where p fires on ≥ 10 items, the self-test delta of 4.5 was < −0.05; otherwise `"all"`
(predicate-gated). Scope uses generated items only — never another bench's real items (no validation set) [DV0 §2].
The REPORTING labels "通用 / 仅本 bench" come only from the test-read withholding evidence (7.4) [A11]. The package is
written to `shared/packages/<sha>.json` (write-once) and becomes the parent of the next step.

**4.8 Test read** (`evaluate`, §7): pilot once at the end [A12]; full run per owner decision 11.D13.

**Stop rule per bench**: at most K_b steps (2.1); stop after two consecutive steps with no acceptance, or when the
next slice pair does not fit the supply.

## 5 Acceptance statistics

5.1 **Arms** [R]. S′ (candidate), S (parent), C (task card only, 1.3), P = P(S′) = S′ with the body of every procedure in
N = (new or revised in S′) replaced by its sham twin. Sham twins keep the predicate, the hook kind, the prompt slot and the
call trigger, and carry no task information:
- `note`: deterministic irrelevant text with the same byte length as p's note on that item (both computed in the notes
  plan), cut from a registered placebo corpus (the eight v3 placebo texts, `PLACEBOS_SCREEN`/`PLACEBOS_CONFIRM`,
  protocol.py:102-124 [CM F45]) at an offset keyed by the item id; passes the emission lint.
- `compute`: the same fixed invitation; the sham evaluator returns `"unavailable"` for every expression; the second call
  is made under exactly the same trigger (≥ 1 well-formed `<calc>` tag), so call counts follow the same rule.
- `repair`: same trigger (crash or no output in the pre-check); call 2 carries only the fixed text "The program did not
  run successfully. Return the complete program again." (no error message, no advice).
- `state`: renders length-matched irrelevant text each step (p's real state runs in shadow to measure the length).
- `advise`: `not_recommended` holds the same number of entries, each the literal `"none"`.
At the first step of the first bench, S = C (empty package): C still runs as a separate arm and the S − C contrast is
the registered same-round noise floor (cal-1 `parent:B` pattern [CAL]).

5.2 **Interleaving** [R]. Every job (arm × item × run, twins, `G_acc` cells) is placed in ONE seeded order
`_order(range(n), "execskill-accept:<b>:k<k>:" + unit)` and run on one thread pool; never sorted by arm. Serving drift
moved the same text by +22 points across windows on OfficeQA and terse-reply shares from 5% to 96% per 15-minute bin
[M: FP F45]; only co-scheduled contrasts are interpreted.

5.3 **Per-item outcome** [R]. Decision metric = v2 completion-aware verdict (3.3). Per item and arm the mean over runs; the
candidate S′ uses L (unknown = fail), comparators S, C, P use H (unknown = pass) — v3's conservative convention
(stats.bounds, stats.py:19-28 [CM F38]). Items on which no arm got a delivered reply leave every contrast
(`shared_unanswered`, step.py:139-147).

5.4 **Decision rule — one decision per batch** [R]. Accept S′ iff all hold:
- (D1) `d̄(S′ − S) ≥ 0.02` and its one-sided 95% item-bootstrap percentile lower bound > 0 (10,000 resamples of items,
  seed 20261022) — the D1 study's rule [FP F41];
- (D2) the one-sided 95% lower bound of `d̄(S′ − P)` > 0 — added because D1's rule alone accepted a +0.036 placebo when
  replayed on cal-1 [M: FP F37];
- (D3) S′ cells with ≥ 1 fault of a procedure in N ≤ 2% of S′ cells [A6];
- (D4) S′'s format-flag rate ≤ S's + 0.05;
- (D5) every arm's infrastructure-unknown share ≤ 0.10 and shared-unanswered items ≤ 10% of A* (5.4a); otherwise the round is
  "undetermined": pause, owner decision, the batch is burned if no decision is made.
(D1) ∧ (D2) is an intersection-union test, so it holds level 0.05 without a multiplicity correction; its power at the
tabulated MDE is below the single-contrast 0.8 (≈ 0.65–0.8 [E: the two contrasts share S′'s noise; correlation 0.3–0.6]),
so the effective certifiable effect is ≈ 1.1–1.2 × the MDE column of 2.1. C is descriptive: `d̄(S′ − C)` and `d̄(S − C)`
with two-sided 95% CIs (cumulative gain over the card, same window).
- Across a full chain of 5–9 decisions, each at 0.05, the chance of at least one false acceptance under a global null is
  ≈ 0.2–0.35 [E: independent decisions]; the report states the number of decisions and treats the test read as the
  confirmatory evidence.

5.4a **Decision subset** [R]. On QA and SpreadsheetBench the firing plan is known before dispatch, and on an item where no
procedure of N (or retired by S′) fires, S′, S and P send byte-identical requests (checked by request hash before
dispatch, zero calls). Such items carry only noise. The registered decision subset is therefore
`A* = {i ∈ A : some procedure of N ∪ retired(S′) fires on i}`; all arms and twins run on A* only, the contrasts of 5.4 are
computed on A*, and the report gives both the effect on A* and the implied whole-batch effect (|A*|/|A| × effect on A*).
Only A* is written to the registry; `A ∖ A*` is never dispatched, nobody sees an outcome on it, and it returns to the
supply. A* is selected from public views by predicates fixed before the slice is opened, so it is independent of
outcomes. If |A*| < 15 the round is not run ("too few firing items") and nothing is consumed. ALFWorld: A* = A (firing
is decided per step during the episode). The §8 costs assume A* = A (upper bound).

5.5 **Random withholding control** [R][A11]. For each p ∈ N the registrar draws before dispatch
`W_p = first ⌈|F_p|/2⌉ of ranked(F_p, 20261021, "execskill-withhold:<b>:k<k>:" + p.id)`, where F_p = acceptance items on
which p fires in the notes/firing plan (QA/Sheet; exact). ALFWorld: F_p = all acceptance games (firing is known only
after the episode). Each item of W_p gets a twin arm `S′∖p` (p withheld; its predicate still runs for the
`shadow_fired` log) with S′'s run count, in the same shuffle.
- Estimand τ_p = mean over W_p of [S′ − S′∖p] (both arms scored with L/H as in 5.3: S′ with L, twin with H). QA/Sheet:
  the effect of p where it fires (on items where it does not fire, the two arms are identical by construction).
  ALFWorld: the effect of making p available in an episode; the split by `shadow_fired` is reported as descriptive only
  (post-treatment).
- τ_p is never a decision criterion; it feeds freeze evidence (4.7), secondary predictive-validity comparisons (6.2) and
  the report.
- Size: at most 3 procedures in N; W_p ≤ 23 items (SB), ≤ 19 (OQ), ≤ 100 (LM), ≤ 500 (SQ), 67 games (ALF). Cost in §8.
  At these sizes τ_p resolves only large effects (SB/OQ ≈ ±20 pts [E: MDE ∝ 1/√n from 2.1]); the report says so.

5.6 **Power statement** [R]. The MDE column of 2.1 is the registered "minimum effect" per bench (replacing design-v0's
3–10 points): SpreadsheetBench ≈ 12, OfficeQA ≈ 10, LiveMath ≈ 6, SearchQA ≈ 3, ALFWorld ≈ 9–10 points, single window,
before the IUT factor. A rejection means "an effect of that size was not shown on this batch", never "no effect".

## 6 Examiner evolution

### 6.1 Detectors [R][A7]
- Form: `def detect(traj: dict) -> bool` over the trajectory view `{bench, public_view (whitelisted), notes,
  replies (raw), extracted_answer | final_program | actions, steps: [{view_sha256, admissible_commands, raw_reply,
  canonical_action, how, post_observation}], format_flags, activation}`. No reference, no verdict, no `private`, no
  expert plan: the worker receives only this dict [A3].
- Ground truth is pass/fail only (decision metric), anchored; model-written category labels are never acceptance
  evidence (the v3 diagnosis role sees the reference, examiner.py:481-498 [CM §5.5]).
- **Acceptance on the CHECK half** (items not used to write it): with n_f fired cells, x of them failing, base failure
  rate π of the CHECK half: accept iff n_f ≥ 12, `x/n_f − π ≥ 0.15`, one-sided exact binomial `P(X ≥ x | n_f, π) < 0.05`,
  and recall `x / fails_CHECK ≥ 0.10`. The binomial treats cells as independent; runs of one item are correlated, so a
  run-0-only sensitivity reading is reported beside it. Example: at π = 0.6 a detector needs ≥ 11 failures in 12 fired
  cells (P = 0.020) [E: exact binomial arithmetic].
- What an accepted detector is used for: category counts and examples for the engineer (4.4), targets for generators
  (4.3), and per-arm category rates at acceptance (descriptive: did S′ reduce the failures it targeted?).
- Honesty rule: detector acceptance is selection evidence about the examiner's diagnostic vocabulary, not evidence
  that S improved (the same caveat v3 wrote for BA, examiner.py:14-15 [CM §5.5]).

### 6.2 Generators [R][A8]
Form: `def generate(source_public: dict, rng) -> dict | None` returning `{public, private, truth: {kind, program_sha256,
value}}`; `rng` is a seeded `random.Random` passed by the worker (the only randomness allowed). Inputs: the public view
of one training item of b (from the run slices; never acceptance slices, never test). Forbidden: any use of training
labels' regularities — concretely, LiveMath generated items must not contain `STRONGER_OPTION` (protocol.py:220-222),
keys follow a balanced letter schedule, and no generator receives `private` (D6's mirror forms used the fact that the
meta option is always the key [M: FP F31]; this is excluded).

Per-bench truth kinds:
- SpreadsheetBench: synthetic workbook + reference program run in the sandbox; answer cells written as literal values
  (openpyxl-written formulas have no cached values and would fail qualification [SF R5]); the item must pass
  `qualify.qualify` (two v7 scorings of the reference submitted as the answer, zero model calls [SF F24]); forbidden
  functions, `_xlfn.`/`_xlws.`, structured references excluded [SF F22].
- OfficeQA: perturb-and-recompute on the source item's own rendered page text (no cell grid exists [SF G5]): the
  generator rewrites k numbers of one table region, states the rounding sentence, and returns a formula; truth =
  `forward.rounded(forward.evaluate(formula), decimals)` (forward.py:196-231 [SF F27]); an independent
  `generator_crosscheck` formula written from the item text must evaluate to the same value, else the item is dropped.
- LiveMath: D6's symbolic pattern (definition + sympy program → exact value; options from typed claims; exclude integrals
  and series that sympy leaves unevaluated; validate numerically at 50 digits) [SF G6]; truth requires that the
  generator's value and an independent crosscheck program agree, and the independent program must be one of the agreeing
  pair (the D6 critic's fix [FP F27]).
- ALFWorld: a selection program over the GEN region of the items file, using only what is public before the episode (task
  type, the initial observation's receptacle list, goal text); truth = the simulator's `won`. There is no environment
  generator; "new environments" means unused existing games [SF R9; MAP §4.10].
- SearchQA: none (no program truth). Paraphrase probes are not built in the pilot (11.D11).

Gates:
- **G1 truth**: every kept item's reference is host-computed as above; drop reasons counted per generator.
- **G2 band**: on `G_self` (≥ 30 items QA/Sheet, ≥ 20 games ALFWorld; 1 run of arm S), the pass rate must lie in
  [0.20, 0.80]. E9's generated panel was saturated at 0.891 for the empty scaffold and missed a real −9.5 harm [M: FP F52];
  the band has never been reached by any v3/feasibility generator [FP K4].
- **G3 shortcut**: LiveMath options-only probe (question replaced by `"[question withheld]"`, 2 runs): items correct in
  both runs are dropped; a generator whose options-only cell accuracy exceeds 0.35 (chance 0.20 + 0.15) is rejected.
  OfficeQA question-masked probe (context kept, 1 run): correct items are dropped; generator rejected above 0.10.
  SpreadsheetBench and ALFWorld: not applicable (recorded as N/A).
- **G4 predictive validity** (at acceptance): with `d_real = d̄(S′ − S)` on the acceptance batch and `d_gen = d̄(S′ − S)` on
  the generator's sealed `G_acc` (≥ 40 items, 20 games; both restricted to items where N fires, as in 5.4a), the
  comparison is eligible iff `|d_real| ≥ 0.05`; agreement iff
  `sign(d_gen) == sign(d_real)` (`d_gen = 0` counts as disagreement). Two consecutive eligible disagreements retire the
  generator. Secondary, reported only: the same sign comparison per procedure p (τ_p on W_p vs S′ − S′∖p on `G_acc`) when
  `|τ_p| ≥ 0.05` and |W_p| ≥ 20.
- **Structural limit, stated in advance**: on SpreadsheetBench, OfficeQA and LiveMath route B takes one step, so a
  generator there gets at most one eligible comparison and can never be retired by the two-disagreement rule; its status
  is reported as `agreed-once`, `disagreed-once`, or `not-eligible`. The rule can bite only on ALFWorld (≤ 3 steps).
  Owner 11.D10 may count secondary per-procedure comparisons towards retirement (default: no).

### 6.3 What "examiner accepted" means [R]
- **Examiner evolved at step g** iff ≥ 1 model-written detector passed 6.1, or ≥ 1 model-written generator passed G1–G3.
- **Examiner validated** (the headline claim of the examiner side) iff ≥ 1 generator has ≥ 1 eligible agreement and no
  retirement at the end of the run.
- Reported separately per bench: detectors written / accepted / retired; generators written / admitted / retired; the G4
  sequence of each generator with d_gen, d_real and eligibility. If no generator is ever validated, the report says
  "the examiner side evolved detectors only" (design-v0 risk 3; [RW] Claim 2 warning).

## 7 Transfer and test readout

### 7.1 Consent and unit [R][A12]
New multi-arm evaluation unit (copied `evaluation.py`, generalized: arms per unit, `unseal` keyed by (arm, task_id),
reuse keyed by the package sha256 + `configuration()` digest [CI F24-F26]). `shared/consent.json` keys
`{test_evaluation, sheet_test_qualification, by, date, note, arms, package_sha256}`, `by == "owner"`. Registered note
text: "我同意在方法冻结后，用登记的四组（最终包、只有任务卡、安慰剂过程、文字形式说明）加随机撤除对照，同时段交错读一次
五个测试集；读完不再改方法。" The SpreadsheetBench test-side qualification runs once (write-once pointer) as in v3.

### 7.2 Arms at the test read [R]
- F (frozen final package), C (task card only), P_F (F with every accepted procedure's body shammed, 5.1), and
  F_text (C plus the accepted procedures' descriptions rendered as text guidance, no code: the code-vs-text contrast,
  11.D17, default on for QA/Sheet, off for ALFWorld).
- Withholding twins: for every accepted procedure p and every test bench where p's hook is legal, `F∖p` on a seeded 50%
  of the test items where p fires (QA/Sheet, exact from the firing plan) or 50% of the games (ALFWorld).
- **Identical-by-construction rule**: on a bench where no accepted procedure has a legal hook (e.g. ALFWorld after a
  SpreadsheetBench/OfficeQA-only pilot), F and P_F send exactly C's requests; they are not run, and the report states
  "the package cannot act on this bench; F ≡ C by construction, not measured". Default for that case: C is not run either
  (11.D18), saving ≈ 7.4M tokens per arm [E: 134 × 55k].
- All arms and twins of all benches in one seeded interleaved round (one evaluation child process per bench, as
  chain.py:153-224, but with a shared seeded order per bench and a common start barrier).

### 7.3 Bench classes (registered similarity table, V6 §1.1, unchanged) [R]
Similar pairs: SearchQA–OfficeQA, OfficeQA–LiveMath, OfficeQA–SpreadsheetBench; ALFWorld similar to none [M: V6 §1.1].
For a package evolved on a set E of benches: own = E; similar = benches similar to some bench in E, minus E;
dissimilar = the rest. Default pilot (E = {SpreadsheetBench, OfficeQA}): similar = {SearchQA, LiveMath}; dissimilar =
{ALFWorld}. Recommended pilot (E = {ALFWorld, SpreadsheetBench}): similar = {OfficeQA}; dissimilar = {SearchQA, LiveMath}.

### 7.4 Readouts (fixed in advance) [R]
- **Own**: `F − C` per own bench, one-sided 95% item-bootstrap lower bound; claim "own gain" iff LB > 0.
- **Similar**: `F − C` per similar bench, point estimate and two-sided 95% CI, **descriptive** (the owner's 10/17 style;
  these benches cannot certify small effects: OfficeQA test 172 items supports ≈ 6.6–7.7 pts [E: DP §5 scaling]).
- **Dissimilar, pooled non-inferiority**: `D = mean over dissimilar benches of (F − C)` (equal weights), claim
  "no drop" iff the one-sided 95% LB of D > −0.05 (5 points pooled; design-v0 "允许下降约 4 到 5 分"); single-bench
  readings with CIs are reported and can only exclude drops of about 7–11 points or more [M: DR §5 第 3 步甲路]. With a
  single dissimilar bench (default pilot: ALFWorld only, and identical by construction) the pooled test reduces to that
  bench or to "by construction".
- **Placebo**: `F − P_F` on every bench where it is run (is it the procedures' information or the slot/call?).
- **Code vs text** ([RW] Break It Down: code-form skills transferred worse than text-form ones): `F − F_text` per
  bench with two-sided CIs, and pooled over similar ∪ dissimilar benches; pre-stated reading: "if F_text ≥ F off the
  own benches, the code form did not transfer better than its own description".
- **Per-procedure table** (the transfer readout [DV0 §3]): for each accepted p × each bench: fire rate in arm F (enable
  log), |W_p|, τ_p = mean(F − F∖p) on W_p with CI. Labels, assigned only from τ_p [A11]:
  - `transfers to b` iff b ≠ origin, |W_p| ≥ 20 and τ_p's one-sided 95% LB > 0;
  - `harmful on b` iff τ_p's two-sided 95% CI lies below 0;
  - `general` (通用) iff it transfers to ≥ 1 non-origin bench and is harmful on none;
  - `this bench only` (仅本 bench) iff it fires on < 20 test items on every non-origin bench, or transfers nowhere and is
    harmful nowhere;
  - otherwise `unresolved`. Enable rates alone never produce a label (they are observational: fired items differ
    from non-fired ones [RW] Claim 4).
- Expected (pre-stated): near-zero transfer outside the table/number cluster; most procedures `this bench only` or
  `unresolved` [RW §6.6; CM §5.11].

### 7.5 Test-read schedule
Pilot: once at the end [A12]. Full run: owner decision 11.D13 — every step (5 reads) or once at the end; the five-domain
per-step table exists only in the first option.

### 7.6 Positioning against the closest prior work [R] (wording for the paper and the report)
- **Not claimed**: "first executable skill library", "first co-evolving verifier", "first cross-benchmark transfer"
  [RW §5, §8 item 9].
- **FlowEvo** (arXiv 2607.21596): executable skills with preconditions, replay tests, banned imports, per-skill utility
  by withholding on matched episodes; each benchmark starts from an empty bank, no cross-benchmark transfer. Route B
  adopts that representation and its withholding idea (5.5), and differs in: one cumulative package across five
  benchmarks with per-procedure cross-benchmark τ_p; a deterministic router that logs every enable decision; an anchored
  examiner; acceptance on one-shot fresh batches against parent, card-only and placebo arms.
- **CoEvoSkills** (arXiv 2604.01687): a surrogate verifier that writes executable tests co-evolves with the skills, no
  validation set, results on the same tasks it evolves on. Route B's anchors are fixed referees (official/v2 scorer,
  simulator, program truth) on items never used before, and its generators are retired by predictive validity on fresh
  real batches; no examiner output is ever an acceptance criterion.
- **GRASP** (arXiv 2605.29668): accepts a skill on a held-out probe from the training split not used to propose it,
  re-runs the parent concurrently, caps regressions; its gate helps in-domain, not out of distribution. Route B spends
  each probe batch once (registry), adds placebo and card-only arms, and keeps the dissimilar-bench non-inferiority
  reading as the primary transfer claim because of GRASP's out-of-distribution finding.
- **Break It Down, Pass It On** (arXiv 2608.20274): code-form skills transfer worse than text-form; the F_text arm and the
  per-procedure table report this risk directly (7.4).
- **Claimed novelty** (measurement and gating): (1) the examiner's predictive-validity gate; (2) one-shot fresh-batch,
  placebo- and card-controlled version acceptance inside the learning loop; (3) per-procedure cross-benchmark
  attribution with random withholding.

## 8 Budgets [A13]

### 8.1 Per-cell anchors and estimates
| bench | measured anchors (deepseek-v4-flash, no reasoning) | route-B arm C estimate | arm S′ estimate |
|---|---|---|---|
| SearchQA | E-ds 1,236, I-ds 4,088 per cell [M: FP F32]; D1 1,531 per cell over 6 arms incl. scaffold+SearchQA seed [M: FP F35]; cal-1 ≈ 3,400 [M: FP F61] | 1,600 | 1,750 |
| OfficeQA | E-ds 4,690, I-ds 7,927 [M: FP F32] | 5,300 | 6,500 (half the cells make a compute second call) |
| LiveMath | E-ds 1,251, I-ds 3,969 [M: FP F32] | 1,650 | 2,200 |
| SpreadsheetBench | E-ds 2,010, I-ds 4,273 [M: FP F32] | 2,600 | 3,400 (a quarter make a repair call) |
| ALFWorld (episode) | E-ds 28.5k, I-ds 105.7k; prompt/step 807 vs 3,364 [M: FP F17]; tracker call 1,225 vs 873 [M: FP F2] | 50k | 57k |

[E: assumptions] 4 characters per token for card text; the single card replaces the 593-byte scaffold and the other four
seeds of I-ds; the new model's reply lengths with `reasoning_effort: "none"` equal deepseek-v4-flash's non-reasoning
lengths (unmeasured; the smoke replaces every number above); ALFWorld ≈ 34 steps per episode at ≈ 1,250 prompt tokens per
step plus ≈ 350 tokens of notes for S′. The ledger cap is ≈ 2 × the estimate because the ledger is a lower bound and
billed usage differed from the ledger in cal-1 (27.5M ledger, ≈ 17.6M billed, ≈ 14M actual receipts [M: DR §4 改, S3]).

### 8.2 Per step (solver tokens) [E: sizes of 2.1, costs of 8.1]
| step | run | generate + self-test | G_acc | acceptance (4 arms) | twins | total | registered cap |
|---|---|---|---|---|---|---|---|
| SpreadsheetBench k1 | 45×2 = 0.23M | 0.52M | 0.48M | 368 cells = 1.18M | 138 cells = 0.47M | ≈ 2.9M | 6M |
| OfficeQA k1 | 37×2 = 0.39M | 1.8M (incl. shortcut probe, SB sets) | 0.96M | 592 cells = 3.55M | 228 cells = 1.48M | ≈ 8.2M | 15M |
| LiveMath k1 | 83×2 = 0.27M | 1.5M | 0.35M | 1,600 cells = 3.4M | 600 cells = 1.3M | ≈ 6.9M | 12M |
| SearchQA (each k ≤ 3) | 200×2 = 0.64M | ≈ 2M (earlier benches' sets) | 0 | 4,000 cells = 6.8M | ≈ 450 cells = 0.8M | ≈ 10.2M | 20M |
| ALFWorld (each k ≤ 3) | 60 = 3.0M | 2.0M band + 4.4M self-test | 4.4M | 536 episodes = 29.5M | ≤ 201 episodes = 11.5M | ≈ 55M | 80M |

GLM per step [E]: engineer ≤ 4 calls, examiner ≤ 7 calls (≤ 75k tokens each at 220,000 input bytes + 16,384 output), plus
crosscheck (D6 measured 397 tokens per LiveMath item [M: FP F32]) and leak adjudication: ≈ 0.4–1.0M; the D3 tracker came
from one 4,986-token call [M: FP F1]. Registered per-step ceilings: engineer 0.5M, examiner 0.9M, leak 0.1M (1.5M in all).

### 8.3 Pilot and chain totals [E]
- **Default pilot** (SpreadsheetBench → OfficeQA, test read at the end, ALFWorld identical by construction): 2.9 + 8.2 +
  test ≈ 13.8 (4 arms on QA/Sheet ≈ 11.4 + twins ≈ 2.4) + smoke ≈ 3 → **≈ 28M solver**, GLM ≈ 2.5M.
- **Recommended pilot** (ALFWorld → SpreadsheetBench, 11.D1): 55 + 2.9 + test ≈ 47 (QA/Sheet ≈ 13.8; ALFWorld F, C, P_F
  ≈ 22.1 + twins ≈ 11.5) + smoke ≈ 3 → **≈ 108M solver**, GLM ≈ 2.5M.
- **Alternative** (ALFWorld → SearchQA): ≈ 55 + 10.2 + 47 + 3 ≈ 115M.
- **Wall clock** [E]: ALFWorld training episodes took a median 290–348 s, p90 up to 1,929 s under contention [M: LO F36];
  536 acceptance episodes on 6 episode slots ≈ 8–9 h, a 134-game test arm ≈ 2 h; QA/Sheet rounds of 400–4,000 cells at
  8 slots ≈ 1–4 h (D1: ≈ 1.4 h for 1,200 SearchQA cells [M: FP F41]).
- **Full chain**, default order (K = 1, 1, 1, 3, 3), test once at the end ≈ 263M; with a test read after every bench
  ≈ 340–410M. design-v0 estimated 400–600M [DV0 §3]; the v3-anchored figure for one five-bench read is ≈ 56.7M with
  ALFWorld ≈ 75% [MAP §4 #10, inferred from I-ds costs]; route B's single-card prompts make reads cheaper, if the
  estimates of 8.1 hold.

### 8.4 Registered caps and halts [R]
- Solver ledger root `deepseek:execskill`: **100M** for the default pilot (160M if 11.D1 picks an ALFWorld pilot);
  per-step scopes `deepseek:execskill:<b>:k<k>` with the caps of 8.2; test read `deepseek:execskill:test` 30M (default
  pilot) / 70M (ALFWorld pilot); smoke and pre-launch `deepseek:execskill:pre` 10M.
- GLM root `overall` (glm-5.3): **30M** for the pilot; per-step role ceilings as in 8.2 (scopes
  `overall:execskill:<b>:k<k>:<role>`).
- A new scope helper replaces `budget.step_scope`/`deepseek_scope` (they accept only the kinds learning/evaluation,
  budget.py:55, 70 [CI F11]) and keeps the `rooted` rule (budget.py:59-64). The v3 1.44B envelope does not apply.
- A cap reached → `BudgetStop` → pause; never auto-resumed; the owner decides. One Endpoint per unit attempt (halt
  generation, calls.py:145 [CI F7]).

## 9 Smoke test specification [R]

Run on dl from snapshot S (`/data/execskill-<D>-source`, sha256 list verified) under `/data/execskill-<D>-pre/smoke-<n>`,
own ledger, cap 10M solver + 2M GLM. The sealed smoke spec is the smoke's run id (smoke.py pattern [CI 3.12]). Every
stage writes `summary.json`; a failed stage stops the smoke (no automatic continuation).

| stage | what | calls | pass criterion |
|---|---|---|---|
| S0 static | full unit-test suite of `skillopt/execskill` + the v3 suites (must still pass unchanged); equivalence tests 1.7; v2 ≥ official invariant; lint and AST rules; worker determinism | 0 | all pass |
| S1 endpoint | through the explicit `GATEWAY`, `reasoning_effort: "none"`: 6 sequential tiny requests, 8 concurrent, and the **max_tokens test**: max_tokens 8 on a prompt needing ~200 tokens ("List the first 60 prime numbers, comma-separated") | ≈ 16 | status 200; echoed model `deepseek-v4.1-flash-1017`; reasoning off on every receipt (field absent/0, no reasoning_content); prompt_tokens ≤ bytes + 512; 8/8 concurrent; the max_tokens result recorded (enforced: completion ≤ 8 with finish `length`; not enforced: the bound rule of 3.1 stays the only protection) |
| S2 sandbox | 30 container starts (latency p50/p90); worker protocol round trip; escape probes (network, file write outside /tmp, fork bomb vs pids 64, 2 GiB allocation vs 1 GiB, CPU loop vs RLIMIT); determinism (same request twice) | 0 | all probes contained; p90 start ≤ 3 s, else the registered fallback (1.8) |
| S3 shell fixture | a hand-written, registered **fixture package** (not learned): SearchQA/OfficeQA/LiveMath `note` ("numbers in the context with their years and units" for OfficeQA; "option lengths" for LiveMath), one `compute` (exact rational arithmetic), one Sheet `note` (column headers and row count of every sheet) and one `repair`, one ALFWorld `state` (D3's hand tracker `tracker_ref.py`, 62 lines [M: FP F1]) and one `advise` (already-checked empty receptacles); arms C, F_fixture, P_fixture; 4 items per QA/Sheet bench, 2 ALFWorld games; items = the first items of each bench's step-1 RUN slice (registered as slice `smoke`; run slices are not decision material) | ≈ 120 + 6 episodes | every hook path exercised; activation logs complete; request hashes reproduce on re-execution; twins indistinguishable in prompt shape; usage summed over calls |
| S4 format check | per bench 20 items of the step-1 run slice × arm C × 1 run (ALFWorld 5 games) | ≈ 85 + 5 episodes | required-format pass ≥ 9/10 per bench (smoke.format_check floor [SF U3]); otherwise owner decision before launch; truncation share recorded per bench (> 2% → registered fallback: raise that bench's max_tokens to 2×) |
| S5 generators | zero-model instantiation of fixture generators: 10 SpreadsheetBench items through `qualify.qualify`; 10 LiveMath sympy items (D6 fixture) with crosscheck by a fixture program; 10 OfficeQA perturbations with `forward.evaluate`; ALFWorld selection of 10 GEN-region games | 0 (+ ≤ 20 GLM crosscheck calls) | ≥ 7/10 kept per bench; every kept truth reproduces; drop reasons recorded |
| S6 roles | one `engineer_propose`, one `engineer_fix`, one `detector_write`, one `generator_write` on recorded smoke-S3 trajectories | ≈ 6 GLM calls | JSON accepted by the validators (2 attempts allowed); code parses; pipeline 4.4 runs to a verdict; tokens per call recorded |
| S7 mini step | the full 4.1-4.7 pipeline on SpreadsheetBench with tiny sizes inside the smoke root: run 6 items, generated "acceptance" of 10 items (smoke only — explicitly not a real slice), twins, `decision.json`, freeze; then the multi-arm evaluation unit on a FAKE test set without `TestAccess` | ≈ 150 | registry lines written before dispatch; one seeded shuffle across arms; decision computed; package stored write-once; evaluation unit seals and unseals per (arm, task) |

Release rule: after the smoke, the chain is launched in tmux with `bash -i run-chain.sh` (which runs `proxy_on`, then
`unset OPENAI_API_KEY OPENAI_BASE_URL`), and the first real responses (status 200, echoed model id, reasoning off) are
confirmed before it is left running (AGENTS.md). Expected smoke cost ≈ 2–3M solver, ≈ 0.3M GLM [E: S3/S4/S7 cell counts
× 8.1].

## 10 Risks and failure modes, each with its honest reporting rule [R]

| # | risk (evidence) | design response | reporting rule |
|---|---|---|---|
| R1 | Code-form procedures transfer worse than text, near zero outside the table/number cluster ([RW] Break It Down; v3 analyst never proposed cross-bench placements [CM §5.11]) | per-procedure τ_p with withholding; F_text arm | report the per-procedure table with `unresolved` entries; never infer transfer from enable rates; state "code did not transfer better than its own description" when F_text ≥ F |
| R2 | Nothing is accepted on SpreadsheetBench/OfficeQA (MDE 10–12, ≈ 12–15 with the IUT) | sizes registered in advance | write "an effect of ≥ X points was not shown", never "no effect" |
| R3 | Placebos are not inert (cal-1 −9.8 to +3.6 points [M: CM F47]); a sham compute call can help through a second look | D2 requires S′ > P; twins keep slot and call | report all four arms; S′ − P is the information effect, S′ − S the package effect |
| R4 | Generators never reach the 20–80% band or fail predictive validity (E1 +13 generated vs 0 real; E9 saturation [M: FP F50, F52]) | gates G1–G4; generated items never decide | "examiner evolved detectors only"; the G4 table is printed even when empty |
| R5 | Detectors fail on small CHECK halves (base failure rates high) | thresholds 6.1, run-0 sensitivity | counts and thresholds printed; mechanical detectors never counted as examiner evolution |
| R6 | Engineer code is fragile (21/49 v3 proposals died of small faults [M: CM §5.2]) | per-row validation, 2 attempts, one fix round, fail-open faults, 2% cap | funnel per step: proposed → static → replay → lint → leak → self-test → accepted |
| R7 | Serving drift between windows (terse share 5–96%; OfficeQA ±22 points [M: FP F45]) | single interleaved round per decision | every result labelled "one serving window"; terse-reply share per arm |
| R8 | New endpoint behaviour (max_tokens possibly unenforced, reasoning flag, proxy, rate limits, silent model change) | per-receipt reasoning check, completion bound, echoed id, smoke S1 | counts of `reasoning_mismatch`, `over_nominal_completion`, truncations per arm |
| R9 | The canonicaliser changes the sign of an ALFWorld effect (D3: rescued steps 41% vs 13% [M: FP F7]) | same canonicaliser in every arm | rescued-step share per arm reported beside every ALFWorld contrast |
| R10 | In-sample hindsight (D14's "55 of 57 targets on open surfaces" came from walkthrough metadata [M: FP F16]) | roles never see expert plans or metadata; procedures cannot read them | D14 facts are not given to any role; stated in the report |
| R11 | Answers leak through code literals, regexes or predicates matching one task | AST literal extraction + mechanical checks + adjudicator | drops per reason per step |
| R12 | Winner's curse on accepted effects (≈ 1.3–1.5× [M: DR §4 改]) | test read is the unbiased estimate | acceptance effects marked "selected"; only test-read effects are quoted as effects |
| R13 | Test sets are read again (v1 test opened 10/19 [M: DR §4 留]) | read only after freeze, owner consent, once in the pilot | disclosure in every report |
| R14 | Sandbox resource contention on 7 CPUs; ~21 leftover D3/D14 workers (~2.7 GB) [M: LO F39] | slot pool, limits, smoke S2 | latency and fault counts; leftovers only removed by the owner (11.D15) |
| R15 | Budget overrun (ALFWorld episodes, unenforced max_tokens) | bound-based reservation, per-scope caps, no auto-resume | spend per scope vs estimate in every report |
| R16 | SearchQA headroom ≤ 3 points [M: DR §2] | SearchQA's main role is "dissimilar no-drop" | a SearchQA rejection is not evidence against the method |
| R17 | Predictive validity is structurally untestable on one-step benches (6.2) | stated in advance; ALFWorld is the only multi-step bench with generators | status `agreed-once / disagreed-once / not-eligible`; no retirement claim from SB/OQ/LM |
| R18 | Multiple decisions across the chain (≈ 0.2–0.35 chance of ≥ 1 false acceptance under a global null [E]) | the test read is confirmatory | number of decisions and the expected false-acceptance count printed |

## 11 需要负责人拍板的事（每条都写了默认做法）

1. **试点顺序（决定 1，最重要）**。默认按您定的顺序：先 SpreadsheetBench（表格编程题）再 OfficeQA（财政公报计算问答），
   最后读测试集；估计做题约 2,800 万 token（上限 1 亿）。缺点：这两个 bench 的训练题太少，每个只够走一步，验收只认得出
   约 10–15 分以上的效果；考官一侧"连续两次方向不一致就作废出题程序"这条规则在只走一步的 bench 上根本没有机会生效。
   **我的建议：试点改为 ALFWorld（文字家务游戏）→ SpreadsheetBench**，理由：① ALFWorld 有 3,514 局任何方法都没用过的
   新局，验收题是真正"全新"的，134 局能认出约 9–10 分；② 失败多是找东西打转，可以用固定程序判断，检测器的验收有意义；
   ③ 两个 bench 都有程序或模拟器算出的真值，考官两半都能进化。代价：估计约 1.1 亿 token，上限需提到 1.6 亿。
   备选：ALFWorld → SearchQA（约 1.15 亿）。
2. **"没用过"怎么算**：默认＝路线 B 自己的历史里没用过（用"已用登记簿"记账，每道题只用一次）；以前的基线、v3 和夜间
   试验用过哪些题，在报告里照实写出。
3. **LiveMath 评测块 e03–e08**（150 道封存的留出题）是否放出来当训练侧材料：默认不放。
4. **SpreadsheetBench all_data_912**（约 512 道未核实的新题，需要代理下载）：默认不下载。
5. **评分器 v2 当决策指标**（官方判对或 JSON 写法的答案判对就算对，保证不低于官方；截断算错）：默认是。官方分照样并报。
6. **做题接口设置**：新接口身份 elucid、模型 deepseek-v4.1-flash-1017；关闭推理（reasoning_effort 设为 none，每条回执
   核对推理 token 是否为 0）；max_tokens 问答 8,192、表格 16,384、ALFWorld 每步 1,024；账本按 2 倍预扣；读超时 600 秒；
   并发 8；走登记过的 PJLAB 代理。方法角色（工程师、考官）继续用 GLM-5.3。默认如此。
7. **沙箱**：模型写的程序只在固定的 docker 镜像里运行，断网、只读、限 CPU/内存/时间，每道题或每局一个容器：默认如此。
8. **过程出错**：出错就当这条过程没启用、照常做题，记一次"过程故障"；候选包故障超过 2% 的格就不收：默认如此。
9. **检测器的标准**：只用"对/错"这一个有锚的结果，不用模型给的失败类别标签：默认如此。
10. **出题程序的淘汰**：出题程序跨步保留；只有真题上新旧版本差至少 5 分时才比方向；连续两次方向相反就作废；
    单条过程的撤除对照是否也计入淘汰次数：默认不计。
11. **SearchQA 的"换说法、答案不变"探针**：默认不做（没有程序真值，说不清由谁来证明答案没变）。
12. **试点用过的题，正式全程不再用**：默认如此。
13. **正式全程读测试集的次数**：每走完一个 bench 读一次（多花约 8,000 万–1.5 亿，换来逐步的五域表），还是只在最后读
    一次：默认只在最后读一次；试点固定只在最后读一次。
14. **复用 v3 的 SpreadsheetBench 判分引擎和训练题合格名单**（零调用重新核对固定的哈希值）：默认复用。
15. **dl 上 D3/D14 留下的约 21 个孤儿进程**（约 2.7 GB 内存）：默认不动，由您决定是否清理。
16. **预算上限**：见第 8 节（试点做题 1 亿、GLM 3,000 万，每步、每个角色另有上限）；碰到上限就暂停，不自动续跑。
17. **测试时加一组"文字形式说明"**（把收下的过程的说明当文字给模型，不运行代码），直接比较代码和文字哪个迁移得好：
    默认问答与表格加，ALFWorld 不加（太贵）。
18. **包里没有过程能作用于某个 bench 时**（例如只学了表格和问答，ALFWorld 上一条都不可能启用），最终包与任务卡发出的
    请求一字不差：默认不读这个 bench（默认试点省约 2,200 万），报告写"按构造相同、未测"。
19. **相似关系表**：沿用 10/17 登记的那张（注意：那张表里 LiveMath 和 SpreadsheetBench 不算相似，和设计稿"前三个是
    一簇"的说法不一致）：默认沿用登记表。
20. **读测试集的同意书措辞**（第 7.1 节）：请确认。
21. **随机撤除对照的比例**：默认 50%。
22. **每步最多改 3 条过程，整个包最多 24 条**：默认如此。
23. **代码身份**：新代码包整套复制、换新版本号，不直接调用会盖上 v3 印记的模块：默认批准。
24. **正式全程的 bench 顺序**：默认保持 SpreadsheetBench → OfficeQA → LiveMath → SearchQA → ALFWorld。

## 12 术语表（给负责人）

- **Skill / 过程库 / 包**：这里的 Skill 是一包可执行的小程序（"过程库"），跟着做题模型一起跑；"包"指某一版的全部过程。
- **过程**：一个小程序，由四样东西组成：适用条件（判断这道题该不该启用的程序）、干活的程序、一句说明、几条回放测试。
- **回放测试**：拿以前记录下来的做题过程重新喂给这个程序，检查它不崩溃、输出前后一致、确实在它声称要修的题上启用。
  它只能证明程序可靠，不能证明能提分；提分只在验收时测。
- **路由器**：固定代码，每道题（ALFWorld 每一步）把所有适用条件跑一遍，成立的过程才启用，并记"启用日志"。
- **壳**：包在做题模型外面的固定代码，负责在调用模型前后运行被启用的过程。
- **五类挂钩**：笔记（往模型看到的内容里加一段文字）；精确计算（模型写算式，壳算出准确结果再问一次）；修复回合（表格
  程序报错时，把错误提示给模型再要一次程序）；状态记录（ALFWorld 里记下去过哪里、看到什么）；不建议动作（ALFWorld 里
  标出不建议的动作，只是提示，不替模型改动作）。
- **任务卡**：每个 bench 一段固定的作答说明（用 v3 那五段 GLM 写的说明），不学；路由器只给当前 bench 的那一段。
- **格式护栏**：每个 bench 固定的一句答案格式要求（如"把答案写在 <answer> 标签里"），只是一句指令；壳保证任何过程都
  不能改模型的最终答案。
- **动作规范化**：ALFWorld 里把"action: go to desk 1"这类带包装的写法还原成合法动作；所有组都用，所以不会造成组间差别。
- **沙箱**：一个断网、只读、限资源的 docker 容器，模型写的程序只能在里面运行。
- **检测器**：考官写的小程序，只看做题过程（看不到标准答案），判断"这一格像不像某类失败"；在没用来写它的另一半记录上
  查准、查全达标才收。
- **出题程序**：考官写的小程序，按真题改出新题，答案由程序或模拟器算出。三道关：真值由程序算；当前包在上面的通过率在
  20%–80% 之间（不太难也不太易）；捷径检查（遮住题干只看选项也能答对的题判为有漏洞）。
- **预测效度**：验收时，新旧版本在生成题上的分差方向必须和在真题上的方向一致；连续两次不一致的出题程序作废。
- **G_self / G_acc**：同一个出题程序的两批独立生成题；前者给自测用，后者封存到验收时才用，只用来查预测效度。
- **S′ / S / C / P**：候选新包 / 上一版包 / 只有任务卡 / 安慰剂包。**F**：冻结后的最终包；**P_F**：最终包的安慰剂版；
  **F_text**：任务卡加上各条过程的说明文字、不运行代码。
- **安慰剂孪生**：和真过程用同一个适用条件、占同样的位置、触发同样多的额外调用，但给的是无关文字或"不可用"。
- **随机撤除对照（τ_p）**：在一半启用了某条过程的题上，同时段再跑一次"拿掉这条过程"的版本；两者之差 τ_p 就是这条
  过程的因果作用。
- **新鲜 / 已用登记簿 / 切片**：每个 bench 的题按一个固定随机顺序排好，切成连续的几段（跑题段、验收段），每段只用一次；
  用之前先写进登记簿。
- **MDE（最小可分辨效果）**：在这么多题上，有八成把握认出来的最小提升；比它小的效果"认不出"，不等于"没有"。
- **下界（LB）**：区间的下端；"单侧 95% 下界 > 0"即有把握说是正的。
- **交集并检验（IUT）**：新包必须同时赢旧包、赢安慰剂，两个检验都过才收；这种组合不需要额外收紧门槛。
- **L / H**：有缺失结果时的保守算法：候选组的缺失按错算（L），对照组的缺失按对算（H）。
- **非劣检验（NI）**：检验"下降不超过某个幅度"（这里是不相似 bench 合并后不超过 5 分）。
- **按构造相同**：两组发给模型的请求一字不差，所以不必再测。
- **评分器 v2**：官方评分判对，或从 JSON 写法里取出的答案判对，就算对；保证每一格都不低于官方分。
- **截断**：回复被长度上限切断；决策指标里算错。
- **reasoning_mismatch（推理不符）**：要求关闭推理却收到了推理内容的回复，按"没送达"重发，仍不行记为基础设施缺失。
- **elucid / GATEWAY**：elucid 是新接口在代码里的名字；GATEWAY 是登记过的 PJLAB 代理地址。
- **账本 / 预扣**：记录 token 花费的文件；每次调用前按上限预先扣一笔，防止超支。
- **五个 bench**：SearchQA（检索问答）、OfficeQA（美国财政公报计算问答）、LiveMath（数学选择题）、SpreadsheetBench
  （写程序改 Excel 表格）、ALFWorld（文字家务游戏）。
- **v3 / cal-1 / D1、D3、D6、D14、E1、E4、E9**：第 3 版正式运行；10/20 的标定实验；10/21 夜间的探索方向编号
  （D1 新题验收试跑，D3 ALFWorld 记事程序，D6 程序出题，D14 ALFWorld 失败剖析，E1 验证端试验，E4/E9 负迁移=格式冲突）。
- **FlowEvo / CoEvoSkills / GRASP / Break It Down**：最接近的四篇 2026 年论文（可执行技能库；与技能一起进化的验证器；
  用训练集里没用过的样本验收技能；代码技能比文字技能迁移差），对比见 7.6 节。
