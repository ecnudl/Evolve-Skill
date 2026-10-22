# fivebench-execskill-v1 — registration-grade specification, ANGLE B (measurement first)

Designer B, 2026-10-21. Read-only work: no repository file, nothing on dl and no paid call was touched or made; the only
dl access was a read-only `cat` of the two endpoint probe logs. Calculations are zero-call scripts in
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/specB-calc/`
(`mde.py`, `cost2.py`). Map tags: [MAP] = understand/map.md, [DP] data-and-pools, [FP] feasibility-prototypes,
[SF] scorers-and-formats, [SB] solver-backends, [CM] coevo5-method, [CI] coevo5-infra, [LO] linux-ops,
[RW] docs/handoff/related-work-execskill-20261021.md, [V6] docs/handoff/coevo5-registration-v6-20261017.md,
[CAL] docs/handoff/cal1-registration-20261020.md, [DR] docs/handoff/direction-recommendation-20261021.md.
Every number is tagged **M** = measured (source) or **E** = estimate (assumptions).

## 给负责人的摘要（白话）

1. 这份稿子的出发点是"先问量得出什么，再定怎么做"。每个结论都事先写明：用哪批题、多少题、能分辨多大的差别、
   分辨不了时怎么写。
2. 每个 bench 只走一步（试点两步）。一步里做题模型先在一批"本路线从没用过的训练题"上做题，考官和工程师据此
   各自改进，最后在另一批同样没用过的训练题上，四组同时段逐题交错比一次：新包、旧包、只有任务卡、安慰剂。
   新包必须**同时**胜过旧包和安慰剂才收下；这一批题只做这一次决定，之后作废。
3. 量得出的最小差别（80% 把握）：SearchQA 1,000 题约 2–3.4 分；LiveMath 200 题约 4.5–6.8 分；ALFWorld 200 局
   约 7–8 分；OfficeQA 50 题×4 次约 6.5–11.6 分；SpreadsheetBench 60 题×2 次约 8–13 分。负责人认可的顺序前两个
   bench 只认得出 8–13 分的大效果，这是题量决定的实话。
4. 试点默认按认可的顺序做 SpreadsheetBench → OfficeQA（做题约 4,200–7,500 万 token，含最后读一次测试集）。
   我建议负责人考虑改成 SpreadsheetBench → ALFWorld：ALFWorld 余量最大、题源充足、模拟器给真值，验收和
   "生成题能否预测真题"这两件事都量得出来；代价约 7,900 万–1.33 亿 token（第 11 节第 1 项）。试点就是整条链的前两步，题不会重复用。
5. 考官一侧只有两种东西算"被收下"：在没用来写它的轨迹上查准率、查全率达标的失败检测器；以及过了真值、
   难度、捷径三关，并且在真题上"方向说对了"的出题程序。没有一个达标就如实写"考官一侧没有进化成功"。
6. 每条过程在别的 bench 上有没有用，靠"随机拿掉对照"读：同一道题、同一时段，再做一遍拿掉这条过程的版本，
   两者之差才是因果效应。单条过程只认得出 10–20 分以上的效应，所以多数会写"未分辨"。
7. 按文献（Break It Down）与本项目证据，代码形式的过程很可能只在本 bench 有用；登记时先写明这个预期，
   结果照实报告。
8. 需要负责人决定的 16 件事在第 11 节，每件都给了默认值。

## Contradiction and correction paragraphs (read before the body)

- **K1, max_tokens (A4).** The working assumption says the gateway does not enforce `max_tokens`. The probe-2 log
  (`dl:/data/execskill-ops/probe-20261021-2.log`, read 2026-10-21) shows `max_tokens_2 ... stop 21 19 63 '391'`, i.e.
  completion 21 of which reasoning 19: the visible content was 2 tokens. With `reasoning_effort: "none"` the same
  request returned `completion_tokens 1`, `reasoning_tokens None` (field absent), 0 reasoning characters (M, same log).
  So the cap may apply to content and exclude reasoning. This does not change A4's rule (it is safe in both cases) but
  it changes the smoke: test S-E4 (§9) decides with a long-answer prompt whether the cap is enforced with reasoning off
  and whether `finish_reason` then says `length`. Until S-E4 passes, truncation is detected by token count, never by
  `finish_reason` alone. Also: "reasoning off" must be checked as `reasoning_tokens in (None, 0)` AND empty/absent
  `reasoning_content`; `None` is the observed value, not 0.
- **K2, predictive validity needs repeated comparisons (A8).** Each bench is visited once in the chain, so a bench's
  generator meets exactly one real acceptance batch; "two consecutive disagreements" could never trigger. Registered
  fix: the generated set is solved by all four acceptance arms, and every pairwise arm contrast that is *informative*
  on the real batch (§6.3) counts as one comparison, in a registered order. Later steps cannot add comparisons for an
  earlier bench without reading that bench's real items again, which the no-validation-set rule forbids. Consequence
  stated plainly: in the pilot most generators will end "untested" (no informative real contrast).
- **K3, step 1 parent = task-card arm.** At step 1 the parent package S0 is empty, so S0 and the task-card-only arm send
  byte-identical requests. The C arm then is a same-text duplicate (cal-1's parent:B role); §5.6 uses it as the noise-
  floor check. From step 2 on, S ≠ C because inherited procedures may fire.
- **K4, cost anchors.** The map's ~56.7M per test read (map §4 item 10) and the I-ds per-cell anchors (FP F32) include
  the whole five-instruction Skill (12,681 B; CAL frozen arm table). Under A5 only the active card is shown, so card-arm
  cells are cheaper; §8 uses "E-ds cell − scaffold + active card" as the low anchor and the I-ds cell as the high anchor.
- **K5, design-v0 minimum effects.** design-v0's "SearchQA 3–4, LiveMath ~5, SpreadsheetBench ~7, OfficeQA/ALFWorld ~10"
  are not reachable for LiveMath (5 needs 500–606 items, DP §5) and SpreadsheetBench (7 needs 279–338). §2.4 registers
  the MDEs that the available items give.
- **K6, detectors on small benches (A7).** With 24–31 run-slice items, the held-out half has ~12–16 items (24–32
  cells); a detector cannot reach the registered lower bound there. Registered consequence: on OfficeQA and
  SpreadsheetBench, detector acceptance is "not decidable" unless the owner releases more items; mechanical
  categories still run.
- **K7, freshness wording (A1).** Under A1 the SpreadsheetBench 91, OfficeQA 74 and ALFWorld 57 pool items are
  route-B-fresh. They are not fresh in the absolute sense (DP F7–F9: inputs to the v1 baselines, older learners, v3,
  cal-1 and feasibility runs), and the five task cards were written after the development data had been viewed
  (DP §6.2). The registration discloses this; it does not call them "unseen".

## 0 Identity, boundaries, what is frozen

负责人摘要：新协议叫 `fivebench-execskill-v1`，代码放新包 `skillopt/execskill/`，输出放开发机新目录
`/data/execskill-20261021-*`；第 3 版（v3）的代码、记录、分数一律不动。

| item | registered value |
|---|---|
| protocol VERSION | `fivebench-execskill-v1` (every record: cell, unit, registry, test panel, manifest, smoke, chain, report) |
| package | `skillopt/execskill/` (new; outside `skillopt/continual_eval/`, whose `core.source_identity` hashes every file there, core.py:89-102 [SB F42]) |
| CLI | `scripts/run_execskill.py` (copy of the subcommand pattern of scripts/run_coevo5.py:238-311 [LO §3]) |
| tests | `tests/test_execskill_*.py` (offline; written before any paid call) |
| branch | `research/exec-skill-coevolution` (docs/project-status.md:14); must also carry the untracked coevo5 files it imports [MAP B9] |
| dl outputs | snapshot `/data/execskill-20261021-source`, ops `/data/execskill-20261021-ops`, run `/data/execskill-20261021-run`, manifest `/data/execskill-20261021-run-manifest.json`, smoke `/data/execskill-20261021-pre`; tmux `execskill-<unit>` [MAP §2.10]. `/data/execskill-ops/` belongs to the probe; never written [LO F2] |
| interpreter | `/root/continual-alf-prep-20260928/env/bin/python` (3.11.16) with `-B` / `PYTHONDONTWRITEBYTECODE=1` [LO F3, FP F34] |

**Import vs copy (A14).** Import unchanged (protocol-free): `coevo5.{budget, ledger, calls, outcomes, stats, checks,
roles}`, `continual_eval.{backends, code_delivery, sheet_*}`; exception classes `BudgetStop`, `AssumptionBroken`,
`LedgerFailure`, `ConfigurationError`, `CleanupUnconfirmed` are imported from `skillopt.coevo5.outcomes` so that copied
`cells`/`units` map them as one set [MAP §2.0]. Copy with the new VERSION: cells, units, evaluation, qualify, manifest,
prelaunch helpers, smoke, chain, CLI, and the ~100 lines of step.py primitives (`run_round`, `_order`, `table_of`,
`shared_unanswered`, `guard`, `violations`, `key`, `bench_of`, `pool_tasks`) [CI 3.9]. Every identity site that hashes
Skill text hashes the package manifest instead (cells.py:222, evaluation.py:356/366, step.py:825, chain.py:290
[FP F13]).

**Frozen, never edited:** all of `skillopt/coevo5/`, `skillopt/continual_eval/`, `scripts/weak_solver_probe.py`, the
v3 snapshot `dl:/data/coevo5-20261019-v3-source-f`, the v3/cal-1/feasibility run directories, every scorer
(`_score_answer_tag`, env evaluators, v7 sheet chain), the pinned images `sha256:0a0a5dcb…0f0dd` (native) and
`sha256:f7f6f598…c4d790` (recalc) [SF F20, F25].

**Reuse of v3 SpreadsheetBench qualification (owner decision D13, default reuse).** `qualify.load` refuses another
VERSION (qualify.py:134-138 [CI F38]); the copied loader accepts the explicit list `IMPORTABLE = {"fivebench-coevolution-v3"}`
for the 91-item training qualification and the 23-control engine record, after a zero-call re-verification of the
pinned sha256 values (`/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json`; engine
`/root/continual-fivebench-20261003-f-q23/qualification.json`, sha `f5bc90df…6f54c` [SF F20]).

**Isolation rules carried over from v3:** only the evaluation step creates `TestAccess`; test scores are sealed
until the chain ends; no response cache; every cell is a fresh call; write-once artifacts [V6 §0, CI F4].

## 1 Objects

负责人摘要：学到的"Skill"是一个程序包：若干条小程序（过程），每条带一个"适用条件"程序、一段说明、一组回放测试。
任务卡、路由器、格式护栏和"壳"都是固定的，不学。

### 1.1 Procedure (learned)

```json
{
  "id": "p-<bench>-<step>-<n>",                 // assigned by the registrar, never reused
  "home_bench": "spreadsheetbench",
  "hook": "context" | "compute" | "veto",       // exactly one
  "scope": "bench" | "cross",                   // "bench": predicate must test bench == home_bench (statically checked)
  "applies_source": "<python: def applies(view: dict) -> bool>",
  "procedure_source": "<python: def run(inp: dict, state: dict) -> dict>",
  "description": "<= 600 bytes plain text, shown to nobody at solve time",
  "replay_tests": [{"trajectory": "<run-slice cell id>", "property": "<python: def check(out) -> bool>", "claims_fix": true}],
  "provenance": {"step": 1, "engineer_call_sha256": "...", "source_trajectories": ["<cell ids>"]},
  "sha256": "<of the canonical JSON above minus sha256>"
}
```

Hook contracts (enforced by the shell, not by trust):
- `context`: `run` returns `{"note": str}` (UTF-8, ≤ `NOTE_BYTES` = 2,048 B QA / 1,024 B ALFWorld per step). The shell
  places notes in the **user** message as an extra JSON key `"shell_notes": [{"id","note"}]` in package order; the
  system prompt (contract + card) is never touched, so it stays byte-identical across arms.
- `compute`: the procedure contributes a fixed instruction note telling the solver it may write one
  `<compute>EXPR</compute>`; the shell evaluates EXPR with the registered evaluator (§1.5) and makes **at most one**
  extra solver call (A10) whose user message is the first user message plus `{"first_reply": ..., "computed": value |
  "computation_failed:<class>"}`. The second reply is the delivered reply. No compute tag → single call.
- `veto` (ALFWorld only): `run` returns `{"discouraged": [admissible commands], "note": str}`; the shell adds the note
  and marks discouraged commands in the view; it never removes a command and never rewrites the chosen action.
- No hook can alter, append to, or post-process the delivered reply (A5); the scorer sees the solver's own text. This
  is checked by the solver-equivalence test (§9 S-Q1) and by construction (the shell API has no reply-writing path).

### 1.2 Package (the learned Skill)

```json
{"version": "fivebench-execskill-v1-package", "parent_sha256": "...", "step": 2,
 "procedures": ["<procedure sha256>", ...],              // ≤ MAX_PROCEDURES = 12; ordered
 "retired": ["<sha256>", ...], "labels": {"<sha>": "bench" | "cross"},
 "sha256": "..."}
```
Per-request total injected bytes ≤ `MAX_INJECT` = 4,096 B (QA) / 2,048 B per ALFWorld step; overflow → the
lowest-priority (latest) notes are dropped and the drop is logged (`inject_overflow`), identically in every arm.

### 1.3 Task cards (frozen, A5)

The five v3 I-ds seed instructions (`/data/coevo5-20261019-v3-pre/texts/texts.json`, version
`fivebench-coevolution-v3-texts-import`; searchqa 1,846 chars sha `48b10afc…`, officeqa 2,926 `2e92500a…`,
livemath 2,068 `9cb3d860…`, spreadsheetbench 2,907 `48a5df7f…`, alfworld 2,301 `5ae6ea9b…` [CM F52, 2.10b]).
The router shows **only the active bench's card**, as `skill_text` after the frozen line
`"\n\nFrozen skill guidance (use only where applicable):\n"` (backends.py:380; ALFWorld single newline :732). The
whole-Skill render of v3 (all five sections, skill.py:63-74) is not used: E4/E9 measured −9.5 to −33 points on OfficeQA
from other benches' answer-format advice [FP F51-F52].

### 1.4 Format guard (frozen, A5)

Instruction only: the v3 contract sentence per bench, contract-first-v2 layout (SearchQA/OfficeQA "Return the concise
final answer inside <answer>...</answer>."; `LIVEMATH_CONTRACT`; `SHEET_CONTRACT_V2`; ALFWorld "Act in the text
environment. Return a single action inside <action>...</action>.") [SF F15-F16]. Plus the ALFWorld action
canonicaliser of A9 (D3 `parse`/`canonical`, pilot_alf_glm.py:165-195 [FP F7]) applied **in every arm including the
task-card arm**; it maps wrapper forms ("action: X", case) to an admissible command and is logged per step
(`how` ∈ tag/whole/canonical/earliest_admissible/unchanged). No other output transformation exists (A5; answer
repair is not Skill evolution, AGENTS.md).

### 1.5 Shell, router, sandbox worker

- **Router** (fixed code): at item start evaluates every procedure's `applies(view)` on the *public view only* and
  logs `{procedure, fired: bool, fault: null|class}` into the prediction dict (`prediction["router"]`; cells.py:187
  stores the whole prediction by hash [CI G3]). Applicability is decided once per item (ALFWorld: on the initial
  observation and task text); a procedure may still return an empty note at a given step (logged `inactive_step`).
  This makes every enable decision known before dispatch, which the withholding twins (§5.5) require.
- **Shell** (fixed code): copied `backends.solve` (:364-455) and `_solve_alfworld` (:715-783) with the hook points of
  [MAP §1]; with zero enabled procedures it must reproduce frozen `backends.solve` request hashes byte for byte
  (§9 S-Q1).
- **Inputs whitelist** (A3): QA `public` view as the solver sees it; SpreadsheetBench public preview plus the public
  `input.xlsx` bytes; ALFWorld `{initial_observation, observation, admissible_commands, history (full), task}`.
  Never `private`, `infos.extra.expert_plan`, `infos.extra.gamefile`, references, file paths, the ledger [SB F22, CM F10].
  ALFWorld keeps the v3 runtime (`alfworld_split: "train"`, 50 steps, seed 42) because every route-B game is a train
  game; the shell strips `infos.extra` before building any view, and a unit test asserts that no view, note or trace
  field contains the expert plan or the game path.
- **Sandbox worker** (A3): image `evolve-skill-native:smoke-20260928` by digest; `docker run --rm -i --pull=never
  --network=none --read-only --user=65534:65534 --cap-drop=ALL --pids-limit=64 --memory=512m --cpus=1
  --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m` (D3 flags, FP F10); `python -I -B /worker/worker.py`; line-delimited
  JSON on stdin/stdout: `{"op":"load","package":{...}}`, `{"op":"applies","id":..,"view":..}`,
  `{"op":"run","id":..,"input":..,"state":..}` → `{"ok":true,"result":..,"ms":..}` | `{"ok":false,"error_class":..,
  "message":"<=500 B"}`. Limits: predicate 2 s, procedure 5 s wall per request; result ≤ 8 KiB (`RESULT_BYTES`);
  allowed imports `{math, fractions, decimal, re, json, itertools, functools, collections, statistics, string,
  operator, sympy, openpyxl, pandas, numpy}`; banned `{os, sys, subprocess, socket, time, random, pathlib, io (except
  BytesIO for the public workbook), importlib, builtins.open/eval/exec/compile}` by AST check before load and an import
  hook inside. Lifetime: one worker per ALFWorld episode (stateful procedures); for QA/Sheet a pool of long-lived
  workers per (unit, arm) reloaded per package, stateless per request. Worker slots: `execskill-sandbox` = 3
  (registered; 7 CPUs are shared with 6 ALFWorld episodes, 3 native and 1 recalc container [LO §5]); the smoke
  measures container start time (S-X3) and the registration is re-opened if median start > 3 s.
- **Compute evaluator** (A10): `fractions.Fraction` arithmetic over `+ - * / ** ( )`, decimal literals, `%`,
  `round(x, d)`, `min/max/sum/abs`, ≤ 512 chars, exponent ≤ 100, result rendered with up to 12 significant digits;
  anything else → `computation_failed:<class>` (still one second call, so call counts depend only on the first reply).
- **Determinism:** procedures are pure functions of (whitelisted input, own state); a re-execution must reproduce
  identical requests (cells.py:144 [CI G16]); replay runs every procedure twice and compares output hashes.

### 1.6 Placebo twin of a procedure (A10, design-v0 step 6)

For every procedure j in Δ (new in S'), its twin P(j): **same predicate, same hook, same prompt slot, same call
count, no task information**.
- context → note of identical byte length, text drawn deterministically from a frozen irrelevant corpus (the eight
  v3 placebo topics, protocol.py:102-124 [CM F45]) at offset `sha256(unit, item, j) mod len`;
- compute → identical instruction note, so the solver writes the same `<compute>` requests and the shell makes the
  same second call, but `computed` is replaced by the fixed string `"[value withheld]"` padded to the real value's
  length; this isolates the computed information from "a second look";
- veto → identical note length, filler text, nothing discouraged.
The placebo arm P = S ∪ {P(j) : j ∈ Δ} (retirements in S' are not mirrored; §4.4 restricts Δ to additions plus
explicit retirements).

## 2 Data

负责人摘要："没用过"指本路线自己的历史里没用过（一本只能写、不能改的消耗账），以前的基线和老方法用过的要在登记里写明。
每个 bench 的题按一个固定种子排一次序，切成连续的两段：跑题段和验收段，各用一次。测试集只有最后的评测步骤能读。

### 2.1 Freshness rule (A1)

- **Consumption registry** `<run>/shared/consumed/<bench>.jsonl`, append-only, one line per item id
  `{"item", "slice", "unit", "time", "sha256_public"}`, written and fsynced **before** the first cell of that item is
  dispatched; the copied `run_round` refuses an item already present (also across chains of the same root). Smoke and
  pilot use separate roots; items consumed by the pilot are never reused by the full run (owner decision D9, default
  "never reuse").
- **One order per bench:** `order_b = data.ranked(supply_b, DATA_SEED_B, "execskill-v1:order:" + b)` with
  `DATA_SEED_B = 20261021` (data.py:173-176); slices are consecutive: `R_b = order_b[0:n_run]`,
  `A_b = order_b[n_run : n_run + n_acc]`; any later step on the same bench continues from the next unconsumed
  position. Independent tags are forbidden (they overlap by chance: 29/18/60 items, DP F6).
- **Disclosure (K7):** every pool item was an input to the v1 SkillOpt/GEPA baselines; OfficeQA 74, SpreadsheetBench
  91 and ALFWorld 57 were all executed by v1/v3 training and gates; SearchQA 555/600 and LiveMath 142/283 were
  executed by v3, cal-1 or feasibility runs (DP F7-F9). The registration says "never used by route B", never "unseen".

### 2.2 Supplies usable without a release (A1)

| bench | supply registered for route B | provenance / exclusion run (with test access where needed) |
|---|---|---|
| SpreadsheetBench | 91 reference-qualified pool items (58 hist-train + 33 hist-val) | v3 qualification, reused (D13) [DP F5] |
| OfficeQA | 74 pool items | upstream 246 = 50+24+172: nothing else exists [DP F11] |
| LiveMath | 283 pool items (129 contain the "stronger statement" meta option, always the key [FP F44]) | pool() [DP F9] |
| SearchQA | 600 pool items + **new block N** from the 11,380 never-sampled HF `validation` rows | exclusion by id of test 400 ∪ reserve 1,000 ∪ blocks A-D ∪ pool, plus normalized-question dedupe, run by code holding test access; ids only; sealed C/D never opened [DP F14-F16] |
| ALFWorld | 57 pool games + **new games G** from the 3,514 `json_2.1.1/train` games outside the pool | items file `{id: "alf-x:<sha12>", gamefile, task_type}`; test exclusion by game path against the test panel and verification that the test panel is `valid_unseen`, both inside the evaluation code holding `TestAccess`; stratified by the 6 task types; zero-call load check [DP §4.7, SF R9] |

Owner releases (not assumed): LiveMath evaluation blocks e03-e08 (150 unread) (D2); SpreadsheetBench all_data_912
(download, overlap check, two-scoring qualification; yield unknown) (D3).

### 2.3 Per-bench slices (default full-run plan; the pilot uses the rows of its two benches)

| bench | run slice R (items × runs, parent arm only) | acceptance slice A (items × runs × 4 arms) | generated set G (frozen, × 1 run × 4 arms) | left after the step |
|---|---|---|---|---|
| SpreadsheetBench | 26 × 2 (31 minus the smoke's 5, §9) | 60 × 2 | ≤ 120 (only if the generator passes §6.2; else none) | 0 |
| OfficeQA | 19 × 2 (24 minus the smoke's 5, §9) | 50 × 4 | ≤ 120 | 0 |
| LiveMath | 83 × 2 | 200 × 2 | ≤ 120 | 0 (283 used) |
| SearchQA | 300 × 1 (pool) | 1,000 × 1 (block N) | none (no program truth; paraphrase probes descriptive only) | 300 pool + 10,380 HF rows |
| ALFWorld | 100 × 1 | 200 × 1 | 40 games chosen by the selector (§6.2) from games outside the supply | ~3,000 unregistered games |

ALFWorld supply = the 57 pool games ∪ D_alf, a registered draw of 600 games from the 3,514 outside the pool (seed `DATA_SEED_B`, 100 per task type, after the test exclusion); R and A are cut from one order over these 657. The selector of §6.2 draws only from the remaining ~2,914 train games, so generated (selected) games never overlap R or A.

Why these splits (measurement first): item variance dominates run variance (D1: "more items, not more runs, buy power",
FP F40), so the acceptance slice gets the larger share wherever the run slice still yields ≥ ~30 failing cells for
the engineer (card-arm pass rates: OfficeQA ~0.25-0.29 [DR §5 step 1], ALFWorld ~0.5 [FP F15]). Runs per item are
raised only where items are scarce (OfficeQA 4, SpreadsheetBench and LiveMath 2), as in v3 (`GATE_RUNS`, DP F1).

### 2.4 Minimal detectable effects at these sizes (E; `mde.py`)

Paired item-mean difference, Var = τ² + s²/k with s² = same-text single-run disagreement and τ = between-arm item
spread 0.12-0.28 (D1, FP F40). s² inputs: SearchQA 0.049-0.104 (cal-1 card vs scaffold, FP F45); ALFWorld 0.14 (8/57,
FP F15); OfficeQA 0.08-0.12, LiveMath 0.10-0.14, SpreadsheetBench 0.10-0.16 (assumed so that 1-run discordance matches
DP F17's implied π). One-sided α = 0.05 (the decision is directional), power 0.8:

| bench | acceptance | MDE, points (E) | D1 anchor at pool sizes (M-derived, FP F40) |
|---|---|---|---|
| SearchQA | 1,000 × 1 | **2.0-3.4** (two-sided 2.2-3.8) | 4.2 at 300 × 2 |
| LiveMath | 200 × 2 | **4.5-6.8** | 5.6 at 233 × 2 |
| ALFWorld | 200 × 1 | **6.9-8.2** (150: 8.0-9.5; 300: 5.6-6.7) | 15.3 at 29 × 2 |
| OfficeQA | 50 × 4 | **6.5-11.6** (37 × 4: 7.6-13.5) | 10.3 at 37 × 4 |
| SpreadsheetBench | 60 × 2 | **8.1-12.8** (46 × 2: 9.3-14.6) | 12.2 at 46 × 2 |

Not included: drift of run noise between windows (2-3× on discordance, DP F17) — interleaving (§5.2) is what makes the
numbers apply; the second-order δ² term. Holm is **not** applied (§5.3 explains the intersection-union rule).

### 2.5 Test sets (read only by the evaluation step)

Canonical fivebench-split-v2 test parts: SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 279 (scored on
its test-side reference-qualified subset, qualification run inside evaluation), ALFWorld 134 (`TEST_SIZES`,
protocol.py:65 [DP F1]). History disclosed: SearchQA test read 10/6 and 10/8; SpreadsheetBench and ALFWorld 10/6;
all five were evaluated by v1 (scores opened 10/19) and by v3 (computed, sealed) [DR §4 留; docs/project-status.md 10/19 10:52 entry]. Only the copied
evaluation creates `TestAccess`; consent file wording is new (§7.6); scores sealed until the chain (pilot) completes.

## 3 Roles

负责人摘要：五个角色。做题模型（deepseek 新接口，关掉推理）只做题；工程师和考官是 GLM-5.3，只读跑题段的记录；
裁判和登记员是固定代码，验收结果只把"收/不收"一个字告诉方法角色。

### 3.1 Solver — `deepseek-v4.1-flash-1017`, client identity `elucid` (A4)

- Client: subclass of `weak_solver_probe.Client` that does not call `super().__init__` (which refuses models outside
  `MODELS`, weak_solver_probe.py:232-233); `backend = "elucid"`; URL/key read by path from
  `/root/.config/weak-solver/elucid.env` (`ELUCID_CHAT_URL`, `ELUCID_API_KEY`, `ELUCID_MODEL`; never printed) with the
  `_read_env`/`_validated_url` pattern (:115-137); `thinking = None`; request adds `"reasoning_effort": "none"`;
  `response_model_ids = {"deepseek-v4.1-flash-1017"}` (echoed id, M: probe logs); `trust_env=False`; proxy = the
  approved PJLAB gateway `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128` (the probes reached the host
  through environment proxies; direct egress untested [LO F15]); temperature 0; single-turn `[system, user]`.
- Registered settings: `max_tokens` QA 8,192 / SpreadsheetBench 16,384 / ALFWorld step 1,024 (D3 ran 512 per step,
  FP F4); completion bound for the ledger `COMPLETION_BOUND = 2 × max_tokens`; read timeout 600 s (the 2,400 s of v3
  turned a stall into a 40-50 min unit [LO F37]; 600 s exceeds 1.8× the time of a 16k-token reply at ≥ 50 tok/s — E);
  client attempts ≤ 4 (ledger assumption, CI F10); slots `elucid-solver` = 8 (8/8 delivered in 3.5-4.3 s, M probe-2 log);
  Recorder resends ≤ 2 with cooldown 60 s (v3 used 300 s).
- Per-receipt verification: `reasoning_tokens in (None, 0)` and empty/absent `reasoning_content`, else
  `reasoning_mismatch` (undelivered → resend → infrastructure unknown, like v3's `thinking_mismatch`, outcomes.py:66-67);
  echoed model must match; `completion_tokens − (reasoning_tokens or 0) ≥ max_tokens` or `finish_reason ∈ {length,
  max_tokens}` → truncated (completion-aware fail); `max_tokens < completion ≤ COMPLETION_BOUND` → flag
  `over_nominal`, counted, delivered; `completion > COMPLETION_BOUND` → `AssumptionBroken` (global halt), as is
  `prompt > request_bytes + 512` (ledger.py:67). Usage of every attempt is kept (the frozen ledger keeps only the last
  attempt's usage, so its total is a lower bound [LO F9]; the copied settle logs all attempts' reported usage).
- Fallback: none for the model; infrastructure unknowns follow §4.9's rows.

### 3.2 Engineer — GLM-5.3 (role `engineer`), writes procedures

- Settings as v3 roles: temperature 0, reasoning low, `ROLE_MAX_TOKENS` 16,384, read timeout 900 s, input ≤ 220,000 B
  (protocol.py:30-32, :245 [CM F1-F5]).
- Input (JSON): bench card; shell/hook API spec (frozen text); current package sources; mechanical flags and accepted-
  detector categories with counts on R; up to 40 failing and 10 passing R trajectories (seeded selection, truncated per
  trajectory to 6,000 B), each with pass/fail bit and, for QA, the reference answer (training labels are allowed for
  the method side; references never enter procedure code, §4.4 leakage check).
- Output schema (one JSON object, `roles.Roles.ask` contract [CM F2]):
  `{"procedures": [{"hook","scope","applies_source","procedure_source","description","replay_tests":[...],
  "claims":[cell ids]}], "retire": [procedure ids], "notes": "<= 1,000 B"}`; ≤ 3 procedures per step; sources ≤ 12 KB
  each. Code travels as JSON strings; the validator also accepts one fenced ```python block per procedure keyed by
  index (to survive escaping faults: 21/49 v3 proposals died of small format faults [CM §5.2]).
- Ceilings: ≤ 2 proposal calls (2nd only after an invalid reply; `ANALYST_ATTEMPTS = 2`), ≤ 1 "fix or drop" call per
  failing procedure (`SELFTEST_SYSTEM` pattern, step.py:405-443), ≤ 1 leakage adjudication per procedure; per-step
  GLM ceiling 1.5M tokens. Fallback: two invalid replies → `method_failure`, no candidate, the step ends with S.

### 3.3 Examiner — GLM-5.3 (role `examiner`), writes detectors and generators

- Input: W-half trajectories of R (§6.1) with pass/fail bits and mechanical flags, **no references**; the current
  detector library with its validation record; the bench card; for generators, the item public views of R (own
  content only) and the generator API.
- Output: `{"detectors": [{"category","predicate_source","rationale"}]}` (≤ 3 per step) and
  `{"generator": {"bench","source","params"}}` (≤ 1 new or revised per step).
- Ceilings: detectors ≤ 2 calls; generator ≤ 2 calls to write + generation runs bounded by the item cap; generated-
  item checks per §6.2; per-step GLM ceiling 2.5M tokens. Fallback: invalid → nothing new this step (library kept).

### 3.4 Judge — fixed code (A2)

- `official` = frozen `backends.score` + `outcomes.classify` exactly as v3 (cells.py:221-230) [SF F13-F14].
- `v2` = new module `skillopt/execskill/scorer_v2.py` (VERSION `execskill-scorer-v2`): verdict = official pass OR
  JSON-extracted pass (QA: no tag → last JSON object, also inside a ```json fence, with key "answer" whose value is a
  string or number, JSON-unescaped; compared with the frozen comparison of that bench); SpreadsheetBench/ALFWorld
  v2 = official, recorded explicitly. Unit-test invariant: v2 ≥ official on every cell [SF 3b.2].
- **Decision metric = v2, completion-aware** (truncation, filter, empty, malformed action, undeliverable code = fail).
  Also recorded per cell: official, official-completion-aware, raw-reply score (= v2 on the solver's own reply; under
  A5 the delivered reply *is* the raw reply), `lenient` (descriptive), format flags (§7.5 list from SF 3b.4), and
  `numeric_equal_but_em_fail` for OfficeQA.
- Generated items are judged by the same comparison as real items of that bench (SF 3b.5).

### 3.5 Registrar — fixed code

Owns: the consumption registry; seeded interleaved dispatch; withholding-twin scheduling; the ledger and caps; the
statistics of §5-§7; the sealed decision record per step. It returns to the method roles only the accept/reject bit
and the per-category failure counts of R (never acceptance-slice outcomes) [FP F41 rule].

## 4 One step on bench b (parent package S)

负责人摘要：八个小步，前五步只用跑题段和生成题，第六步才碰验收段，而且只碰一次。

Each sub-step is a unit (`units.run_unit` pattern: lock, attempt-N, write-once `unit.json`); a pause never resumes by
itself [V6 §13.4].

**4.1 Run.** S on R_b (§2.3), one arm, cells in seeded order. Record per cell: v2/official verdicts, router log,
per-step trace (ALFWorld: view, raw reply, canonicaliser `how`, admissible commands, procedure notes, vetoes; the
frozen trace lacks these, SB F24), all receipts. Guard: infrastructure-unknown share > 10% → pause (v3 rule).

**4.2 Diagnose (examiner, part 1).** (a) Mechanical categories, fixed code, all benches: `no_answer_tag`,
`json_answer`, `multiple_answers`, `formula_only_reply`, `program_missing`, `fence_glued`, `truncated`,
`step_budget_exhausted` (ALFWorld 50 steps), `revisit_count ≥ 3` (a "go to X" where X was already reached and nothing
changed), `inadmissible_action`, `nothing_happens ≥ 5`. (b) Accepted detectors from the library run on all R cells.
(c) The examiner writes ≤ 3 new detectors from the W half (§6.1); they are validated on the V half before the
engineer sees their counts. The engineer receives: counts per category on R, and for each failing trajectory the
categories that fired.

**4.3 Generate (examiner, part 2).** Per §6.2; the frozen set G_b and its gate record exist before 4.4 starts
(SearchQA: none).

**4.4 Engineer.** Proposal per §3.2; then, per procedure, in order (first failure → one fix-or-drop call → re-check
once → drop):
1. static: AST import/builtin whitelist, sizes, `scope == "bench"` ⇒ `applies` contains an explicit bench test;
2. leakage: `leakage.mechanical` + AST literal/regex/dict-key extraction against the R references and test-free
   corpora; a hit → `leak_adjudicate` (one call); veto → drop [CM F48-F50];
3. replay on **all** R trajectories (and all public views of G_b): zero crashes, zero timeouts, outputs within caps,
   determinism (two executions, identical hashes); for each `claims` trajectory the stated property holds;
4. guard: the procedure's notes are inserted only via the shell API (structural); no output on any R view contains an
   answer tag, an `<action>` tag or a code fence (mechanical check, so a note cannot dictate the reply format).
Δ = surviving new procedures (+ registered retirements, only of procedures whose home bench is b). S' = S − retire + Δ.
If Δ is empty and nothing is retired, the step ends with S (no acceptance round; A_b stays unconsumed and is
recorded as such).

**4.5 Self-test (sieve, never acceptance).** All four arms (S', S, C, P) on G_b × 1 run (needed for §6.3), plus S' and
S on each earlier bench's frozen G (≤ 60 items; ALFWorld ≤ 20 games). The sieve may stop a candidate only for:
(a) procedure_fault share > 2% of S' cells on G_b ∪ R-replay; (b) a format regression on an earlier bench's G: the
share of cells with the bench's required format (`REQUIRED_FORMAT` checks; ALFWorld admissible-action share) lower for
S' than S by ≥ 5 points with sign-test p < 0.05; (c) S' − S on G_b with one-sided 95% upper bound < −5 points, **only
if** that generator's status is `validated` (§6.3). In the pilot no generator can be `validated` at its own step, so
(c) cannot fire there. A stopped candidate leaves A_b unconsumed.

**4.6 Accept.** §5: four arms + withholding twins, one interleaved round on A_b, one decision.

**4.7 Freeze and pass on.** Accepted: package S' sealed (sha256), each new procedure labelled by its static `scope`
("bench" or "cross"); the causal labels "general" / "this bench only" are assigned only by §7.3 from test-read
withholding evidence, never used for decisions. Rejected: S passes on unchanged; Δ is archived (it may be re-proposed
on a later bench only as a new procedure with a new id).

**4.8 Test read.** Pilot: once, after the last step (§7). Full run: owner decision D6.

**4.9 Decision-table rows added to the copied `outcomes` (A6).** Inserted before v3 row 11 ("unclassified"):

| row | situation | completion-aware outcome | remedy |
|---|---|---|---|
| P1 | predicate raises, times out or returns non-bool | procedure treated as not fired; `predicate_fault` logged | none; cell continues |
| P2 | procedure raises, times out, exceeds caps or returns a malformed result | cell continues **without** that procedure (fail-open to parent behaviour); `procedure_fault` logged | none |
| P3 | compute expression invalid/unsafe/over limits | second call carries `computation_failed:<class>`; `compute_fallback` logged | none |
| P4 | sandbox infrastructure failure (docker/image unavailable, worker start failure not caused by the procedure) | re-execute the cell's shell from the recorded receipts ≤ 2; still failing → unknown (infrastructure) | REEXECUTE |
| P5 | `reasoning_mismatch` on the last receipt | undelivered → v3 row 4 resend; exhausted → unknown (infrastructure) | resend |
| P6 | `over_nominal` (max_tokens < completion ≤ bound) | as the delivered reply scores; flag counted | none |
Faults never become infrastructure unknowns. Acceptance guard G1 (§5.4) rejects a candidate whose P1+P2 share in the
S' arm exceeds 2% of cells. Worker-killed-by-limit (memory, pids, wall) is P2, not P4.

## 5 Acceptance statistics (one decision per fresh batch)

负责人摘要：四组同时段、逐题打乱顺序发送。新包要同时比旧包好、比安慰剂好，两个比较各自用 5% 的单侧检验；因为两条都要成立
才收，不需要再做多重校正。这批题只做这一次决定。

### 5.1 Arms

| arm | content | role |
|---|---|---|
| S' | candidate package (S − retired + Δ) + card + guard | judged |
| S | parent package + card + guard | comparator 1 (decision contrast) |
| P | S ∪ placebo twins P(j), j ∈ Δ (§1.6) | comparator 2 (rules out "any extra note / second call helps") |
| C | card + guard, no procedures (QA/Sheet: frozen `backends.solve` with the v3 runtime and the active card as Skill text, reproducing v3 prompts byte for byte [SB U2]; ALFWorld: the new loop with zero procedures and the canonicaliser) | reference for the package-over-card reading; at step 1 a same-text duplicate of S (K3) |
| twins | S' ∖ {j} on randomly chosen enabled items (§5.5) | per-procedure attribution, descriptive |

### 5.2 Interleaving (same session)

All cells of the round — 4 arms × |A_b| items × k runs plus twins — are put in one seeded order
`_order(jobs, "execskill-v1:accept:" + unit)` and dispatched by one pool with shared slots (the cal-1/D1 pattern,
step.py:105-121 [CM F42, FP F39]). Each cell sends its own request; no cache. Recorded per cell: dispatch and finish
time. Reported per arm and 15-minute bin: share of terse replies, answer-format share, reply length (D11 measured
terse share 5-96% per bin, FP F45). ALFWorld: episode-level interleaving across 6 episode slots.

### 5.3 Decision rule (registered)

Per item i: d_i(X, Y) = mean over runs of L(X, i, r) − mean over runs of H(Y, i, r), where L counts unknown as fail
and H counts unknown as pass (v3 `stats.bounds` [CM F38]); items unanswered in every arm are excluded
(`shared_unanswered`, step.py:139-147). Test per contrast: one-sided paired **sign-flip permutation test** on the
d_i (100,000 Monte Carlo flips, seed 20261021 + step), H0: the distribution of d_i is symmetric about 0 (true under
identical arms with interleaving). Reported with it: mean, item-bootstrap 95% CI (10,000 resamples), up/down/tie
counts, exact sign-test p.

**ACCEPT S' iff** p(S' > S) ≤ 0.05 **and** p(S' > P) ≤ 0.05 **and** guards G1-G5 hold. Otherwise REJECT (S stays).

Why no Holm: acceptance needs *both* contrasts, which is an intersection-union test; its probability of accepting
when S' is not better than S is ≤ 0.05 without adjustment [mem: Berger 1982, not re-checked]. The price is power:
joint power ≈ power(S' vs S) × P(S' vs P passes | ...); if the placebo itself helps (a "second look" effect), the
second contrast loses power — which is exactly the claim it is there to protect. S' − C is reported, not tested for
the decision.

### 5.4 Guards

- **G1** P1+P2 fault share in S' ≤ 2% of S' cells (A6).
- **G2** infrastructure-unknown share ≤ 10% in every arm (else pause, v3 rule [V6 §5.4]); S' unknown share (any kind)
  ≤ 10% (else "undecided" = reject).
- **G3** format: violations of the bench's required format (QA answer tag; LiveMath single letter; Sheet program
  delivered; ALFWorld admissible-action share per episode < 0.9 counts as a violation) in S' exceed those in S by
  ≤ max(2 cells, 2% of cells) (v3 C3 pattern).
- **G4** reasoning mismatches after resends ≤ 1% of cells in every arm; else pause (instrument problem, not a verdict).
- **G5** step 1 only (S ≡ C): two-sided sign-flip p(S vs C) < 0.01 → pause, decision withheld, owner informed
  (interleaving or determinism broken). The same check is computed at later steps between C and a C-duplicate only if
  the owner buys the optional duplicate arm (D10).

### 5.5 Random withholding in acceptance (A11, descriptive)

For each item i, E_i = procedures of Δ whose predicate fired for S' on i (known before dispatch, §1.5). With
probability w_acc = 0.5 (hash of `(seed, unit, i)`), one twin S' ∖ {j}, j drawn uniformly from E_i (seeded), is added
to the round with the same k. Estimate per j: mean of S' − (S' ∖ j) over its twin items, with bootstrap CI (E). Never
used for the decision, for pruning, or shown to any role. Expected twins ≈ 0.5 × share of items with a fired new
procedure (E: 0.6) × |A_b| ≈ 0.3 × |A_b| (cost in §8).

### 5.6 What one decision can and cannot say

- Power at the §2.4 MDE ≈ 0.8 for S' − S alone (E). A rejection means "no effect ≥ MDE was established", never
  "the procedures do not help".
- False accept ≤ 5% per step (IUT bound); over the five steps of a full chain the expected number of false accepts
  under a global null is ≤ 0.25 (E). Reported.
- The batch is consumed whether the candidate is accepted or rejected; no candidate is re-tested on it; no procedure
  is pruned on it (pruning on the acceptance batch would be selection on the decision data).
- Known instrument facts the readout must carry: placebos are not inert (cal-1: −9.8 to +3.6 points, mostly the JSON
  artefact that v2 now scores [CM F47, FP F43]); same-text items flip 8-10% between runs [DR §2.4]; OfficeQA moves
  20+ points between serving windows (M: SD 11.4 over 4 windows of 60 items [DR §2.4]) — interleaving protects the
  contrast, not the absolute level, so absolute accuracies are labelled "this window only".

### 5.7 Stopping and abandon rules (registered)

- **ST1 smoke:** any failed §9 criterion → no pilot cell until the registration is amended (sub-version
  `fivebench-execskill-v1.1`, new directories) and the failed checks are re-run.
- **ST2 pause:** G2/G4/G5, budget stop, `AssumptionBroken`, cleanup unconfirmed, configuration error → pause; nothing
  resumes automatically; the owner chooses (a) terminate or (b) redo the paused unit whole in a new attempt
  directory; decisions use infrastructure information only, never scores [V6 §13.4].
- **ST3 no candidate:** two invalid engineer replies, or every procedure dropped in §4.4/§4.5 → the step ends with S,
  A_b stays unconsumed. Two consecutive benches without a surviving candidate → pause for owner review.
- **ST4 nothing accepted in the pilot:** F ≡ S0 ≡ C, so the test read would compare identical arms; it is **not run**
  (the one-time test consent is not spent); the learning-side record is reported.
- **ST5 continuation:** the pilot is steps 1-2 of the chain (owner decision 9). The remaining steps run only after an
  owner decision taken on the pilot report; the default recommendation is "continue only if ≥ 1 package was accepted
  with all guards intact"; otherwise write up the measurement and negative result [DR §3 路线 A 乙路].
- **ST6 supply:** a step whose registered slice exceeds the unconsumed supply is skipped ("supply exhausted"); items
  are never reused.
- **ST7 caps:** reaching the pilot cap pauses (ST2); a raised cap is a recorded deviation.

## 6 Examiner evolution

负责人摘要：考官一侧"被收下"只有两种：检测器在没见过的轨迹上查得准、查得到；出题程序过了真值、难度、捷径三关
叫"准入"，再在真题上至少两次把方向说对才叫"验证通过"。只靠模型判断的标签永远不算证据。

### 6.1 Detectors (A7)

- Split: R's items are split by `ranked(R, DATA_SEED_B, "execskill-v1:wv:" + b)` into W (first half) and V (second),
  stratified by the item's S pass pattern (all-pass / mixed / all-fail). The examiner sees W only; V outcomes are
  never shown to any role.
- A detector is `def fires(trajectory) -> bool` over the whitelisted trajectory (no reference, no private data,
  enforced by the worker input). Ground truth = the anchored pass/fail bit only.
- On V: b = fail share; F = fired cells; precision p = fails in F / |F|; recall r = fails in F / fails.
  **Accept iff** |F| ≥ 10 cells from ≥ 6 items, and the one-sided 90% item-cluster-bootstrap lower bound of
  (p − b) ≥ 0.10, and r ≥ 0.15. Accepted detectors join the bench library; on a later step of the same bench they are
  re-validated on the new V and retired after two failures.
- Mechanical categories (§4.2a) are instrumentation, unit-tested, never "examiner evolution".
- Decidability (E): |V| cells = SearchQA 150, LiveMath 84, ALFWorld 50, SpreadsheetBench ~26, OfficeQA ~19. On the
  last two, a detector with true p − b = 0.25 reaches the bound only rarely; the readout says "not decidable" there.

### 6.2 Generators: admission gates (A8)

Per bench: SpreadsheetBench — perturb the input values of an R item whose reference answer cells are formulas; truth =
LibreOffice recalculation of the perturbed reference (recalc image), then the two-scoring reference qualification
[SF F24, R5]. OfficeQA — the generator code extracts the numbers an R question uses from the item's own page text,
writes a formula that must reproduce the item's original reference exactly from the original numbers, perturbs the
numbers, recomputes with `forward.evaluate` exact arithmetic and states the rounding [SF F27-F28]. LiveMath — D6-style
symbolic variants of R items (sympy in the image, 50-digit numeric validation, no unevaluated integrals/series)
[FP F26-F27]. ALFWorld — a **selector** (code over the public initial observation and task type) that picks unused
train games aimed at the most frequent failure category of R; truth = simulator `won` [SF R9]. SearchQA — none.

A generated set is **admitted** only if all four gates pass (drop counts recorded per reason, forward.py DROPS pattern):
- **T truth:** program/simulator truth; for OfficeQA/LiveMath an independent program (a separate role call that never
  sees the first program) agrees exactly, and the independent program is always one of the agreeing pair (D6 critic
  fix, FP F27); OfficeQA/Sheet: the original-reference reproduction check passes; Sheet: qualification passes.
- **D band:** the parent S solves a 30-item probe of G (1 run) with pass rate in [0.20, 0.80]; ≤ 2 parameter
  adjustments, each re-probed on newly generated items; otherwise "saturated"/"too hard" and G_b is not used.
  (No style ever reached this band before: E9 0.891, D6 OfficeQA-style 14/14 [FP K4].)
- **S shortcut:** LiveMath options-only (stem masked) by the C arm, 2 runs: items passed both times are dropped; the
  generator is rejected if the set's options-only accuracy has a one-sided 95% lower bound > 0.30 (chance 0.20).
  OfficeQA/Sheet blind check (page/table removed): items passed blind are dropped; reject if the blind pass rate > 10%.
- **L labels:** the generator may use only the source item's own content and program truth. Banned: training-label
  regularities (LiveMath generated items contain no "stronger statement" meta option at all; key letters balanced,
  each 20% ± 5%) [FP F31, F44].
Target size after gates: 120 items (ALFWorld 40 games); generation stops at the GLM ceiling.

### 6.3 Predictive validity (the examiner's headline metric)

- G_b is solved by S', S, P, C (step 4.5) **before** the real round, so it is a genuine prediction.
- Registered contrast order: (S'−S), (S'−P), (S'−C), (S−C), (P−S), (P−C).
- A contrast is **informative** iff on the real batch its two-sided 90% item-bootstrap CI excludes 0 and
  |d_real| ≥ 0.5 × MDE_b (low end of §2.4).
- Classification on G_b: AGREE = same sign and the one-sided 90% bound excludes 0 in that direction; OPPOSE =
  bound excludes 0 in the opposite direction; SILENT = otherwise (E9's miss of a real −9.5 harm is a SILENT case).
- Status: `admitted` → `validated` after ≥ 2 AGREE and 0 OPPOSE; `retired` after two consecutive informative
  comparisons that are not AGREE (A8). Also reported: d_gen / d_real (E9 measured 0.23-0.54 [FP F52]).
- What cannot be measured: with one step per bench, a generator gets at most six correlated comparisons from one
  round, and most contrasts will not be informative at the §2.4 MDEs. "Untested" is a registered outcome.

### 6.4 What "examiner accepted" means

Per step: `detectors_accepted` (§6.1), `generator_admitted` (§6.2), `generator_validated` (§6.3). The examiner side
"evolved" in a step iff a detector was accepted or a generator was validated; "admitted only" is reported as
engineering, not as evolution. Coupling: the engineer receives accepted detectors' categories and counts; the
generator targets the top category; neither role ever sees A_b outcomes.

## 7 Transfer and test readout

负责人摘要：试点最后读一次五个测试集，同时段交错跑五组：最终包、只有任务卡、安慰剂、"只有文字说明不带代码"、以及
"逐条拿掉"的对照。学过的 bench 看"有没有提高"，相似的只描述，不相似的合并做"不比任务卡差太多"的检验。

### 7.1 Arms of the test read (multi-arm unit, A12)

F (final package), C (card only), P_F (card + placebo twins of every procedure in F), T_F (**text twin**: card + the
procedures' descriptions as one `shell_notes` block on every item, no code executed — the direct code-vs-text
comparator, see §7.4), and withholding twins F ∖ {j} with **w_test = 1** (every enabled procedure on every item; if more
than 3 are enabled, a seeded random 3). All cells of all five benches' arms in one seeded order per bench unit,
benches as parallel child processes (chain.py pattern [CI §4]).

### 7.2 Registered readouts (pilot)

Learned set L (the pilot's two benches). Similar = benches similar to some member of L by the 10/17 table
(SearchQA–OfficeQA, OfficeQA–LiveMath, OfficeQA–SpreadsheetBench; ALFWorld none [V6 §1.1]); dissimilar = the rest.
- **Q1 home:** for each b ∈ L, F − C on b's test set, one-sided 95% sign-flip test, Holm over |L| = 2.
- **Q2 similar:** descriptive only (estimate, 95% CI, per-procedure twins, enable rates). Test MDEs at 1 run are
  6.6-7.7 (OfficeQA), 10-11 (LiveMath) points [DP F17], so "similar also rises" cannot be certified.
- **Q3 dissimilar, pooled non-inferiority:** equal-weight mean over dissimilar benches of (F − C); one-sided 95% lower
  bound > −Δ_NI. Δ_NI registered as the margin giving 80% power at a true difference of 0 (E, `mde.py`):
  pilot SB→OQ (dissimilar = {ALFWorld}): **Δ_NI = 10 points** (needs 9.5); pilot SB→ALF (dissimilar = {SearchQA,
  LiveMath}): **6**; pilot ALF+SQ (dissimilar = {LiveMath, SpreadsheetBench}): **7**. Missing data by the v6 direction
  rule (favourable claims need complete-case and unfavourable-imputation both to hold [V6 §12.6]).
- F − P_F and F − T_F per bench: descriptive with CIs.

### 7.3 Per-procedure attribution (A11)

For procedure j and bench b with ≥ 10 fired test items: effect_jb = mean over fired items of F − (F ∖ j), bootstrap
95% CI; enable rate from the router (observational, always printed next to the causal estimate). Labels (readout
only): **general** = 95% LB > 0 on ≥ 1 non-home bench and no bench with 95% UB < 0; **this bench only** = LB > 0 on
home and on no other bench; **harmful elsewhere** = UB < 0 on some non-home bench; else **undetermined**. Per-
procedure MDE (E): 19 / 14 / 10 / 7 points at 25 / 50 / 100 / 200 fired items, so most labels will be
"undetermined"; the table says so.

### 7.4 Pre-stated risk: code transfers worse than text

Expected before any run: code-form procedures help mainly on their home bench; transfer outside the table/number
cluster ≈ 0 (Break It Down: text > code for transfer; GRASP: gate gains in-domain only [RW §0.3, §2]). The readout
reports, per non-home bench: F − T_F (does the code add over its own description?), F − C, and the share of "cross"
procedures that fired. If T_F ≥ F outside the home bench, the report states "text form transferred at least as well
as code form" and does not claim code transfer.

### 7.5 Reported with every accuracy

Per arm and bench: v2 completion-aware (primary), official, official completion-aware, lenient; unknown counts by
kind; truncation, `over_nominal`, `reasoning_mismatch`; format flags (tag present, tag count, JSON answer, boxed, bare
letter, last-line fallback, single answer, program delivered, formula-only, fence glued, admissible-action share);
procedure faults; enable rates; per-15-minute terse share. Absolute levels carry "this serving window only".

### 7.6 Consent

New `consent.json` keys: `{test_evaluation, sheet_test_qualification, alfworld_test_identity_check, multi_arm_arms:
["F","C","P_F","T_F","twins"], by: "owner", date, note}` with the owner's own words; evaluation refuses any other key
set (evaluation.py:43, 152-159 pattern [CI F23]).

## 8 Budgets

负责人摘要：默认试点（SpreadsheetBench → OfficeQA，最后读一次测试集）做题约 5,000 万–8,900 万 token，GLM 约 300–800 万；
建议的替代试点（SpreadsheetBench → ALFWorld）约 7,900 万–1.33 亿（已按 150 局验收、ALFWorld 测试不做文字对照压缩）。
测试集一次读取约 3,800 万–6,600 万，ALFWorld 占 55–64%。上限按账本计、不自动续跑。

### 8.1 Per-cell anchors (solver tokens, prompt + completion)

| bench | low (E: E-ds cell − 141 scaffold tokens + active card at 4.2 B/token) | high (M-anchored) |
|---|---|---|
| SearchQA | 1,535 (E-ds 1,236, FP F32) | 3,400 (cal-1 ledger per cell, FP F61) |
| OfficeQA | 5,246 (E-ds 4,690) | 7,927 (I-ds, FP F32) |
| LiveMath | 1,602 (E-ds 1,251) | 3,969 (I-ds) |
| SpreadsheetBench | 2,561 (E-ds 2,010) | 4,273 (I-ds) |
| ALFWorld, per episode | 36,000 (30 steps × 1,214: E-ds 807/step − 141 + 548 card, FP F17) | 45,000 (35 steps × ~1,290) |

Procedure arms (S', P, twins) × 1.25 (low) / × 1.6 (high) for notes and second compute calls (E; D3 measured
1,225 vs 873 tokens per ALFWorld call with a state block, FP F2). The new model's completion lengths are unknown: the
smoke (S-E6) replaces these anchors before the pilot; caps below are re-registered (before any pilot cell) if the
smoke's per-cell mean exceeds the high anchor by > 25%.

### 8.2 Per step (solver, E, from `cost2.py`; parent with inherited procedures from step 2 on)

| step (bench) | run slice | acceptance (4 arms + twins) | self-test (4 arms on G + sieve) | step total low-high | registered step cap (ledger) |
|---|---|---|---|---|---|
| SpreadsheetBench | 0.16-0.26M | 1.5-2.9M | 1.4-2.7M | 3.0-5.8M | 8M |
| OfficeQA | 0.31-0.61M | 5.4-10.0M | 3.4-6.3M | 9.1-16.9M | 22M |
| LiveMath | 0.33-1.05M | 3.3-10.0M | 2.1-5.1M | 5.7-16.1M | 21M |
| SearchQA | 0.58-1.63M | 7.9-21.4M | 2.3-5.5M | 10.7-28.5M | 37M |
| ALFWorld | 4.5-7.2M | 36.9-56.5M | 8.5-14.2M | 49.9-77.9M | 102M |

GLM roles per step: engineer ≤ 1.5M, examiner ≤ 2.5M (incl. generation and independent checks; D6 measured 2,585
GLM tokens per valid LiveMath item, FP F32), adjudication ≤ 0.2M → step cap 4M. Per-role call ceilings in §3.

### 8.3 Test read (one multi-arm read: C, F, P_F, T_F, twins)

| | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | total |
|---|---|---|---|---|---|---|
| E, low-high (default pilot: twins w = 1 on SB, OQ) | 3.1-8.2M | 5.3-9.7M | 1.0-3.0M | 4.2-8.5M | 24.2-36.4M | **38-66M** |
Registered cap per read: 86M. (The map's 56.7M per read assumed three arms with the whole five-card Skill, K4.)

### 8.4 Pilot totals and caps

| pilot | learning (solver) | test read | total solver (E) | GLM (E) | registered caps |
|---|---|---|---|---|---|
| **default** SB → OQ | 12-23M | 38-66M | **50-89M** | 3-8M | solver **120M** (A13's 100M covers only the expected case); GLM 30M incl. smoke |
| alternative SB → ALF (ALF acceptance 150, no T_F on ALFWorld) | 44-70M | 36-63M | **79-133M** | 3-8M | solver 175M; GLM 30M |
| alternative SQ → ALF (same reductions) | 51-91M | 36-63M | **86-154M** | 3-8M | solver 200M; GLM 30M |

Full chain, test read once at the end: 116-211M solver (E); test read every step: 5 reads, 270-475M (E).
Ledger rules: reservation 4 × (request bytes + 512 + max_tokens) per call (ledger.py:26-36); halt on completion >
2 × max_tokens or prompt > bytes + 512 (A4); caps are ledger caps assuming ledger/actual ≤ 1.3 (S-E6 measures it;
cal-1's 27.5M ledger vs ~14M actual came from upper-bound charging at max_tokens 32,768 [DR §4 改]). Budget stop →
pause; no automatic resume; a raised cap is a recorded deviation [V6 §13.4].

## 9 Smoke test specification

负责人摘要：先做不花钱的检查（代码一致、沙盒关得住、评分器 v2 只升不降），再用新接口做很小的付费检查（推理确实关掉、
并发 8 路、max_tokens 到底执不执行、格式守不守）。任何一项不过，先改登记再试点。

Smoke root `/data/execskill-20261021-pre`, own ledger (cap 3M solver, 2M GLM). Items: SearchQA/LiveMath/ALFWorld from
the tail of each order (beyond every registered slice); SpreadsheetBench and OfficeQA: 5 items each removed from the
supply before slicing (registered; OfficeQA then R = 19, SpreadsheetBench R = 26; A unchanged).

| id | check (zero-call unless marked paid) | pass criterion |
|---|---|---|
| S-Q1 | solver equivalence: with zero enabled procedures, every (system, user) request hash (`calls._request_hash`) and prediction equals frozen `backends.solve` on 20 public views per bench, using a stub `call` replaying recorded receipts | 100% identical |
| S-Q2 | scorer v2 on all archived v3/cal-1 **training** cells | v2 ≥ official on every cell; counts of JSON-only passes reported |
| S-X1 | sandbox containment: network, file write, fork bomb, memory hog, infinite loop, oversized output, banned import | each blocked and classified P2 (not P4); host unaffected |
| S-X2 | determinism: every smoke procedure executed twice on 50 views | identical output hashes |
| S-X3 | worker start time over 50 starts; per-request latency | median start ≤ 3 s, else re-open the worker design |
| S-R1 | router + twin scheduler dry run on all slices' public views (no solving) | enable decisions deterministic; twin counts within 10% of plan |
| S-L1 | ledger/halt unit tests with synthetic receipts (reasoning on/off, over_nominal, > bound) | rows P5/P6 and halt fire exactly as registered |
| S-E1 paid | 5 requests: echoed model id, usage fields | all delivered, id = `deepseek-v4.1-flash-1017` |
| S-E2 paid | 40 requests with `reasoning_effort: "none"` | 0 with reasoning tokens > 0 or reasoning content |
| S-E3 paid | 200 requests at 8 concurrent | 429 share ≤ 2% (else slots 6); p90 latency reported |
| S-E4 paid | long-answer prompt, reasoning off, max_tokens 16, 10 requests | decides: cap enforced? finish_reason `length` reported? Registers the truncation rule (K1) |
| S-E5 paid | prompt_tokens vs request bytes on 40 requests | prompt ≤ bytes + 512 on all (PJLAB gateway added ~90 tokens once, SB K2) |
| S-E6 paid | per-cell tokens on the format-check cells; ledger/actual ratio | replaces §8.1 anchors; ratio ≤ 1.3 |
| S-F1 paid | format check, C arm: 20 items (SB/OQ 5) per bench | ≥ 9/10 format compliance (v3 floor, smoke.py:71-77); else stop |
| S-A1 paid | ALFWorld shell: 5 games, C arm and a toy context procedure | canonicaliser log present; no `expert_plan`/`gamefile` in any view; cleanup confirmed; wall time per episode |
| S-G1 | generators: SpreadsheetBench 5-10 generated items qualified with 0 model calls [SF R5]; OfficeQA reproduction check on 10 items; LiveMath independent-program agreement on 10 | yields reported; gate code exercised |
| S-T1 | ALFWorld test identity: evaluation code with TestAccess verifies the test panel is `valid_unseen` and that no D_alf game path is in it; prints counts only | verified, or the ALFWorld supply is re-registered |

## 10 Risks, failure modes, and the honest reporting rule for each

负责人摘要：每种可能的坏结果事先写好"怎么写"。最可能的结果是：试点两步都不收、考官的出题程序"未检验"、迁移"未分辨"。
这些都照实写，不能写成"有效"。

### 10.1 Positioning against the closest prior work (novelty risk)

| work | what it already has | what this registration adds and must claim instead |
|---|---|---|
| FlowEvo [RW §2, ref 22] | executable skills with preconditions, replay tests, banned imports; per-skill utility by withholding on matched episodes; each benchmark starts from an empty bank, no cross-benchmark transfer; ALFWorld learned online on its 134 tasks | we adopt its representation and its withholding control; new: randomized withholding **across benchmarks** inside one cumulative package (§7.3), placebo twins of procedures (§1.6), and acceptance on route-B-fresh batches instead of online on the reported tasks |
| CoEvoSkills [ref 21] | skills co-evolve with a surrogate verifier that writes executable tests, anchored by an oracle pass/fail bit of the **same** task; no validation set; reports on the tasks it evolves on | our examiner is anchored on items it never optimised on: detectors accepted on held-out trajectories (§6.1), generators judged by predictive validity against a later real batch (§6.3) |
| GRASP [ref 23] | accepts a skill only on a held-out probe from the training split, re-runs the parent at the same time, caps regressions; gate helps in-domain, not out of distribution; probes are reused across decisions | one-shot batches (consumption registry), four interleaved arms incl. placebo procedure and card-only, an intersection-union decision (§5.3); and we expect GRASP's in-domain-only pattern and test for it (§7.2 Q3, §7.4) |
| Break It Down, Pass It On [ref 29] | code-form skills transfer worse than text-form; task-level skills can hurt | the text twin T_F (§7.1) measures exactly this contrast at test; the expected result is pre-stated (§7.4) |

Claims we never make: "first executable skill library", "first co-evolving verifier", "first cross-benchmark
transfer" [RW §0.4]. Headline claims, if supported: (1) the examiner's predictive-validity gate; (2) placebo-controlled
one-shot fresh-batch acceptance; (3) per-procedure cross-benchmark attribution with randomized withholding.

### 10.2 Failure modes

| # | failure mode | detection | honest reporting rule |
|---|---|---|---|
| R1 | no candidate accepted in the pilot (most likely, E) | §5.3 | "no procedure package was accepted at the registered MDEs (list)"; never "procedures do not help"; report S' − S estimates with CIs |
| R2 | accepted only through the placebo-free contrast (S' > S, S' ≯ P) | §5.3 | reject; report "the gain is not distinguishable from a structurally matched placebo" |
| R3 | placebo itself helps (P > S) | descriptive P − S | report as an instrument fact ("an extra note or second look helps by x"); it is not a learned effect |
| R4 | instrument broken: duplicate null fails (G5), reasoning mismatches > 1% (G4), interleaving imbalance | guards | pause; no decision; the batch is recorded as consumed-without-decision |
| R5 | generators never admitted (saturated / too hard / shortcut) | §6.2 | "examiner-side generation did not pass its gates on bench b" — the examiner story reduces to detectors |
| R6 | generators admitted but untested or retired (§6.3) | §6.3 | "predictive validity untested (no informative contrast)" or "refuted"; generated-set results never cited as effects |
| R7 | detectors not decidable on small benches (K6) | §6.1 | "not decidable at |V| = n"; only mechanical categories reported |
| R8 | procedures help only at home; transfer ≈ 0; T_F ≥ F elsewhere | §7.3-7.4 | "no per-procedure transfer established; text form transferred at least as well as code form" |
| R9 | harmful elsewhere (UB < 0 on a dissimilar bench) or Q3 fails | §7.2-7.3 | named per procedure and bench; Q3 "non-inferiority not established at Δ_NI = x" |
| R10 | engineer-written code fails (D3: 41% of agent steps needed the parser; 21/49 v3 proposals died of format faults) | §4.4 counts | report proposals, drops by reason, fault rates; engineering yield is a result, not hidden |
| R11 | canonicaliser changes the sign of an ALFWorld effect (D3/D14: tracker hurt in the frozen loop, FP F7) | it is in every arm (A9) | report canonicalised-step shares per arm; claims hold only for the guarded loop |
| R12 | in-sample hindsight (D14 "55/57 open surfaces" from walkthrough metadata, FP F16) | leakage + input whitelist | no procedure, detector or generator may use walkthrough metadata; evidence from it is labelled in-sample |
| R13 | serving drift (terse/verbose regimes, OfficeQA ±20 points between windows) | per-bin shares | contrasts only; absolute accuracies "this window only" |
| R14 | small-pool overfitting on OfficeQA/SpreadsheetBench (reused v1/v3 items) | disclosure (K7) | "route-B-fresh, not absolutely fresh"; effects below ~8-13 points not certifiable there |
| R15 | budget stop mid-unit | ledger | pause, no auto-resume; the unit is redone whole only on an owner decision; partial units never read |
| R16 | new model differs (action wrapper forms, verbosity, truncation) | smoke S-E*, S-F1, S-A1 | registration adjusted **before** the pilot; never after any acceptance outcome |
| R17 | sandbox escape or host contamination | S-X1 | stop the protocol; security incident, not a result |
| R18 | multiplicity across steps | count | report the number of decisions and the ≤ 0.05 per-decision bound; no chain-level guarantee claimed |

### 10.3 What cannot be measured in this design (stated up front)

- Learning-process variance: one history per chain; intervals are item-sampling intervals only [V6 §1].
- Effects below the §2.4 MDEs on any bench; similar-bench gains at test (Q2 is descriptive).
- Per-procedure effects below ~10-20 points; most per-procedure labels will be "undetermined".
- Predictive validity of a generator beyond one round per bench (K2).
- Whether procedures would transfer to a *new* benchmark outside the five (no such bench is read).
- The causal role of the examiner in any accepted procedure (no ablation arm without examiner inputs; optional D12).

## 11 需要负责人决定的事（每项都有默认值；不决定就按默认）

1. **试点做哪两个 bench、什么顺序。** 默认按您认可的顺序：SpreadsheetBench（表格题）→ OfficeQA（财政公报计算题），
   做题约 5,000 万–8,900 万 token。缺点：这两个 bench 题太少（91 道、74 道），验收只认得出 8–13 分、6.5–11.6 分的大效果，
   "生成题能否预测真题"也很可能量不出来。**我建议**改成 SpreadsheetBench → ALFWorld（文字家务游戏）：ALFWorld 有 3,514 局
   没用过的训练局、模拟器直接判成败、任务卡下约一半失败、失败几乎都是找东西打转，验收 150 局能认出约 8–9.5 分，出题程序
   （挑选新局）的方向对不对也最有机会量出来；代价约 7,900 万–1.33 亿 token。另一个可选：SearchQA → ALFWorld（约
   8,600 万–1.54 亿；SearchQA 题多但任务卡之上只剩 0–3 分余量）。注意：试点就是整条链的前两步，改试点顺序等于改整条链的顺序。
2. **LiveMath 评测块 e03–e08（150 道，至今没人读过）** 是否放出来当训练侧验收题。默认：不放；LiveMath 只用池内 283 道。
3. **SpreadsheetBench 原始 912 题版**是否下载（需开发机代理、许可证 CC-BY-SA-4.0、要做合格检查，能用多少不知道）。默认：不下载。
4. **SearchQA 新块**：从 HuggingFace 验证集里从没抽过的 11,380 道中抽 1,000 道作验收题；排除测试集、预留 1,000 道、
   A–D 四块和训练池，只核对题号，由持有测试访问权限的代码执行，封存的 C/D 两块不打开。默认：同意（只在 SearchQA 那一步用）。
5. **ALFWorld 新局**：从训练集 3,514 局里按 6 种任务类型各抽 100 局；并由持有测试访问权限的代码核实测试集确实是
   `valid_unseen`、新局不在测试集里（只打印计数）。默认：同意（只在 ALFWorld 那一步用）。
6. **测试集读几次。** 默认：试点只在最后读一次（约 3,800 万–6,600 万）；整条链也只在最后读一次。每步都读会多出
   约 1.5 亿–4.1 亿，但能得到每一步的五域表。
7. **预算上限（按账本计，碰到就暂停，不自动续跑）。** 默认试点做题 1.2 亿（选 SpreadsheetBench → ALFWorld 则 1.75 亿），
   GLM 方法角色 3,000 万（含冒烟），冒烟做题 300 万。说明：A13 提议的 1 亿只够预期情况，高成本情况会在读测试集时停下。
8. **做题模型与角色设置。** 默认：做题用 deepseek-v4.1-flash-1017，经 PJLAB 网关，关掉推理（`reasoning_effort: "none"`，
   每次回复都核对推理 token 为 0）；单次回答上限问答 8,192、表格 16,384、ALFWorld 每步 1,024 token；读超时 600 秒；
   8 路并发；工程师、考官用 GLM-5.3（推理档 low、温度 0）。
9. **试点即正式链的前两步。** 默认：是。因为"每批题只用一次"，试点用过的 OfficeQA、SpreadsheetBench 题不会再有新的；
   如果把试点当成单独的一次，正式链在这两个 bench 上就没有题可用。
10. **可选的"同文本重复组"**（与只有任务卡的组完全相同的第五组，用来量同时段的噪声底；验收费用多约 25%）。默认：只在
    SearchQA 那一步加（第 1 步本来就自带一个，见 K3）。
11. **测试读取里加"只有文字说明、不带代码"的一组**（直接回答"代码形式是不是比文字形式更难迁移"）。默认：加；ALFWorld
    上可省（省约 550–810 万）。
12. **可选消融"工程师不看考官的输出"**（回答考官到底有没有帮上忙）。默认：不做（要多一整组验收）。
13. **沿用 v3 的 SpreadsheetBench 合格名单与判分引擎记录。** 默认：沿用，开跑前零调用重新核对哈希。
14. **开发机上约 21 个残留的 D3/D14 进程（约 2.7 GB）。** 默认：冒烟前由您删除或授权删除；在此之前"没有残留 ALFWorld
    进程"这一项检查只能记"无法判断"。
15. **读测试集的同意书措辞**（新增：多组、ALFWorld 测试集身份核实）。默认措辞见 §7.6，请您用自己的话写一句。
16. **沙盒方式。** 默认：每局（ALFWorld）或每组（问答、表格）一个常驻容器；备选"每次调用一个容器"更隔离但慢（冒烟会量
    启动时间，中位数超过 3 秒就回来找您）。

## 12 术语表（给负责人）

- **过程（procedure）**：工程师写的一小段程序，在做题模型每次作答前后由"壳"运行，做三类事之一：往提示里加一段整理好的
  信息（context）、替模型做精确计算（compute）、把某些动作标成不建议（veto）。
- **适用条件（predicate / applies）**：每条过程自带的判断程序，读题目的公开内容，决定这条过程这道题要不要启用。
- **路由器（router）**：固定代码，每道题开始时把所有适用条件跑一遍，并记日志（启用日志）。
- **壳（shell）**：固定代码，包在做题模型外面，负责运行被启用的过程；它不能改模型的最终回答。
- **任务卡（task card）**：每个 bench 一段冻结的作答说明（沿用 v3 I-ds 起点用的五份 GLM 写的指令），只给当前 bench 的那一份。
- **格式护栏（format guard）**：每个 bench 固定的"答案写在哪里、怎么写"的一句话，加上 ALFWorld 的动作规范化（把
  "action: X" 这类写法对到合法命令上），所有组都一样，不学。
- **S、S'、P、C**：S 是上一步传下来的包（父版本）；S' 是这一步的候选包；P 是安慰剂组（把新过程换成"占同样位置、做同样
  次数调用、但不给有用信息"的替身）；C 是只有任务卡、没有任何过程的组。
- **F、P_F、T_F**：读测试集时的最终包、它的安慰剂版本、它的"只有文字说明"版本。
- **跑题段 / 验收段（run slice / acceptance slice）**：每个 bench 的题按固定种子排好序后切出的两段；前一段给考官和工程师
  看失败，后一段只用于一次"收不收"的决定。
- **消耗账（consumption registry）**：只能追加、不能改的记录，每道题第一次被派发之前写进去；写过的题不能再用。
- **同时段交错（interleaving）**：几组的所有题目放在一个随机顺序里一起发，消除"不同时段服务状态不同"的影响。
- **MDE（最小可检测效应）**：在登记的题量下，有 80% 把握认出来的最小提高（单位：百分点）。比它小的提高"认不出"，
  不等于"没有"。
- **单侧检验、交并检验（IUT）**：只问"是不是更好"的检验；"两条都要成立才收"时，每条各用 5% 的门槛，整体误收也不超过 5%。
- **不劣检验（non-inferiority）**：问"是不是没有比对照差超过 Δ 分"；Δ 按题量算，试点里约 6–10 分。
- **随机拿掉对照（withholding twin）**：同一道题、同一时段，再做一遍"拿掉某条过程"的版本，两者之差是这条过程的因果效应。
- **检测器（detector）**：考官写的程序，读一道题的完整作答记录，判断它是否属于某类失败；只拿"对/错"当真值。
- **查准率 / 查全率 / 提升（precision / recall / lift）**：检测器报警的题里真失败的比例；真失败的题里被报警的比例；
  查准率比平均失败率高出多少。
- **生成题、出题程序（generator）**：考官写的程序生成的新题，答案由程序或模拟器算出；ALFWorld 是从没用过的现成游戏局里挑。
- **饱和 / 难度带**：父版本在生成题上的通过率要在 20%–80% 之间，太容易或太难都量不出差别。
- **捷径检查（shortcut）**：遮住题干只给选项（或拿掉表格）也能答对的题，说明有漏洞，剔除。
- **预测效度（predictive validity）**：生成题上"谁比谁好"的方向，要和真实验收题上的方向一致；不一致或量不出（SILENT）两次就
  淘汰这个出题程序。
- **评分器 v2**：在冻结评分器之外，也认 JSON 格式写出的答案；它只会把官方判错的改判对，不会反过来；决策用它，官方分并列报告。
- **完成口径（completion-aware）**：回答被截断、为空、格式无效都算错（官方口径里截断算"未知"）。
- **推理 token**：模型在正式回答前"想"的部分；本协议要求关掉，每次回复都核对为 0。
- **账本、预留**：每次调用前先按上界预扣 token，回来后按实际结算；碰到上限就暂停。
- **M / E**：M = 实测（附出处）；E = 估计（附假设）。
- **bench 简称**：SB = SpreadsheetBench，OQ = OfficeQA，LM = LiveMath，SQ = SearchQA，ALF = ALFWorld。
- **v3**：上一版正式协议 `fivebench-coevolution-v3`，结果冻结不动；本协议是 `fivebench-execskill-v1`。
- **elucid**：新做题接口在代码里的名字（负责人新开的 OpenAI 兼容网关）。
- **FlowEvo、CoEvoSkills、GRASP、Break It Down**：最接近的四篇 2026 年工作，对比见 §10.1。

## Sources (path:line)

design-v0 (`scratchpad/execskill/design-v0.md`); map §0-§5 (`understand/map.md`); data-and-pools F1-F17, §5;
feasibility-prototypes F1-F61; scorers-and-formats F1-F31, 3b; solver-backends F18-F44; coevo5-method F1-F56;
coevo5-infra F7, F10, F13, G1-G4, G16; linux-ops F1, F11, F35-F39, §5; docs/handoff/related-work-execskill-20261021.md
§0, §2, §5, §6; docs/handoff/coevo5-registration-v6-20261017.md §0-§2, §5, §10, §12.6, §12.8, §13;
docs/handoff/cal1-registration-20261020.md:19-48, 91-152; docs/handoff/direction-recommendation-20261021.md §2, §4-§8;
docs/project-status.md:14; dl:/data/execskill-ops/probe-20261021-{1,2}.log (read-only, 2026-10-21);
calculations `scratchpad/execskill/design/specB-calc/{mde.py, cost2.py, testread.py}`.
