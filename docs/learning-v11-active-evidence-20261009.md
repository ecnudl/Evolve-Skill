# 学习 v11：主动证据驱动的 Skill 进化（`active_evidence`，10/9）

状态：**代码与离线测试完成；真实单轮运行结果以[账本](results-and-lessons.md)为准。** 本文只描述实现与边界，不含效果结论。分支 `research/active-evidence-skill-evolution`。

## 1. 要解决什么

v10 主方法（Rubric→probe→Research 验证器）的每个 stage 都把**固定 val 集**当作接受/撤销的必经关卡；验证器只看 train 产物，检查是域级 rubric 在每一行上的实例化，没有"要区分什么"的原因假设，报告按步整份授权，更新后没有任何新任务或回放证据。L1/L3（10/8–10/9）表明验证器反馈能改进单步提案（h2>标量，p=0.047），但归因不到 Rubric 演化或 Research。

v11 把主线改为：train 执行 → 识别验证缺口与原因假设 → 按需 Research → 生成并执行诊断检查 → 条件化、分级的反馈 → 修改 Skill → 少量**新**任务 + 历史回放检查 → 保留/撤销/暂存。**不再有 val 角色**；动态任务与回放是学习过程数据，不是最终评测（test 仍只在用户要求时报告一次）。（10/10 措辞更正：不读取、不授权规范的 val 划分，也没有重复的整面板验证；但更新后决策使用的新面板抽自准备阶段固定保留的开发挑战池，这个保留池承担选择功能，见 §9。）

## 2. 实现（`skillopt/active_evidence/`，兄弟包）

放在 `continual_learning` 之外（与 `feedback_study` 同理）：`contracts.sources()` 哈希该目录全部模块，新增文件会使当前检出无法验证任何已封存的 v8–v10 stage。包只把 v10 机制当库复用：账本、solver 适配器、probe 提示/解析/审阅/执行 helper、原生更新器流水线。

| 模块 | 职责 |
|---|---|
| `protocol.py` | 封存协议记录：`contracts.manifest` 要求非空 selection，因此包内按同一字段形状构造 **v10 形状的兼容记录**（`version=continual-learning-v10`、`method=rubric_research`、`feedback_profile` 不变——账本/适配器/反馈投影/原生桥都按版本字符串门控），但 `selection_families=[]`、全部 development 任务以低层 `train` 角色授权；真实身份在扩展 `active_evidence`：协议 `active-evidence-learning-v11`、step/challenge 族划分、臂、限额、包/更新器/执行代码闭包哈希。`validate_manifest` 重建比对。`max_iterations≤100`（step rollout 0..99 与挑战 key 1000+ 不冲突）。 |
| `profiles.py` | 五域 profile（输入输出、环境、可见/隐藏证据、可靠检查、允许的变换、限制、信息权限）；Sheet/ALF `supported: False`。从冻结的 `HARNESS_CAPABILITIES`/`DEFAULT_POLICIES` 组装，不从标签或分数学习。 |
| `triage.py` | 纯代码分类（environment / delivery / host_fail / host_pass）、批摘要、按冻结配额选代表案例（失败与成功各半、同族配对优先、再按证据哈希）；隐藏测试回溯只进 `host_only/triage/`。 |
| `diagnoser.py` | 一次 diagnoser 调用（+一次格式修复）：≤N 条原因假设 `{id, kind, statement, mechanism, applies_to, discriminating_observation{supports, excludes}, needs_fact, preserve}`，严格解析。 |
| `checks.py` | 假设绑定的检查：BCB 复用冻结 probe 提示（追加诊断焦点）、`parse_probes`、新增 **`state`** 种类（调用前后对 JSON 参数快照比较；只有合同引文命中"保持输入/原地修改"的确定性线索才可采纳，否则 `not_applicable`）；确定性去重 → **有限盲审**（去掉 rationale 与假设结论，不传产物/宿主状态）→ 现有容器 harness 执行；QA/KOR 走冻结裁判（追加焦点，义务前缀 `[h1]`）。分级 `grade()`：`confirmed_*` 需审阅 keep + 契约引文 + 执行判定且期望依据为 contract/documentation；裁判最高 `pending_explanation`；未解决事实不执行（`unknown`）。 |
| `research.py` | 仅当审阅保留检查但提出事实问题时：plan 选 ≤3 页白名单文档 → 经 v10 抽取器取回（每步按 URL 缓存）→ 解决回复；引文须是来源逐字摘录（`_citation`）且与问题共享内容词（相关性启发式）；修正的期望重新走 probe 准入；无来源/取回失败/无效解决/无引文保留 → 检查不执行，记录 `missing_facts` 与状态。 |
| `reports.py` | 每行分项报告（CONFIRMED VIOLATION / CONFIRMED PRESERVED / PENDING / UNKNOWN / NOT APPLICABLE / ERROR，含假设 id、断言、引文、观察；成功行也可带 PRESERVED）与步级摘要（确认的问题、排除的解释、需保留的行为、建议修改范围、例外、未证明）。 |
| `diagnosis.py` | 每步编排与封存（`diagnosis/<step>/{triage,hypotheses,summary}.json`、`checks/`、`executions/`（intent→receipt）、`reports/`、`research/`、`documents/`）；`call_json` 按 v7 交付规则（闭合长度截断一次恢复、终端单元结果、一次格式重试）。 |
| `updater.py` | `propose_with_evidence`：仿 `propose_arm` 复用 reflect→merge→rank→apply；轨迹的 `evidence` 文本须等于**从磁盘重读并校验封存**的报告（`canonical_report`），摘要同理；族与 rollout 从封存 manifest 推出，调用方不能覆盖；标量臂拒绝任何报告/摘要。analyst 系统提示 = 原生提示 + 迁移要求 + 证据阅读说明 + 步级摘要；**不再把 rubric 字段注入为系统规则**。 |
| `challenge.py` | 候选冻结后封存抽样（族分层、按协议身份与步号种子、排除此前步抽过的任务）：`fresh`（挑战池真实 development 任务）、`replay`（Current 通过的 step 行）、`local_fix`（Current 失败的 step 行，analyst 已见，单列）；执行前对照封存 manifest 与本步评测校验 draw；**两个 Skill 都重跑**，新 rollout key（1000+10·step+{0,1}）；分母分开，含 seen/unseen 族分层。 |
| `decision.py` | **当前为规则 v2（10/10 傍晚，见 §9）**：族级精确单侧符号检验的冻结表。*历史 v1（10/9–10/10 上午的阶段 r–y2 与 SearchQA 研究记录的决策）*：no_update → accepted_without_challenge（无挑战臂）→ park（挑战未完成/成对已知不足）→ revert（回归超限或净负）→ keep（净胜≥阈值）→ park（不确定，附 `restriction_suggested` 新增 hunk）。两版共同：候选 unknown 不计输；缺证据不算成功。 |
| `stage.py` | 一轮：rollout → `bind_step_rows` → **在任何更新支出前预留挑战容量**（不足→`BudgetExhausted`→pending）→ 诊断 → 提案 → draw/挑战 → 决策 → 证据链 `chain/<step>.json`（problem→hypotheses→research→`fact_needs`（假设声明需要的事实：Research 是否被咨询到、未咨询的原因）→checks→observations→edits→challenge→decision，每环 `intervened` 为可观察参与——`research_consulted`/`research_new_information`/`feedback_differs_from_scalar`/`skill_changed`/`challenge_delta`——不是因果收益）→ `steps/<step>.json`。中断返回完整封存 pending 记录（带父、账目、清单），从不续跑。 |
| `__main__.py` | 离线 smoke：`python -m skillopt.active_evidence smoke --output <dir>`（全 fixture，只证明控制流程）。 |

**臂（共享配置）**：`feedback ∈ {scalar, diagnosis, diagnosis_research}` × `post_update ∈ {none, challenge_replay}`；登记四个对照：标量直更、+profile 与主动诊断、+按需 Research、+更新后挑战与回放。固定父 Skill、train 子集、seed、更新器、信息权限与预算规则。

**信息边界**：只有 development 分区可授权（代码断言拒绝 skill_confirmation/final/verifier_calibration）；挑战池永不进入诊断、反思或 Research（solver 必然看到它求解的任务）；隐藏测试、回溯、参考答案不进任何模型载荷；Research 白名单与禁答提示沿用 v10。

**工具入口**：[run_fivebench_g_stage.py](../scripts/run_fivebench_g_stage.py) `prepare --method active_evidence --learning-version v11 [--arm-feedback …] [--arm-post-update …]`（不读 val；step 子集=F 的 outcome-blind train 抽样，挑战池=F development 面板其余任务，全部在 canonical train 内）→ `learn`（F 客户端服务核对、原生锁、包自有的执行 intent 交接检查）→ `status`/`test`/`--parent g:`（`learned.json` 含 `decisions`、`arms`、`evidence_chain_hashes` 与每步 `decision/challenge_summary`）。Linux 启动器 [run_fivebench_active_evidence_linux.sh](../scripts/run_fivebench_active_evidence_linux.sh)。预算 `BUDGET_V11`：v10 + `max_iterations 1`、`max_metric_calls 12000`、`max_verifier_calls 3000`、`verifier_max_tokens 8192`。

## 3. 测试（离线，CI glob 内）

[test_continual_learning_active_evidence.py](../tests/test_continual_learning_active_evidence.py)（31 项，含 §5 的 `fact_needs` 4 项）与[工具测试](../tests/test_continual_learning_active_evidence_tool.py)（2 项）覆盖：无 val 完成一轮且旧 v10 测试不变；显式"不修改输入"契约下 `state` 检查成立、显式"原地修改"或未说明时同一检查 `not_applicable`；错误引文/虚构义务/非法转换/未解决事实/无引文保留/无关引文/修正期望未再准入都不成为 `confirmed_*`；更新后两个 Skill 都有新 receipt 且挑战产物与原产物不同；挑战池文本与私有标签从不出现在诊断/反思提示；中断返回完整封存 pending；预算预留不足 → pending 且更新器未运行；伪造报告/摘要被拒；零调用重放得到同一记录；工具 prepare 不读 val 且 manifest 可重建、证据清单核验。

## 4. 本轮刻意不做（接口预留）

- `--rollout-source`（从封存 v10 stage 导入第 0 步 train rollout，所有臂共享训练经历）：需要 source-aware binder（旧 manifest hash）。
- `restrict`（受限修订：编辑限于候选新增 hunk，在新抽样本上确认）：默认 `restriction_attempts=0`，只记建议。
- KOR 合成实例（`kor_probes.generate`，需全部 23 个 handler）；QA 无生成器。
- Rubric 前瞻式晋升：本轮 rubric 冻结为默认七字段，仅作检查策略材料。
- `reference_val`（仅报告的 val 观测）。

## 5. Codex 代码审查（10/9）与已知限制

两轮审查（GPT-6-Astra ultra，只读）。第 1 步 6 项 must-fix 与第 2–4 步 8 项 must-fix 均已处理：中断返回**并写入**完整封存 pending 记录；step/challenge 边界与 rollout 从封存 manifest 推出；draw 执行前校验；更新前预留挑战容量（含更新器调用估计），不足→pending，诊断逐案检查剩余容量不触及预留；报告/摘要从磁盘重读校验；`max_iterations≤100`；修正期望须重新解析**并经第二次有限盲审**才可执行，引文相关性启发式收紧（通用容器名词不计、问题≥3 个内容词时须共享 2 个）；`state` 快照**精确比较**（无浮点容差）、线索判定否定感知（同时含"保持/原地"线索或都不含→`not_applicable`）、原地义务下参数未变只算 `pending`（输入可能已处于最终状态）；摘要把断言确认（执行检查）与假设推断（consistent / not_observed / undecided，均为试探）分开，不再写"确认的问题/排除的解释"；Research 解决提示改为 v11 专用（keep 必须带引文）；`call_json` 的格式重试同样走 v7 交付规则（含长度恢复）；每步研究页数上限按步而非按案例；KOR profile 改为"仅裁判"。`--rollout-source` 明确记为本轮延后。

首次真实运行（10/9 12:00，见账本）后的修正：真实模型把 `select: null`、`index` 等多余键写进非 structure 探针、把假设 id 大小写写错，导致 16 个案例中 4 个全部探针被严格校验拒绝——新增无害表面变体归一化（`_normalize_probe`）与**一次**带确切错误的探针修复调用（只在整份回复无存活探针且拒绝原因不是 `not_applicable` 时），每案调用上界相应提高到 12；摘要把"关于成功案例的假设全部检查成立"单列为 `preserved`，不再写成"预测的违约未发生"。Codex 复审（第 3 轮）3 项 must-fix 随后修复：假设推断以**全部**被解释案例为准——有案例没有任何可采纳检查时推断保持 `undecided` 并记未覆盖数（缺少覆盖永不读作"无违约"），`preserved/not_observed` 都附支持检查 id；每案调用上界改为最坏情形（每单元 4 次账本请求：调用＋长度恢复＋格式重试＋其恢复；BCB 6 单元＝24，diagnoser 2 单元＝8）；保持线索正则不再把"The original list is modified/changed"当作保持陈述（修改动词必须带否定）。

第一次真实运行还暴露了证据链的一处沉默：诊断器给 h1 声明了 `needs_fact`（seaborn/scipy 的库事实），而 Research 只在某条**已准入**检查的盲审提出事实问题时才会被咨询——h1 的案例没有任何探针进入审阅，Research 从未被触发，链上只有空的 `research: []`，看不出"为什么没介入"。修正（Codex 第 4–6 轮：3 项、2 项 must-fix 后第 6 轮 ACCEPTABLE）：`reports.fact_needs` 对每条声明了事实需求的假设记录 Research 是否真的到达——绑定到**该假设自己的检查**（逐检查的 resolution 记录，或该案例有 Research 记录时检查上仍开放的事实问题；失败的 Research 不留逐索引记录）——以及未到达的原因（`arm_without_research`／`no_admissible_check`（被拒的 state 线索不算准入）／`no_check_reached_review`／`fact_question_only_on_dropped_checks`（研究器只接收被保留检查的问题）／`review_raised_no_fact_question`）；多个案例的 Research 结果不一致时记 `consulted:mixed` 并列出全部状态；`resolved` 只在自己的检查取得 `documentation` 依据时为真，声明的问题与审阅问题之间只有结构绑定、不做语义匹配。未解决的事实以"不可编码为规则"的措辞进入步级摘要的 Unproven 段；摘要截断为该段预留至多三分之一额度，任意额度下总长 ≤ 额度＋一个截断标记（更新器上限，Codex 对 1–4000 的全部额度穷举核验）；没有准入检查但有事实需求时也生成摘要。链上新增 `fact_needs` 与 `intervened.research_consulted`，`feedback_differs_from_scalar` 在只有摘要（无逐行报告）到达 analyst 时也为真；报告脚本的公开导出不含问题文本。测试 +4（31 项＋工具 2 项）。这只改记录与反馈措辞，不改变检查的生成与执行；快照 u 的 s/t 两轮不含此修正。

限制：Sheet/ALF 不支持；QA 无执行、KOR 的 `kor.verify` 形式检查未接入；文档白名单仅 Python 3.11 标准库（≈62% BCB train 任务返回 DataFrame/图/数组，照旧难有可执行 expected 检查）；确定性可采纳性只有去重与 `state` 线索，**没有**与公开示例冲突的检查；`state` 线索与引文相关性都是启发式，不是语义保证；有限盲审仍看到产物条件化的检查本身（输入、期望、引文）；探针执行的异常末行可进入 analyst 报告（不是隐藏测试回溯）；analyst 提示未做字节级打包（继承 v10，账本 240 KB 上限）；同一 Skill 重复翻转 6–10% 位置，24+16+8 个位置的挑战只能给方向性证据；诊断按案例顺序串行（BCB 每案 ≤10 次账本请求上界）。

## 6. 真实运行与证据链（10/9，BCB，GLM-5.3 low；逐条记录见[账本](results-and-lessons.md)）

每个阶段一个 step；下表每格来自封存记录的零调用导出（[fivebench-active-evidence-20261009.json](results/fivebench-active-evidence-20261009.json)，只含计数/哈希）。"介入"= 该环在链上**可观察地参与了**（Research 被咨询／Research 带来新来源且被检查引用／反馈文本与 scalar 不同／Skill 变化／挑战差异＝fresh 净胜≠0 或 replay 有回归），**不是**因果收益。所有阶段 train 子集同为 128 题（66 fail／62 pass 的空父 rollout 在 r、scalar、diag、s、v 五次重跑中逐位有 6–10% 翻转，但总数一致），挑战池 272 题（development 内、不与 train 子集重叠），`cases_skipped_for_reserve` 全为空（预留容量从未触发）。

| 阶段（快照） | 臂 feedback/post_update | 父 | 假设（needs_fact） | 检查执行→分级 | 假设推断 | Research 介入 | 反馈≠scalar（带报告行） | 编辑→Skill 字节 | 挑战 fresh／replay／local_fix（胜/负） | 决策 | test 格（一次性） | 成本（调用；tokens） |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r（r） | diagnosis_research／challenge_replay | 空 | 4（h1 需库事实） | 5→preserved 5 | h1 undecided（0 检查）；h2/h3/h4 not_observed* | **否**（`research: []`；h1 的事实需求没有任何检查进入审阅，当时链上无 `fact_needs` 记录——§5 修正的起因） | 是（4） | 2→6,034 | 5/1（净+4，p=0.11）／1/0／2/0；0 回归 | keep → `selected_update` | 256/484 vs No-Skill 239；44胜26负净+18；p=0.041 | 267（224/22/21）；33.1 万 ＋ test 48.4 万 calls／75.7 万 |
| r-scalar（r） | scalar／none | 空 | — | — | — | 否（臂定义） | 否（0） | 4→6,792 | — | accepted_without_challenge | 未跑（决定：单格分不开同类 Skill） | 150（128/0/22）；17.4 万 |
| r-diag（r） | diagnosis／none | 空 | 4（无） | 6→preserved 6 | h1/h3 not_observed*；h2/h4 undecided | 否（臂定义） | 是（4） | 4→6,708 | — | accepted_without_challenge | 未跑 | 171（128/22/21）；22.6 万 |
| s（u） | diagnosis_research／challenge_replay | 空 | 4（h2 环境事实） | 5→preserved 3、pending 3、unknown 1、format_or_env_error 1 | 全部 undecided（覆盖感知） | 否（修复调用 4 次挽回 3 个案例的探针，但没有审阅提出事实问题） | 是（7） | 1→候选未采纳 | 1/1（净 0，p=0.75）／0/2（2 回归＝上限）／1/0 | park（`inconclusive_net_wins_below_minimum`）→ `completed_no_update` | 不适用 | 273（224/29/20）；35.9 万 |
| t（u） | diagnosis_research／challenge_replay | g:r（6,034 B） | 4（无） | 8→preserved 8、pending 1 | 全部 undecided | 否 | 是（7） | 4→10,381 | 2/0（净+2，p=0.25）／3/0／1/0；0 回归 | keep → `selected_update` | 256/484；42胜25负净+17；p=0.050；与父 r 逐位 58 处对称翻转（28/29） | 276（224/30/22）；61.8 万 ＋ test 48.4 万 calls／119.2 万 |
| v（v） | diagnosis_research／challenge_replay | 空 | 4（h3 需库事实：scipy.stats.skew/kurtosis 的单元素行为） | 6→preserved 6、pending 6 | 全部 undecided | **否，且首次记下原因**：`fact_needs[h3] = not_consulted:no_admissible_check`（h3 名下 0 条可准入检查），`research_consulted=false`；未解决事实进入摘要 Unproven 段，候选补丁不含它 | 是（9） | 2→候选未采纳 | 1/1（净 0，p=0.75）／1/0／1/1；0 replay 回归；`challenge_delta=false` | park → `completed_no_update` | 不适用 | 273（224/28/21）；35.9 万 |

\* r 与 r-diag 跑在快照 r（Codex 第 3 轮覆盖感知推断之前）：那里的 `not_observed` 在当前代码下会读作 `undecided`（有案例无可采纳检查）。r–t 跑在快照 r/u，链上没有 `fact_needs`／`research_consulted`（导出中为空列表／缺键）；只有 v 含这两项。

读法：除 Research 之外每一环都真实参与了——诊断器每次都给出 4 条假设、探针经确定性准入与有限盲审后在容器里执行、分级报告与步级摘要进入 analyst、两份 Skill 在新抽任务与回放上重跑、决策表给出 keep／park 并驱动了工具的 `selected_update`／`completed_no_update`。但**信息量**是另一回事：执行检查几乎只产生 `confirmed_preserved`（六个阶段 0 次 `confirmed_violation`），假设推断全部停在试探级，Research 一次都没有被到达（六个阶段的事实需求在 r、s、v 各出现一次，都没有检查把它带到审阅；v 的记录把原因写明为"无可准入检查"）；三份不同臂的 Skill 同为"按合同逐条审计"的通用文本；同配置三次挑战（r 净+4、s 净 0、v 净 0；父=r 的 t 净+2）与同谱系两个 test 格（256→256）都在噪声带内。因此这组运行证明的是**流程闭合与证据链可回查**，不是方法效果；在 BCB 上 v11 与 v10 面对同一信息瓶颈（隐藏测试失败多为期望值断言，公开契约推不出可执行 expected 检查）。阶段 w（快照 v、父=r）零调用准备、未启动。

## 7. 10/10 判决实验：有界的开发集失败信息反馈（配对分支研究，不是方法）

**Step 0（零调用，10/10 01:00）**：用封存产物回答"solver 到底遵不遵循 Skill"。同一 128 题开发任务上五次空 Skill rollout（r、scalar、diag、s、v）之间：状态翻转 9.4–12.5%、文本相同 7–13 题、AST 相同 7–15 题、difflib 相似度均值 0.689–0.729；空 Skill 对 r 的 Skill（阶段 t 的 rollout）：翻转 14.1–17.2%、相同 4–6 题、相似度 0.639–0.664；test 484 题上 No-Skill 对 r/t/SkillOpt v9 三格/GEPA 两格：相似度 0.623–0.671。特征频率在五次重跑范围之外的移动：r 的 Skill 下绘图任务（n=48）设标题的产物从 52–62% 降到 29%、`try:` 从 16–21% 降到 13%、代码更短；v9 的 Skill 在 test 上把文档字符串从 14.5% 推到 22–32%、代码更长。**读法（经 Codex 审查收紧）**：这是提示敏感性而非规则级遵循——Skill 文本确实可测地改变了产物分布（五次重跑是相依比较、特征是探索性的，不是校准过的显著性检验），但不同 Skill 把代码推向不同方向却都落在 247–258；六阶段"0 确认违约、Research 未到达"不能单独推出"信息是唯一瓶颈"（探针准入、Research 不可达、抽象弱、编辑选择、遵循度都是竞争解释）。

**决定（Codex 方向审查四轮：三轮 NOT ACCEPTABLE 共 14 项 must-fix 后第四轮 ACCEPTABLE；备忘 v4 见 `docs/handoff/active-evidence-label-study-design-20261010.md`）**：做一个**有界的开发集失败信息反馈**研究，回答"在父 Skill、训练 rollout、更新器、种子、minibatch 分组、编辑预算与（无）选择策略全部固定时，把失败开发行的隐藏测试最终异常消息交给 analyst，是否得到一个在新抽开发留出集上胜过配对标量分支的候选 Skill"。它不是上界、不是方法；一次实现的候选对、一条训练历史、复用的开发池——探索性。

- **臂与模式**：`feedback = hidden_failure` 只能与 `post_update = matched_scalar_branch` 配对（协议拒绝其他组合）。一次 rollout（父=空 Skill，与 r/s/v 同 128 题同种子）→ 同一组绑定轨迹喂两个更新器分支：S（比较基准）＝ scalar 臂的逐字节相同 analyst 包；M（处理）＝ 释放的报告 + 固定的 LABEL 前言/摘要（估计量＝整个反馈包）。两个冻结候选在候选冻结后抽取的 242 题开发留出集（挑战池 272 题内、按族分层、每族一题）上各求解一次（rollout 键 1000/1001）；replay/local_fix 为 0（比较基准从未解过 step 行，协议强制）；`min_paired_known = 218`（90%）。决策记录把 M 记为 candidate、S 记为 current 以复用配对机制，但**不部署任何东西**（`current` 不前进，`learned.json` = `completed_no_update`，`G_SKIP_TEST=1`，不读 final）。
- **释放策略（`label_feedback.py`，`development-failure-messages-v1`，封进 manifest 的 `release_profile`）**：来源 `score.metrics.details`（测试名→回溯）；每条回溯取**最后一行**匹配异常类模式的行到末尾（链式异常取最终一个），删除帧头与绝对路径，400 字符上限；测试名排序取前 4，行文本 ≤1800；无异常行的回溯**不释放**；每条消息与整行文本都过禁止内容检查（`Traceback` 头、`File "`、`line N, in`、绝对路径、两格以上缩进的源码行），命中即扣留。审计 `release_audit.json`（分母、消息分类 value_diff/not_raised/bare_assertion/typed_error/other_assertion、每行来源与释放载荷哈希）在任何更新器调用之前封存；释放行 < 失败行的 50% → `failed_delivery`，步在更新器之前停止（pending）。零调用预演（r/s/v 的封存 rollout，v3 策略）：66 个失败行中释放 63–64、扣留 2–3，共 225–227 条失败测试中展示 177–181、扣留 7–8、截断 3–5；展示消息分类（r）：typed_error 81、value_diff 62、other_assertion 14、bare_assertion 11、not_raised 9。承认：v8/v9 的 BCB 学习已释放过异常类、失败位置与候选源码行，这里新增的是消息内容。
- **统计（`matched.py`，预先指定）**：估计量＝共同已知留出位置上的配对通过率差（M−S）；区间＝ **Tango (1998) 配对比例差的 score 区间**（稀疏/零不一致对下有效，δ=0 时退化为 McNemar；自检：n=218 下 2000 次重复覆盖率 0.943–0.960，审稿反例 b=6/c=0 给 [0.0097, 0.0587] 不排除 0.05，真差 0.05 时误排除率 1.8%）；检验＝不一致对上的精确双侧符号检验（挑战摘要里冻结的 `family_p_value` 是单侧的，只记录不用于分类）。结局类：`failed_delivery`（释放不足/候选相同/处理分支无候选/unknown > 10% 或已知 < 218）、`useful_gain`（d ≥ 0.05 且 p ≤ 0.05 且下界 > 0，另标 `robust_to_unknowns`：把所有 unknown 记为处理方失败后仍成立）、`harmful_change`（镜像）、`inconclusive`（`worthwhile_gain_excluded` 仅当上界 < 0.05，否则 `interval_includes_both`）。任何结局都不是"通道上限"。
- **机制与泛化**：零调用报告给出显式归因审计（提案文本是否引用释放的测试名/异常类/"hidden test"等词）——缺席记为**机制未知**，不写成"消息没有影响编辑"；`label_echo`（释放的字面量/测试名逐字出现在 M Skill 中的计数）只作描述。本研究**明确允许**基准特定的监督式学习（M 可以学到 BCB 隐藏测试惯例），留出任务与 step 任务不相交但语义独立只是假设。
- **披露**：final 面板已被每条 BCB 链与 10/9 的 r/t 格读过，本研究方向受这些数字影响；本研究不读 final、不产生 test 数字。挑战池已向 r/s/t/v 提供过 fresh 挑战（至多 96 题曾在其他 Skill 下被解过、从未进过 analyst 提示），因此留出集是**复用的开发评测**，报告记录与各阶段 fresh 抽样的重叠。
- **工程**：新模块 `label_feedback.py`、`matched.py`（进入 `MODULES` 与代码闭包，新协议身份）；`stage.py` 分派与配对分支、`native_matched/<step>/` 目录进入产物清单；`updater.py` 的 LABEL 前言（版本 `development-failure-message-guidance-v1`）与 checker note 只对 M 分支生效，其他臂逐字节不变；`profiles.INFORMATION_PERMISSIONS` v2 与 manifest 的 `information_boundaries` 按臂如实声明；工具 `--arm-feedback hidden_failure --arm-post-update matched_scalar_branch`、`default_limits(arms)`、清单含 `native_matched`、`learned.json` 记 `matched_outcome`；报告脚本输出 `release`/`matched`/`study_audits`。测试 +4（37 项＋工具 2 项；精确 `intervened` 断言加入 `label_feedback`），smoke 通过，回归 124 项通过。Codex 代码审查四轮（第 1 轮 7 项 must-fix：释放审计逐行记账、跨平台路径、归因只看 reasoning 字段并区分选中/minibatch、留出集复用重叠与族独立假设、unknown 过多仍报统计、双分支预留按 minibatch/merge 结构并检查 reflection 上限、工具清单与阶段回放一致；第 2 轮 4 项：归因报告崩溃、行级截断后的展示计数、标点开头的路径、递归合并层级；第 3 轮 1 项：路径模式对 `<>|` 的排除；第 4 轮 ACCEPTABLE）。预算：128 + 2×~22 + 2×242 ≈ 660 次逻辑调用、约 0.7–0.9M tokens、约 45 分钟。**同一配对设计也接受方法自身的反馈作为处理分支**（`feedback = diagnosis_research` + `matched_scalar_branch`：诊断包对标量包，同 rollout、同留出集，不部署）——这是 10/9 的 24 题挑战做不到的、有一定检验力的方法反馈对照（阶段 y）。

**结果（x4，02:00–02:27）**：释放 65/67 失败行、187 条消息；S 6,267 B／M 13,750 B，diff 107 行；留出 242 题全部共同已知：M 胜 20／负 17／平 205，d = +0.012，Tango 95% [−0.038, +0.064]，p = 0.74 → **`inconclusive`（区间含 0 与 +5%；排除大效应）**；归因 `cited_in_selected_edits`（弱：1 个字面量），label echo 11 个字面量；留出集 76/242 曾被 r/s/t/v 的 fresh 抽样用过；657 次调用、1.60M tokens。冻结决策表对同一数据给 "keep"（净+3）——规则在噪声级触发，结局类才是正确读法。

**结果（y2，方法自身的 diagnosis_research 包对标量包，02:36–03:06；y 在第 46 行因任务 348 的进程杀伤型解停止，见账本）**：16 案例、4 假设、7 执行检查（preserved 6）、**Research 首次介入并解决 h2 的事实问题**（`consulted:resolved`、`research_new_information = true`）；S 4,334 B／M 6,035 B，diff 52 行；留出 242 题（241 共同已知）：M 胜 15／负 14／平 212，d = +0.004，Tango 95% [−0.042, +0.050]，p = 1.0 → **`inconclusive`**（5% 收益几乎被排除）；684 次调用、1.12M tokens。两项研究合起来的读法见账本 10/10 03:10 条目：反馈内容（无论执行证据还是标签）经 Skill 文本通道能改变的通过率只有几个百分点。

补充限制：`matched.py` 的检验假设每族一题（BCB 池按族分层抽样成立；多题族需要别的推断）；pending 记录自 x6 起带 `reason_detail`（有界的异常消息，只在宿主侧的封存结果里，不进导出），起因是阶段 y 在一行（BigCodeBench/348：生成的解按名杀进程，原生评分器 `native_exception:ConnectionRefusedError`）上以不带消息的 ValueError 停止。

## 8. 10/10 下午：配对研究 v2——同一留出集上的参照分支（仍是研究工具，不是方法）

**起因**：对 x4/y2 的事后零调用对照（F 的 No-Skill 开发集基线对到同一批留出题，见账本）显示四个候选对空 Skill 也只有 0 到 +4 个百分点、八个区间全含 0。原设计缺少同期的"无更新"分支，只能回答"反馈包 A 对包 B"，回答不了"不用验证集的更新本身有没有用"——后者才是项目的主张。

**改动（Codex 三轮：2 项、3 项 must-fix 后 ACCEPTABLE；设计备忘 `docs/handoff/active-evidence-reference-study-design-20261010.md`）**：

- `protocol.py`：manifest 扩展新增 `reference_skills`（≤4 个具名冻结 Skill，各带来源记录；仅 `matched_scalar_branch`），研究臂的 `information_boundaries` 新增 `holdout_references`。
- `challenge.run_references`：S、M 两批之后，父 Skill 与各具名参照在**同一批**留出位置上各求解一次（键 `1000+10·step+3+i`），封存 `challenge/<step>/references.json`（逐位状态、每个分支对每个参照的配对计数、具名参照对父的配对计数）。只评测；具名参照的文本不进任何诊断/裁判/分析提示。
- `matched.py`：`paired_class`（v4 的统计与结局类抽出复用，另加单侧"不比对方差超过 5 个百分点"标志：`holds` 只就共同已知位置，整批须看 `holds_with_unknowns_as_losses`；不成立不等于更差）、`reference_comparisons`、`not_measured`（分支未产生更新＝父自身被解两次的噪声重复、分支与参照逐字节相同、参照与父相同、共同已知不足——都记 `failed_delivery`，计数只作描述，两个标志都清除）、`q3_interpretable`（具名参照减父的**仪器检查**为 `useful_gain` 时，对该参照的比较才可解释）。研究版本 `matched-scalar-branch-study-v2`，链版本 v3。
- `diagnosis.py`／`matched.treatment_delivery_problem`：逐案交付记账 `checks / format_failure / no_checks`（以**有效回复**为准：修复解析成功则用修复后的回复及其拒绝表——顺带修正了此前把修复后的"不适用"条目按首次回复的拒绝表查找的问题），封进案例记录、摘要与证据链；研究中处理包未送达（诊断未完成、0 行报告、或超过一半被尝试案例格式失败）→ 在任何更新器调用之前 pending。方法自身的臂行为不变（照旧在标量反馈上更新，并记下丢失的交付）。
- `stage.reserve_capacity`：更新前预留的容量加入"参照数 × 留出位置数"的求解。
- 工具：`prepare --reference name=g:<已完成的 G 阶段目录>`（可重复）；`reference_skill()` 核对同研究协议哈希、同划分哈希、阶段已完成且 Skill 哈希一致、其训练族与本阶段挑战池不相交；**不**重新核验其学习证据（来源记录中写明）。
- 测试 39＋3 项；回归 166 通过／7 跳过；离线 smoke 产出 `references.json`。

**读法（启动前固定）**：Q1 不用验证集的更新对无更新（S−P、M−P）；Q2 反馈内容（M−S）；Q3 这些无门控 Skill 对那些有门控 Skill（S、M 各减每个参照；单侧 5 个百分点）。全部为探索性、无多重性校正、一条训练历史、每分支一个候选；参照来自至多三轮经验证集选择的迭代，分支是一步未经选择的更新，所以 Q3 只能说明"这些无门控 Skill 是否达到那些有门控 Skill 的水平"，**不能**分离"去掉验证集"本身的效应。

**首次运行（SearchQA，方法不做任何改动）**：SearchQA 是项目内唯一有清晰 Skill 效应的域（test：No-Skill 291/400，带验证集门控的 SkillOpt v9／GEPA v9 347，主方法 v10 341）。阶段 `fivebench-g-20261010-searchqa-active-a`（快照 `20261010-a`）：`diagnosis_research / matched_scalar_branch`，父=空，训练 128 题（与两个参照阶段**同一** 128 个训练族），挑战池 272，留出 242；参照 `skillopt_v9`（5,357 B）与 `main_v10`（4,873 B），二者的父都是各自链上未更新的 BCB 阶段（空 Skill）。该域的诊断是 诊断器假设→裁判检查（最高 `pending_explanation`）→逐行报告＋摘要，没有执行与盲审，Research 不可达。结果见[账本](results-and-lessons.md)。

**SearchQA 结果（15:39–16:03，1,399 次调用、313.1 万 tokens）**：留出 242 题（240 共同已知）通过数——父 169、S 194、M 196、main_v10 197、skillopt_v9 204。S−父 +0.104 [+0.064, +0.153]、M−父 +0.113 [+0.073, +0.161]（都是 `useful_gain`）；M−S +0.008 [−0.021, +0.039]（`inconclusive`，5 个百分点的收益被排除）；仪器检查 skillopt_v9−父 +0.146、main_v10−父 +0.117（都是 `useful_gain`）；对 main_v10"不差于 5 个百分点"成立（S −0.013、M −0.004），对 skillopt_v9 不成立且区间不含 0（S −0.042 [−0.080, −0.010]、M −0.033 [−0.068, −0.006]）。读法与限制见账本：一步、未经任何选择的更新实现了大部分已知收益，与带 val 门控的 v10 的 Skill 没有显示出差异（已实现 Skill 之间的比较，不能分离门控本身的贡献）；对 v9 的差距更可能来自标签信息（文本对照的推断，未做消融）；诊断包对标量包在 BCB 与 SearchQA 上都没有确立差异。导出 [fivebench-active-evidence-reference-study-20261010.json](results/fivebench-active-evidence-reference-study-20261010.json)。

## 9. 10/10 傍晚：更新后决策规则 v2（族级单侧符号检验；方法的一部分）

**起因（零调用）**：对三项配对研究封存的已实现配对结果做精确的条件重抽样（[脚本](handoff/active-evidence-decision-rule-oc-20261010.py)，只评估 fresh 部分，不是完整程序的工作特性）：v1 的 fresh 规则（24 题、净胜≥2 保留、净负撤销）对 SearchQA 上观测到的 +10/+11 个百分点差异只有 0.73/0.77 的保留频率，对 BCB 上与 0 相容的各对比保留 0.18–0.38、撤销 0.18–0.38——阈值落在同一 Skill 重复求解的噪声里，与同配置 r/s/v 三次 fresh 净 +4/0/0 一致。

**规则（[设计备忘](handoff/active-evidence-decision-v2-design-20261010.md)，Codex 设计审查两轮）**：证据单位是**族**（该族在一个集合内共同已知位置上的净值：改进／退步／持平；BCB、SearchQA 单题族即逐题配对，KOR 的族是规则，同一规则的相关题只算一次）。检验是非持平族上的精确**单侧**符号检验（增益、损害各一）。顺序：① 无候选→`no_update`；② 无挑战臂→`accepted_without_challenge`；③ 挑战未完成→`park`；④ 回放损害显著→`revert`；⑤ fresh 共同已知不足 `min_paired_known`→`park`（fresh 决策不可采纳）；⑥ fresh 损害显著→`revert`；⑦ fresh 增益显著**且**总量护栏（共同已知 fresh 位置上题级净胜严格为正——族方向不等于总体准确率，15 条规则各赢 1 题、5 条规则各输 4 题时 p=0.021 而净 −5）**且**不利补全（把每个有 unknown 一侧的 fresh 位置记为候选失败后，增益检验与护栏仍成立）→`keep`；⑧ 其余→`park`。回放行是 analyst 见过的训练行，只作损害检验，结论只针对这些行。`revert`＝在所述行上显示了损害，`park`＝没有可采纳的增益证据，二者都保留父。

**执行顺序**：v1 先跑完父的整批再跑候选，批间服务漂移可能冒充效应；v2 对每个集合按种子把位置分成两半，A 半先父后候选、B 半先候选后父（`balanced_abba_v1`，分半与块序封进 outcome）。它抵消单调漂移，不证明可交换性或族间独立——这两者仍是假设。

**错误率陈述（针对一次候选决策步）**：在"以冻结候选与此前全部历史为条件（回放另以历史通过的选择为条件），各集合内观测到的非持平族符号独立且公平"的零假设下，P(keep) ≤ α、P(revert) ≤ 2α（两次损害检验的并界）。多步阶段或多阶段链上有多次这样的决策，不声称阶段级或链级的 5% 保证。

**限额（在任何挑战结果出现前由工具固定并封进 manifest）**：请求值 `fresh_tasks 96`、`replay_rows 32`、`local_fix_rows 8`（只报告，不进决策）、`decision_alpha_permille 50`；`min_net_wins`、`max_regressions` 取消。有效值 `n_eff = min(请求值, 挑战池可用题数)`、`min_paired_known = ceil(0.90·n_eff)`（96→87；配对研究在 KOR 的 200 题池上为 200/180），协议校验该下限；回放/local-fix 在抽样时各自按可用的通过/失败行封顶，不影响 fresh 数；零可用题→挑战 `not_run`→`park`；多步阶段后续步遇到池耗尽→共同已知不足→`park`。池小只降低检验力，**α 不放宽**（KOR 至多 20 个证据单位）。

**运行点的来历与措辞**：96 题与 α=0.05 是用开发证据（含 SearchQA 研究观测到的约 13% 不一致率）选定的，自此前瞻冻结——这不是对规则的独立验证。决策使用的是**从固定保留的开发挑战池中抽样的新面板**（与训练步的族不相交、准备阶段固定）；没有规范的 val 划分，也没有重复的整面板验证，但保留池确实承担选择功能；"fresh"指未被**同一阶段**更早的步抽过，不同阶段可以复用池内任务。每步成本：2×(96+32+8)=272 次求解（v1 为 96）。

**实现**：`decision.py`（`active-evidence-decision-v2`；记录带两个损害标志、`p_gain`、不利补全、总量净值与族分母）、`challenge.py`（平衡执行顺序、`_summary` 的族级统计与 `adverse`）、`protocol.py`（限额模式、`min_known`、`effective_limits`）、工具（准备时计算有效限额，`stage.json` 同时记录请求值与可用题数）；链版本 v4。测试 41＋3 项（决策表每一分支、单题族与多题族、总量护栏、不利补全、平衡顺序、封顶与 90% 校验）；回归 168 通过／7 跳过；五个臂的离线 smoke 通过。

**三个方法模式阶段（10/10 16:50–20:40，前瞻运行）与独立重复（10/11，另一种子）**：SearchQA keep（66→79/96，13 胜 0 负，p=0.00012；重复 68→78，11 胜 1 负）；BigCodeBench park（48→49，5 胜 4 负；重复同为 48→49）；KOR park（题级 11 胜 9 负，规则族 4 改进/5 退步/11 持平）。导出 [fivebench-active-evidence-method-v2-20261010.json](results/fivebench-active-evidence-method-v2-20261010.json)。四次运行不能校准错误率。

## 10. 10/11：两个模块的日志审计、证据交付修复与组合感知筛选

**审计（零调用，封存记录；详见账本 10/11 01:00）**：诊断只覆盖 16 个代表案例（带报告的行在 BCB 是 128 行中的 4–9 行）；BCB 的执行检查在失败产物上多数通过，不判别；探针在严格校验中大量损耗；**裁判域里模型判定有信号却被丢弃**（SearchQA 8 个失败案例中 5 个被判失败、8 个通过案例 0 个；摘要却恒为"0 确认……建议不改"，analyst 直接引用这句话提出空补丁）；KOR 长规则在案例视图里被截断；Research 实际不可达；更新器里**没有任何一步衡量单条编辑的作用**；摘要里引用的 Rubric"例外"句在每个使用诊断包的 SearchQA 阶段都变成了 Skill 里的"无把握时弃权"规则（未测到代价）；一次 BCB 运行因一个文本字段超长而丢失整份诊断。

**证据交付修复（`reports.py`、`diagnoser.py`、`diagnosis.py`、`checks.py`、`updater.py`）**：`JUDGED FAIL/PASS/UNKNOWN` 行（等级仍为 pending/unknown）；摘要的"裁判线索"（每条假设在失败/通过案例上被判失败的案例数）、带报告行数与有执行检查行数分列、不再把"无可执行检查"或"已执行但未解决"写成"无违约/建议不改"、有确认违约但无假设支持时如实说明；摘要不再引用 Rubric 的任何字段；诊断器视图按**序列化提示的字节数**适配（完整题面优先，记录原长度、截断字段与缩放比例）；未被任何假设引用的案例以伪假设 `u0` 做通用检查并计入 `cases_unassigned`；探针表面修复（唯一焦点假设且 id 缺失时绑定；引文与题面唯一一行只差大小写/引号/首尾标点时替换为该整行；点名其他假设、改写、多处匹配、超 600 字符的行仍拒绝）；假设文本超长截断并记录（`clipped_text_fields`）；`check_case` 以**有效回复**为准；Research 否决或再次提问的"修正期望"不再执行。

**组合感知筛选（`screen.py`，`update_mode = "screened"`；[设计约定](handoff/active-evidence-screen-design-20261011.md)）**：原生提案（反思→合并→排序→应用，封存一次）之后，在全部已知训练行上用原生评分器实测**精确文本**：原生候选、每个"去掉一处已应用编辑"的变体（父上重新应用其余已应用编辑，无任何生成步骤；应用状态与原候选不一致视为依赖而不计分；与父相同、超预算、与其他变体同文者记录处置不计分）、编辑≥3 处时每处编辑单独应用的变体，以及父的两次重跑（A/A 对照）。各臂在按种子划分的 16 行块内以随机顺序交错执行；rollout 键 `2000+100·step+arm`。规则 `screen-selection-v2`：对**两个**对照都题级净胜为正且族级单侧符号检验 p≤`screen_alpha`(0.10)、且每个配对比较的共同已知行≥90% 才合格；取净胜和最大者，平局取更短文本；无合格者**弃权**（本步无候选，方法模式不花 fresh 面板）；对照覆盖不足则先封存测量再 pending。盘点记录在计分前封存（行、臂、应用报告、处置、调度、键、规则、一项不参与决定的启发式文本审计）。这是 analyst 见过的行上的**训练选择**——不是效应估计，不验证单条编辑；信息边界：参考答案字段、隐藏测试内容与回溯不进任何提示，优化器得到求解器输出与依赖参考答案的 pass/fail，并用更多评分器查询选择精确文本（分数监督的搜索）。筛选模式下 analyst 被告知编辑会被逐条实测、不同假设应写成可分离的编辑（`SCREENED_PREAMBLE`，其余模式的提示逐字节不变）。更新前预留的容量加入筛选位置数（`(2+1+2·编辑预算)×训练行`）。

**选择研究（`post_update = "matched_selection_branch"`，研究 v3）**：同一 rollout、同一诊断、同一原生提案；比较臂＝原生候选，处理臂＝筛选的选择（候选本身→记为策略一致、是同文本重复而非对比；去一变体或单编辑变体；弃权→以父为处理臂，是被测量的对比）；两者在留出集上以平衡顺序求解，随后父与具名参照求解。参照与父 Skill 现在都可以取自已完成研究的**未经选择**的分支（`m:<研究阶段目录>:comparator|treatment`，逐层绑定该阶段封存的 learned→result→chain→proposal→Skill），`g:` 参照若其阶段曾在本阶段留出池的题上做过选择则拒绝。`--train-families N` 可放大训练子集（种子排序不变，因而包含默认子集；反思调用上限按比例放大）。

**冻结基底的精修试验（[设计约定修订 2](handoff/active-evidence-refinement-design-20261011.md)）**：以研究 a 的标量分支候选（未经选择、从未带"弃权"句）为父，再走一步并筛选；主要估计量＝处理臂减父参照（精修后减精修前）。结果见账本。

**通过案例对照（`diagnosis.control_assignment`，10/11 凌晨）**：错误类假设（task_error_candidate／coverage_gap／delivery／environment）以前只在它声称解释的失败案例上被检查，线索没有对照。现在每个通过的代表案例被分配至多 `max_checks_per_case` 条尚未引用它的错误类假设（稳定顺序轮转、确定性，封存为摘要的 `controls`）；逐案提示只给中性角色 `probe`（对照身份留在宿主侧）；`judged_leads`／`observations` 只按封存的分配计对照（分配数、已判/已查数、被判失败/被确认违约数分列），假设自己声称的通过案例单列；执行违约同时在宿主失败的被解释案例与通过对照上被确认时推断为 `also_on_controls`（特异性与原因未定）。`--limit key=整数` 可在准备阶段覆盖诊断/更新的形状类限额（如 `view_rows`），决策与筛选的运行点不可覆盖。

**探针路径格式修复（10/11 清晨，快照 h；零调用审计见账本 10/11 04:40）**：`checks._normalize_probe` 把缺失的 `obligation_id` 补为唯一可采值 `requested_behavior`（显式写其他取值仍拒绝）；`parse_check_probes` 对超过上限的回复按给定顺序保留前 `max_checks` 条并在拒绝表里记 `over_limit`（信封 `{"probes": [...]}` 仍须精确）；`check_case` 重建“不适用”记录时先把原始探针按解析器同样的规则规范化（此前引文只差大小写/标点时记录消失、单焦点绑定的假设 id 丢失）。已知未改的弱点：`contract_quote` 只校验为题面子串（一个词也能通过），相关性靠有限盲审；模型主动返回空探针列表不算格式问题。

**多题族留出集的读数（KOR-Bench；[约定](handoff/active-evidence-kor-study-design-20261011.md)，Codex 三轮后 ACCEPTABLE）**：研究记录里的题级类别与 Tango 区间在一条规则多题时只作描述；主读数由[零调用脚本](handoff/active-evidence-family-summary-20261011.py)从封存位置计算——各族共同已知位置上的通过率差的等权均值与 t 区间、非持平族的精确双侧符号检验；没有任何共同已知位置的族列为缺失（不记为持平，超过十分之一则不给主估计）；每个对比单独要求 ceil(0.9·位置数) 的共同已知；同文本、未改变父、诊断未送达、缺留出或参照记录时标为仅诊断/不可用。

**测试**：51＋7 项；回归 182 通过／7 跳过；各臂与两种更新模式的离线 smoke 通过。Codex：方向讨论 4 次（两次要求改方向并被采纳）、代码审查 13 轮。

## 11. 10/11 夜间结果汇总（GLM-5.3 low；只用开发集，不读 test；逐次运行，不合并检验）

25 个完成的阶段、31,953 次调用、已报告用量小计 71,771,759 tokens（113 次调用缺 usage）；其中包括未列入三张表的工程演练 pfix1，表 3 另列三个 10/10 的 m1 阶段作对照。表中的通过数是全部抽取题上的边际计数，配对差值只使用该对比共同已知的位置。公开导出 [fivebench-active-evidence-20261011.json](results/fivebench-active-evidence-20261011.json)（只含计数、哈希与决定）；逐条记录见[账本](results-and-lessons.md) 10/11 各条。留出集都是从**被多次复用的**开发挑战池抽取的 242 题（big1d 为 144 题），所以下面全部是自适应的开发证据，不是独立确认。区间为 Tango 95%，每个都只描述那一对已实现的 Skill。

**表 1　配对研究：同一 rollout 喂两个更新器分支——S 只给 pass/fail，M 给修复后的诊断包；都不经选择直接在留出集上评测**（包：c＝证据交付修复；d＝c＋可放大训练子集；e＝再去掉 Rubric 句；g＝e＋通过案例对照）

| 阶段 | 域 | 包 | 种子 | 训练行 | 共同已知 | 父 | S | M | M−S 胜/负 | d [95%] | S−父 | M−父 | v9 | v10 | 调用 | tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rep1 | SearchQA | c | 06 | 128 | 241 | 171 | 196 | 203 | 11/4 | +0.029 [−0.003, +0.066] | +0.104 | +0.133 | 206 | 199 | 1401 | 3.13M |
| big1d | SearchQA | d | 06 | 256 | 144 | 91 | 112 | 119 | 12/5 | +0.049 [−0.008, +0.111] | +0.146 | +0.194 | 119 | 116 | 1362 | 3.72M |
| rep3 | SearchQA | e | 07 | 128 | 241 | 163 | 193 | 199 | 13/7 | +0.025 [−0.012, +0.065] | +0.124 | +0.149 | – | – | 915 | 1.99M |
| rep2 | SearchQA | e | 06 | 128 | 240 | 169 | 199 | 196 | 6/9 | −0.013 [−0.048, +0.021] | +0.125 | +0.113 | 202 | 198 | 1400 | 3.15M |
| rep4 | SearchQA | e | 08 | 128 | 240 | 164 | 191 | 195 | 10/7 | +0.013 [−0.023, +0.050] | +0.113 | +0.125 | – | – | 916 | 2.12M |
| ctl1 | SearchQA | g | 06 | 128 | 240 | 173 | 207 | 200 | 4/11 | −0.029 [−0.066, +0.003] | +0.142 | +0.113 | 209 | 197 | 1400 | 3.26M |
| brep1 | BigCodeBench | e | 06 | 128 | 242 | 122 | 122 | 125 | 16/13 | +0.012 [−0.033, +0.058] | +0.000 | +0.012 | – | – | 926 | 1.50M |

**表 2　选择研究与冻结基底的精修试验**（原生提案后在训练行上实测精确文本并选一个或弃权；sel1／bsel1 的基底是空 Skill，refine* 的基底是此前某次研究里未经选择的一步更新；“选择−基底”在弃权时是同文本重复，不是效应）

| 阶段 | 域 | 种子 | 第二步反馈 | 基底（父参照） | 原生候选 | 筛选的选择 | 选择通过数 | 原生−基底 胜/负 | d [95%] | 选择−基底 胜/负 | d [95%] | 调用 | tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sel1 | SearchQA | 06 | 诊断包 | 170 | 195 | candidate | 194 | 28/3 | +0.104 [+0.064, +0.153] | 32/8 | +0.100 [+0.051, +0.154] | 2014 | 4.03M |
| bsel1 | BigCodeBench | 06 | 诊断包 | 127 | 120 | drop_1 | 127 | 11/18 | −0.029 [−0.076, +0.016] | 16/16 | +0.000 [−0.048, +0.048] | 1802 | 2.63M |
| refine1 | SearchQA | 06 | 诊断包 | 195 | 199 | drop_3 | 202 | 9/5 | +0.017 [−0.016, +0.052] | 11/4 | +0.029 [−0.003, +0.066] | 2776 | 7.82M |
| refine2 | SearchQA | 06 | 诊断包 | 198 | 202 | 弃权（＝父文本） | 198 | 9/5 | +0.017 [−0.016, +0.052] | 5/5 | +0.000 [−0.030, +0.030] | 2775 | 6.25M |
| refine3 | SearchQA | 07 | 诊断包 | 207 | 205 | 弃权（＝父文本） | 205 | 8/10 | −0.008 [−0.046, +0.029] | 7/9 | −0.008 [−0.045, +0.027] | 2282 | 5.07M |
| refine3s | SearchQA | 07 | pass/fail | 202 | 209 | 弃权（＝父文本） | 201 | 12/5 | +0.029 [−0.005, +0.067] | 6/7 | −0.004 [−0.037, +0.028] | 2262 | 5.06M |
| refine4 | SearchQA | 08 | 诊断包 | 190 | 192 | 弃权（＝父文本） | 194 | 9/7 | +0.008 [−0.027, +0.045] | 7/3 | +0.017 [−0.011, +0.048] | 2292 | 6.04M |
| refine4s | SearchQA | 08 | pass/fail | 192 | 194 | 弃权（＝父文本） | 192 | 12/10 | +0.008 [−0.032, +0.050] | 4/4 | +0.000 [−0.028, +0.028] | 2275 | 6.54M |

**表 3　方法模式：一步更新后由决策规则 v2 在 fresh 96 题面板上决定 keep／park／revert**（m1、m2 为此前的快照 b，其余快照 h）

| 阶段 | 域 | 种子 | 反馈/更新 | fresh 父→候选（共同已知） | 胜/负 | 族级p | 回放 胜/负 | 决定 | 调用 | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| m1（10/10） | SearchQA | 06 | 诊断包/原生 | 66→79（95） | 13/0 | 0.00012 | 1/0 | keep | 440 | 0.93M |
| m2 | SearchQA | 07 | 诊断包/原生 | 68→78（96） | 11/1 | 0.0032 | 1/0 | keep | 438 | 0.94M |
| ms1 | SearchQA | 08 | 诊断包/筛选 | 65→79（94） | 16/2 | 0.00066 | 3/0 | keep | 1584 | 2.77M |
| sm06 | SearchQA | 06 | pass/fail/原生 | 69→84（96） | 16/1 | 0.00014 | 0/2 | keep | 422 | 0.92M |
| sm07 | SearchQA | 07 | pass/fail/原生 | 64→82（96） | 23/5 | 0.00046 | 2/1 | keep | 422 | 0.91M |
| sm08 | SearchQA | 08 | pass/fail/原生 | 64→77（95） | 16/3 | 0.0022 | 0/1 | keep | 422 | 0.91M |
| sm09 | SearchQA | 09 | pass/fail/原生 | 69→82（96） | 15/2 | 0.0012 | 1/1 | keep | 421 | 0.88M |
| sm10 | SearchQA | 10 | pass/fail/原生 | 65→82（96） | 18/1 | 3.8e-05 | 1/1 | keep | 421 | 0.91M |
| m1（10/10） | BigCodeBench | 06 | 诊断包/原生 | 48→49（96） | 5/4 | 0.5 | 1/2 | park | 434 | 0.48M |
| m2 | BigCodeBench | 07 | 诊断包未送达，回退标量/原生 | 48→49（96） | 5/4 | 0.5 | 2/2 | park | 422 | 0.51M |
| bsm06 | BigCodeBench | 06 | pass/fail/原生 | 53→48（96） | 4/9 | 0.95 | 3/3 | park | 422 | 0.43M |
| m1（10/10） | KOR-Bench | 06 | 诊断包/原生 | 64→69（93） | 11/9 | 0.75 | 4/1 | park | 399 | 2.11M |

**能说的（措辞经 Codex 综合审查收窄）**

1. **SearchQA 上一步未经选择的更新是有效的，而且只给 pass/fail 就够了。** 128 个训练行、pass/fail 反馈的一步更新，在已完成的各条历史（三个种子）里比空 Skill 高 10.4–14.2 个百分点；在有参照的四次里与带验证集门控的 main_v10 大体相当、比标签反馈＋验证集门控的 skillopt_v9 低 0.8–4.2 个百分点（其中一次区间不含 0）。“等价”与“去掉验证门的贡献”都没有建立。
2. **诊断（验证）包相对 pass/fail 反馈的增量没有建立，等价也没有建立。** 六次 SearchQA 比较 +0.029、+0.049、+0.025、−0.013、+0.013、−0.029（跨包版本与训练行数，只有 ctl1 带通过案例对照），每个区间都含 0；BigCodeBench 一次 +0.012。诊断器的答案形式假设确实进入了 M 的 Skill（内容传播成立），它对准确率的因果贡献没有证据。
3. **精修增益没有建立。** 六次冻结基底试验里“原生第二步−基底”为 +0.017、+0.017、−0.008、+0.029、+0.008、+0.008；筛选选中 1 次（选择−基底 +0.029；相对原生第二步只多 +0.013）、弃权 5 次。训练行上的筛选不能证明单条编辑可泛化的贡献；本轮 128 行的筛选未能确立这一量级（2–3 个百分点）的增益。六次试验已报告用量小计 36,777,773 tokens（41 次调用缺 usage）。
4. **BigCodeBench：被测的 Skill 没有一个在留出集上显示出相对空 Skill 的可靠提升**（10/10 以来的七条历史：x4、y2、m1、m2、bsel1、brep1、bsm06）。bsel1 里筛选 v1 选中的变体与父持平，而原生候选的点估计是 −2.9 个百分点——保护作用与原生候选的损害都没有建立。已执行的检查在失败产物上多数通过，说明现有检查的判别力弱，不证明公开契约永远支撑不了有用的检查。
5. **决策规则 v2 的行为与设计一致。** SearchQA 八个方法模式阶段（五个种子，三种反馈/更新组合）全部 keep，BigCodeBench 三次、KOR-Bench 一次都是 park（其中 bsm06 的候选比父低 5 题）。这是规则在复用的开发数据上的决定；它使用固定保留的开发挑战池，不占用规范 val 划分，但在功能上仍是类验证的数据使用。
6. **Research 在裁判域按现行路由不可达、在 BigCodeBench 上极少被触发**（假设层面声明的事实需求从不触发它；白名单只有标准库文档），它对 Skill 表现的贡献没有建立。

**工程上确实修好的（不等于带来了准确率）**：被丢弃的裁判判定、长题面截断、未被假设引用的案例、Rubric 句泄漏进 Skill、超长字段丢掉整份诊断、探针的若干格式损耗；新增并在真实运行里演练了组合感知筛选、弃权与通过案例对照；按族读数脚本已就绪，等 KOR-Bench 结果时第一次使用。**仍未修的健全性弱点**：引文只校验“是题面子串”，引文与期望是否相关依赖有限盲审；模型主动返回空探针的案例没有检查。

**由此得到的优先级判断（不是已证明的瓶颈）**：反馈内容的加码没有显示出边际收益；更要紧的是确认“一个固定的优化器”是否在多个域上都产生有用的增益。建议的次序：(1) 把策略**冻结成唯一一个**——默认“pass/fail 一步更新＋决策规则 v2，不开筛选”，事先写明种子、预算、对比与信息权限；(2) 在此之后才做一次 test 读取（此前的 test 结果已经影响过开发，所以它是对 v11 的前瞻评测，不是天然纯净的独立确认；需负责人批准）；(3) 增加事先选定、从未用于开发的域，并保留 BigCodeBench／KOR-Bench 的结果而不是只挑有利的域；(4) “在训练行上用评分器执行答案形式探针”是另一种信息制度（接近标签反馈），放在最后单独决定。诊断与精修保留为未证明的可选组件。

**KOR-Bench 配对研究 krep1（07:55–10:50 完成；快照 g，种子 06，GLM-5.3 low；743 次调用、3.43M tokens；读数约定见 §10）**：留出＝整个保留池 200 题（20 条训练步未见的规则 × 10 题），三方全部共同已知。通过数：空 Skill 142、pass/fail 分支 156、诊断分支 153。按规则族的主读数（族等权均值、t 区间、非持平族符号检验）：

| 对比 | 族均值差 [t95] | 改进/退步/持平族 | 符号检验 p | 题级 胜/负（只作描述） |
|---|---|---|---|---|
| 诊断 − pass/fail | −0.015 [−0.050, +0.020] | 4/7/9 | 0.549 | 7/10 |
| pass/fail − 空 Skill | +0.070 [−0.013, +0.153] | 9/2/9 | 0.065 | 24/10 |
| 诊断 − 空 Skill | +0.055 [−0.014, +0.124] | 8/3/9 | 0.227 | 22/11 |

读法：一步未经选择的 pass/fail 更新在未见规则上观察到 +7.0 个百分点，但按族区间含 0——增益仍未确立（一条历史、复用的开发池、父参照在两个分支之后运行）；题级的显著性不能盖过按族的主读数。诊断增量 −1.5 个百分点 [−5.0, +2.0]，没有建立——至此八次比较（SearchQA 六次、BigCodeBench 一次、KOR-Bench 一次）区间全部含 0。诊断日志：16 个案例全部得到 2 条判定，无格式损耗；但指派的 16 个通过案例对照只有 2 个被判定——KOR 的假设按规则类别划分，跨类别对照按其性质不适用（判定模型没有硬判）；起对照作用的是诊断器自己挂上的同规则通过案例（8 个，1 个被判 fail）。

## 12. 10/11 下午：负责人答复后的安排（进行中）

**负责人的四点答复**：(1) 倾向不把方法冻结成“pass/fail 一步＋决策 v2”，除非它确有更好的泛化表现；(2) 批准一次 test 读取，但留出性不能被质疑；(3) 可以换/加数据集，五个域都可尝试；(4) 允许评分器执行的答案形式探针，但最好不削弱“基本不需要验证集”的说法。Codex 方向审查（第 5 次）：先做“只用训练行做决定”的证伪试点；Sheet/ALF 接线与答案形式探针后置；规范 test 因历史暴露不能单独承担“不可质疑”。

**新增：训练行影子读数（快照 i；默认关闭，生效的决定不变）**。`prepare` 时加 `--limit train_panel_rows=N`：候选冻结后从训练步的整个任务名单里不看结果地抽 N 行（按步族分层轮转，含步内 unknown 的行），父与候选都重解（与回放/局部修复重合的位置复用其评测，每题每个 Skill 只解一次）；结果里记录与 fresh 相同口径的按族配对摘要，决定记录里记录 `in_sample_shadow`——把规则 v2 的表原样套在训练面板上会得到的动作，以及在 fresh 抽样顺序前 n 个位置上的等规模读数。抽样种子取“去掉可选限额后的清单哈希”，所以 fresh 面板不随是否加面板而变；运行前重建并逐项比对面板。Codex 代码审查两轮（第一轮 4 项 must-fix 全部修复）后 ACCEPTABLE；v11 测试 60 通过，更宽回归 564 通过/17 跳过。约定：[设计备忘](handoff/active-evidence-in-sample-shadow-design-20261011.md)。**这是证伪试点**：影子 keep 而保留池不 keep、或训练行效应明显高于 fresh，都算对“只用训练行”不利；一致并不足以把规则换掉。

**两份零调用分析（账本 10/11 14:45、14:55）**：
- *SearchQA 留出集上失败的构成*：空 Skill 的失败约八成是“EM 失败但规范化后与参考答案互为子串”（占全部题目 21–25%；不能直接等同于纯形式失败）；pass/fail 一步更新后这一类降到 8–12%，标签反馈的 v9 仍有 7–9%。即 +10–14 个百分点伴随着这一类失败的大幅减少，与“回答的书写形式贴近精确匹配惯例”相容；但这些是边际计数，不能确认逐题的修复机制与新题上的泛化，也不能排除内容/推理的变化；残余失败的成因与可修复性尚未检验，这个比较也不能估计或限制尚未测试的答案形式探针的增益。
- *训练行 vs 留出集（既有封存记录）*：昨夜九个筛选阶段都在全部 128 个训练行上测了“原生候选−父”。第一步更新在训练行与留出集上同号且量级接近（SearchQA sel1 +0.13 对 +0.10；BigCodeBench −0.02/−0.04 对 −0.03；ms1 的留出一列测的是筛选选中的另一份文本，只能说同号），第二步精修两边都是噪声量级；没有出现“训练行显著为正而留出为负”。事后读取，不是前瞻验证。

**两份未执行的文档**：[一次前瞻留出读取的协议草案](handoff/active-evidence-prospective-holdout-protocol-draft-20261011.md)（规范 test 只能作披露历史后的次要评测；候选的主留出集是 BigCodeBench/KOR-Bench 的 reserve 分区与一份新的 SearchQA 样本；10/11 的暴露审计在已检索材料里未发现 reserve 的求解记录，提示层面的暴露尚未排除（调用缓存正文未读），BigCodeBench 有 4 题曾显示给调研子代理、须剔除；一次读取同时评多个事先写明的策略臂，不必先把方法冻结成一个臂）；[SpreadsheetBench/ALFWorld 接入 v11 的改动清单](handoff/active-evidence-sheet-alf-wiring-notes-20261011.md)（pass/fail 臂可接、诊断臂暂不可；两域开发面板只有 80/39 题，留给保留池的题很少、规则 v2 功效有限但不必然 park，本轮后置）。

**下午的运行**：ksm07（KOR-Bench 方法模式，pass/fail，种子 07，快照 h）14:11 启动、15:00 由操作者取消（KOR 方法模式一次约 3 小时，会堵住更短的试点；部分记录保留、不续跑、不是结果）。影子试点（快照 i；pass/fail、一步、原生、方法模式）：第一步 SearchQA sh11–sh13（64 行面板）与 sh14–sh16（全名单 128 行面板，16:15 事后追加）、BigCodeBench bsh07–bsh10（64）与 bsh11（128）；**第二步** SearchQA s2sh06/06r1/06c1/07/08（父＝昨夜 rep2/rep1/ctl1/rep3/rep4 的 pass/fail 一步 Skill；15:10 起在第一个结果之后追加，Codex 方向检查 GO）；KOR-Bench ksh08 排在最后。次序与追加都记在设计备忘里。

**表 4　影子试点的逐次结果**（生成自封存记录；逐行表与完整读法在[账本](results-and-lessons.md) 10/11 15:00 条）。17 条历史在 21:26 全部完成（公开导出 [fivebench-active-evidence-20261011b.json](results/fivebench-active-evidence-20261011b.json)：这 17 个阶段与 KOR-Bench 研究 krep1，只含计数、哈希与决定）：

| 设置 | 历史数 | 生效 keep／影子 keep | 生效 keep／影子 park | 生效 park／影子 park | 生效非 keep／影子 keep |
|---|---|---|---|---|---|
| SearchQA 第一步，面板 64 | 3 | 2 | 1 | 0 | 0 |
| SearchQA 第一步，面板 128（全名单） | 3 | 3 | 0 | 0 | 0 |
| SearchQA 第二步，面板 64 | 5 | 0 | 1 | 4 | 0 |
| BigCodeBench 第一步，面板 64 | 4 | 0 | 0 | 4 | 0 |
| BigCodeBench 第一步，面板 128（全名单） | 1 | 0 | 0 | 1 | 0 |
| KOR-Bench 第一步，面板 45 | 1 | 0 | 0 | 1 | 0 |

读法（描述性）：试点要找的反例——训练行说 keep 而保留池不 keep——17 条历史里 0 次；相反方向 2 次（64 行面板里步内失败的行只有 10 和 7 个，3 胜 0 负够不到阈值）；四条全名单 128 行面板的历史（SearchQA 三条 keep／keep，BigCodeBench 一条 park／park）都与保留池一致；训练面板与 fresh 的净胜率差 17 次里 10 次为负，没有看到系统性的训练行乐观。KOR-Bench 的 ksh08 两边都 park：fresh 64→70/96（95 题共同已知，10 胜 4 负；20 条规则族平均差 +0.057，t 区间 −0.025 到 +0.140，单侧族级 p=0.17），训练面板 1 胜 5 负（45 题）——fresh 上的方向与 krep1 一致、同样未达阈值，不是独立确认。这**不等于**验证了“只用训练行做决定”：各域可能只是在重复本来的走向，fresh 的决定本身也是有噪声的开发证据；要换规则需要新版本，并在三种策略（只用训练行／保留池／不设门）都没用过的数据上做前瞻比较（见留出读取协议草案的 P4）。附带观察：第二步在方法模式下被规则 v2 保留了 1 次（s2sh07：76→84/96），“多步＋逐步决定”的增益仍未建立。

**10/11 晚新增：机制读数与“通用指令”对照（进行中；第一条结果见下一段）**。零调用读数（账本 10/11 19:10）：KOR-Bench 的 krep1 里，pass/fail 分支相对空 Skill 净增的 14 题有 11 题在 logic 类（19→30/40），该类每题平均推理 token 从 133 升到 761；SearchQA 上带 Skill 后回答变短、三臂每题推理 token 都只有 2–11 个。v11 至今所有比较的参照都是空 Skill，从未有过通用指令对照。于是：快照 j（＝i＋阶段工具的 `--reference name=f:<文件>`，包不变）把三段固定的手写通用指令作为只评测的具名参照放进配对研究（[设计备忘](handoff/active-evidence-generic-control-design-20261011.md)，Codex 两轮后 ACCEPTABLE）；队列 t1 于 19:14 排在 ksh08 之后：SearchQA gen17／gen18、BigCodeBench bgen12（各三个参照），KOR-Bench krepg2–krepg4（参照 `generic`；同时是 krep1 的三条新历史，读数约定见 [KOR 研究备忘第 4 节](handoff/active-evidence-kor-study-design-20261011.md)）。读数脚本：[对照汇总](handoff/active-evidence-control-summary-20261011.py)、[KOR 汇总](handoff/active-evidence-kor-pooled-20261011.py)。“pass/fail 分支−通用指令”比较的是两份文本，不是“在通用指令之上再学习能多得多少”；结果出来前不下任何结论。留出读取协议草案已加入通用指令臂 PG。

**通用指令对照的第一条结果（SearchQA gen17，21:41；留出 242 题、各臂共同已知 240；逐项数字在[账本](results-and-lessons.md) 10/11 21:41 条）**：

| 臂 | 字节 | 通过 | 相对空 Skill（Tango 95%） |
|---|---:|---:|---|
| 空 Skill | 0 | 169 | — |
| 通用指令 `generic`（三行） | 416 | 187 | +0.075［+0.036, +0.121］ |
| `generic_form`（只有答题形式一行） | 173 | 184 | +0.062［+0.031, +0.103］ |
| `generic_reason`（只有逐步推理、严格按规则两行） | 264 | 168 | −0.004［−0.039, +0.030］ |
| pass/fail 分支（从空 Skill 学一步） | 4,251 | 198 | +0.121［+0.076, +0.173］ |
| 诊断分支（从空 Skill 学一步） | 4,575 | 191 | +0.092［+0.039, +0.147］ |

pass/fail 分支−通用指令 +0.046［+0.005, +0.090］（18 胜 7 负），诊断分支−通用指令 +0.017［−0.028, +0.063］。读法（按备忘事先写定的规则）：这一条历史上，一步更新相对空 Skill 的增益里约六成用一段不含数据集信息的三行手写指令就能拿到，而且几乎全部来自“按要求的形式、尽量短地作答”那一行；学到的 Skill 在通用文本之上还多 4.6 个百分点，区间下端贴近 0。只有一条历史，不成立等价，也不说明学习无用；通用文本是读过一份学到的 SearchQA Skill 之后写的“知情的平凡基线”。**此后凡是“学习有增益”的说法都要同时对着通用指令基线报告。** gen18 在任何更新之前停止（诊断器的假设列表两次未通过“全有或全无”校验；没有留出结果、不续跑），替补 gen19（种子 20261019）已排队。 **BigCodeBench（bgen12，22:33；留出 242 题全部共同已知）**：空 Skill 121、pass/fail 分支 124、诊断分支 123、`generic` 122、`generic_form` 117、`generic_reason` 127；通用指令−空 +0.004［−0.035, +0.044］，pass/fail 分支−通用指令 +0.008［−0.036, +0.054］，全部区间含 0，与事先写下的预期一致（没有等价结论）。

**后续研究：从通用指令出发再学一步（结果见下一段）**。上面的“pass/fail 分支−通用指令”比较的是两份备选文本；“学习在通用指令之上还能加多少”需要以通用指令为父。快照 k（＝j＋阶段工具的 `--parent f:<绝对路径>` 与 `--reference name=none`；包不变，Codex GO，71 项测试通过）下的 fg17／fg19（SearchQA；与 gen17／gen19 同一批训练行；父＝`generic`；参照＝空 Skill 与对应 gen 阶段的 pass/fail 分支），主对比是“pass/fail 分支−父（通用指令）”。[设计备忘](handoff/active-evidence-from-generic-design-20261011.md)在任何对照结果出来之前写定。

**10/12 上午：夜间对照队列的结果（逐项在[账本](results-and-lessons.md) 10/12 09:30 条）**。

| 域／阶段 | 空 Skill | 通用指令 | 从空白学一步（pass/fail） | 通用指令−空 | 学到的−通用指令 |
|---|---:|---:|---:|---|---|
| SearchQA gen17（240 题） | 169 | 187 | 198 | +0.075［+0.036, +0.121］ | +0.046［+0.005, +0.090］ |
| SearchQA gen19（240 题） | 168 | 190 | 197 | +0.092［+0.055, +0.137］ | +0.029［−0.012, +0.073］ |
| BigCodeBench bgen12（242 题） | 121 | 122 | 124 | +0.004［−0.035, +0.044］ | +0.008［−0.036, +0.054］ |
| KOR-Bench krepg2（20 条规则） | 155 | 149 | 153 | −0.016［−0.074, +0.042］ | +0.006［−0.054, +0.066］ |
| KOR-Bench krepg3（20 条规则） | 153 | 150 | 151 | −0.017［−0.096, +0.061］ | +0.005［−0.064, +0.074］ |

（SearchQA、BigCodeBench 为 Tango 区间；KOR-Bench 为按规则族的 t 区间。）从通用指令出发再学一步（fg17，SearchQA）：pass/fail 分支−父（通用指令）**+0.029［−0.011, +0.072］**，未建立；同一批训练行上它比“从空白学到的 Skill”低 0.037［−0.078, −0.002］（探索性）。KOR-Bench 的 pass/fail−空在三条历史上为 +0.070、−0.010、−0.014，规则聚类合并 +0.033［−0.013, +0.079］：krep1 的增益没有复现；logic 类上 Skill 仍让求解器多推理，但正确率没有随之提高。gen18、fg19（诊断假设列表校验）与 krepg4（调用未送达）在任何更新之前停止，没有结果。**小结：在现有三个域、这个求解器和 242 题量级的留出集上，“从任务经验学习”相对“一段合理的初始指令”的增量没有任何一处被建立；这是“未建立”，不是“已证明没有”（242 题只能分辨约 5–6 个百分点以上的差）。** 外部专家的反馈与据此整理的下一步工作包未公开（含第三方文字；计划尚待负责人确认）。

## 13. 10/13：在新题上的主读数与提示词档位（逐项分母、区间与局限见[账本](results-and-lessons.md) 10/13各条）

**从合理初始指令学习还剩多少**（SearchQA，975道新题，20个臂；[设计备忘](handoff/active-evidence-learn-from-b-design-20261012.md)）：

| 对比 | 估计 | 保守交叉区间（单文本对为题目级区间） | 结论（事先写定的规则） |
|---|---|---|---|
| 零样本指令 bzero − 空 | +0.134 | ［+0.111, +0.157］ | 一份不看任务结果的指令即有 +13 个点 |
| 从空学一步 `le` − 空 | +0.130 | ［+0.099, +0.160］ | 成立 |
| `le` − bzero | −0.005 | ［−0.023, +0.012］ | 与零样本指令持平 |
| P1：从 bzero 学一步 `lz` − bzero | +0.001 | ［−0.016, +0.018］ | 缺失结果界上限 +0.032，按规则记“缺失条件下未分辨”；估计即零 |
| P2：从手写三行指令学一步 `lh` − bhand | +0.049 | ［+0.020, +0.078］ | 成立（较弱的初始指令被补到同一水平） |
| 原 v10（验证集门控）− bzero | +0.001 | ［−0.013, +0.016］ | 未见差别 |
| SkillOpt v9（验证集门控）− bzero | +0.010 | ［−0.005, +0.026］ | 未见差别 |
| `le` − SkillOpt v9 | −0.016 | ［−0.034, +0.003］ | 未分辨，方向为负 |

各种做法都落在 0.82–0.85：在这个数据集与求解器上，一步学习相对零样本指令的增量为 0±2 个百分点。

**分析者提示词档位 `generalize_v1`**（同种子同训练题，250 道新题，四条配对历史；[设计备忘](handoff/prompt-chain-design-20261013.md)）：新档位−原提示词 +0.027，四个种子全为正（+0.036、+0.012、+0.008、+0.052），Skill 短约三成；交叉区间［−0.017, +0.071］含 0，按事先写定的规则**未分辨**；新档位−bzero +0.016（［−0.038, +0.070］）未分辨。要分辨 2–3 个点需要更多历史；只在 SearchQA 上测过，代码与规则任务未跑。**确认实验（10/13 下午，8 个新种子、750 道新题，只用新种子）**：新档位−原提示词 **+0.004**（交叉区间［−0.008, +0.015］），首轮的 +2.7 没有复现；新档位−bzero +0.001。准确率上没有可测增益，Skill 在准确率不变的前提下短约三分之一（2.5–3.7 KB 对 3.9–6.2 KB）。

**与方法走向的关系**：负责人 10/13 指示回到 Rubric＋Research 版本并以生成的测试任务代替验证集，该方向的实现与结果在[流程文档](current-workflow.md) 10/13 段与[账本](results-and-lessons.md) 10/13 条；本文件描述的 v11 一步流程此后主要作为产生学习历史与对照的工具使用。
