# 论文基线：现有数字清单、记忆方向候选与运行手册（2026-11-03）

> 用途：论文 Baselines 一节的底稿和执行手册。本文件只整理**已经打开**的数字、候选方法和准备步骤；
> **没有新的测试读数，没有付费调用**，所有花费都是估算，冒烟后要用实测替换。
> 口径：当前五个 bench 的留出测试面板 SearchQA 400、OfficeQA 172、ZebraLogic 200、SpreadsheetBench（表格题）204、
> ALFWorld 134 局；两条解题链 G = GLM-5.3、D = deepseek-v4-flash（northgate）；每题每组只读一次。
> B = 空白（No-Skill，与路线 A 的 No-Skill 提示相同）；C = 冻结的零样本指令卡（instruction-only，
> `execskill-v29/docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json`）；F = 链末程序包 + 指令卡（route B 主方法）。

## 0 结论先行

- **B、C**：两条链、五个 bench 都有同一面板上的 3–4 次独立读数（main-v5、implant-v5、cross-v5，D 链另有 main-v6），
  另有 main-v4（四个 bench）、baseline-v210（三个 bench）的更早读数。ZebraLogic 的 C 按构造等于 B（外壳不发卡）。
- **route B 主方法 F**：G 链只有 main-v5（四个学习步都没留下程序，只有导入的 ALFWorld 包起作用）；D 链有 main-v6
  （自己学出的 ZebraLogic 求解器 +10.0 分）。main-v6 G 链还在跑，数字未开。
- **SkillOpt、GEPA**：只在 G 链（GLM-5.3）、路线 A 外壳 coevo5 v1（10/19）上有 SearchQA、OfficeQA、表格题、ALFWorld
  四个 bench 的数字；**D 链完全没有；ZebraLogic 两条链都没有**；而且 coevo5 v1 不是 route B 的同一把尺（§1.1 注 †）。
- 更早的 10/06 五域数字（BCB/Sheet/QA/KOR/ALF）里 SearchQA、ALFWorld 用的是同一份面板文件，但学习顺序、外壳不同，只能当旁证。
- **记忆方向基线一个都没有**。推荐跑 **ExpeL**（同时读它的 retrieve-only 臂，即 kNN 示例记忆）和 **Dynamic Cheatsheet**
  （冻结的 DC-Cu），第三个可选 **AWM**；Reflexion 不适用（要在同一道测试题上重试），Voyager 式技能库当作 route B 去掉验收门的消融，
  MemoryBank / A-MEM 不跑。
- 评测一律走 route B 的读数外壳：同一 solver 请求格式、同一评分器、同一面板，每次读数在同一运行里重读 C 做配对。
  记忆文字只放进卡片位（system 里的 guidance 段），**不走 procedure notes**（词表筛查会拦答案与代码块）。
- 估算花费：第一档（C、ExpeL、DC 两条链 + G 链重读 coevo5 v1 的 GEPA/SkillOpt Skill）约 1.0–1.3 亿 token；
  第二档（kNN、AWM、B）再加约 0.5–0.6 亿；GEPA/SkillOpt 补 ZebraLogic 与 D 链另计（0.1–2 亿，看范围）。
- 今晚只做零调用准备：核对面板哈希与 GLM 参数是否一致、抽出 coevo5 v1 冻结 Skill、清点可复用训练轨迹、写登记简报、让 Codex 写代码与离线测试。

## 1 现有数字清单

### 1.1 当前五个测试面板上的答对题数

读数代号（都是只读提取、经负责人同意打开）：m5 = main-v5（账本 11/01 02:46；[亮点](../results-highlights.md) §1.2、§1.7）；
i5 = implant-v5（11/01 12:08；§1.1、§1.7）；x5 = cross-v5（11/03 07:52；§1.1b，[cross5-table.md](../handoff/cross-v5-readout-20261103/cross5-table.md)）；
m6 = main-v6 D 链（11/03 15:5x；§1.2b，[m6-D-table.md](../handoff/main-v6-readout-20261103/m6-D-table.md)）；
m4 = main-v4（10/31 03:05；§1.3）；b210 = baseline-v210（10/30 11:0x；§1.6）；
c1 = 路线 A 五 bench 协同进化第 1 版（10/19 10:52；§2.1，[coevo5-v1-results](../handoff/coevo5-v1-results-20261019.md) §3.2、§3.5）。
B、C 行里 G 链按 m5·i5·x5、D 链按 m5·i5·x5·m6 排列，括号里是更早的读数。

| 方法 | 链 | SearchQA /400 | OfficeQA /172 | ZebraLogic /200 | 表格题 /204 | ALFWorld /134 |
|---|---|---|---|---|---|---|
| B No-Skill | G | 299·290·301（m4 293，b210 289） | 53·53·50（m4 51，b210 52） | 149·139·145（= C） | 123·129·131（m4 129） | 121·122·120（m4 119，b210 120） |
| B No-Skill | D | 260·260·257·256（m4 258，b210 261） | 25·25·30·25（m4 26，b210 28） | 167·162·163·165（= C） | 130·128·130·129（m4 127） | 69·67·59·63（m4 67，b210 68） |
| C instruction-only | G | 334·337·341（m4 334，b210 333） | 84·81·79（m4 84，b210 82） | = B（外壳不发卡） | 139·150·131（m4 137） | 123·118·123（m4 120，b210 122） |
| C instruction-only | D | 329·329·329·327（m4 333，b210 327） | 54·54·59·51（m4 54，b210 49） | = B | 119·120·119·120（m4 121） | 92·89·91·88（m4 91，b210 93） |
| SkillOpt | G | c1 347（S1 352）† | c1 86（S1 82）† | 无 | c1 121/200（S1 114/194）† | c1 121（S1 123）† |
| SkillOpt | D | 无 | 无 | 无 | 无 | 无 |
| GEPA | G | c1 356 † | c1 83 † | 无 | c1 108/195 † | c1 116 † |
| GEPA | D | 无 | 无 | 无 | 无 | 无 |
| route B F（方法） | G | m5 340（请求与 C 相同） | m5 78（同） | m5 149（没学到）；m6 G 未开 | m5 133（同） | m5 128（导入 alfworld-v11 包） |
| route B F（方法） | D | m6 327（复用 C 格） | m6 51（复用 C 格） | m6 185（自学求解器，+10.0） | m6 120（复用 C 格） | m6 112（导入包，+17.9） |

注：
- † c1 的 SkillOpt 链末 Skill = 第 3 步（LiveMath 步）的 15,177 字节；S1 = 第 1 步（SearchQA）的 7,526 字节，第 2 步停在输入超长、沿用 S1；
  GEPA 只在第 1 步更新（4,325 字节），之后四步沿用。c1 与 route B 的测试面板来自同一来源（`skillopt/coevo5/data.py` 的 `DEV_MACHINE["test"]`
  与 OfficeQA 上游题号；逐文件哈希待 §4 P0 核对）、同为 GLM-5.3（求解参数逐项待核）、同一种"Frozen skill guidance"放法，
  **但不是同一把尺**：c1 的表格题按已知口径（去掉未知格，分母 194–200），route B 把 C/B 的未知格记对；route B 的排版是 contract-first-v2
  （格式句在 Skill 前，表格题合同也改过），c1 是第 1 版排版；读取时间 10/18–19；c1 的"指令"参照 I-glm 是五份卡合成一份 12 KB Skill
  （349、85、142/197、119），与 route B 的 C（只看本 bench 的卡）不是同一请求。c1 空白参照：290、50、125/199、119。
- 同一文字重读的波动不小：D 链 ALFWorld 的 B 在 59–69、C 在 88–96 之间（含 alfworld-v10、v11 的 92、96）；所以任何新臂都要在同一运行里配对 C。
- 不列入方法行的上界读数（事后挑选的程序）：i5 F G 341、80、157、132、128，D 328、44、188、116、112；
  ZebraLogic v3r4 单读（10/30 18:27）D F 188 对 C 165。另：alfworld-v11 单步（10/29）D F 112 对 C 96 是方法结果，F 行 ALFWorld 列导入的就是它的包。

### 1.2 只在旧面板或旧 bench 上存在的数字

| 来源 | 内容 | 能不能直接用 |
|---|---|---|
| 10/06 五域 test（账本 10/6 07:43；亮点 §3；[F 报告](../fivebench-f-skillopt-gepa-20261003.md)；`docs/results/fivebench-test-eval-20261006.json`） | GLM-5.3 low，按 BCB→Sheet→QA→KOR→ALF 学习。No-Skill：QA 291/400、Sheet 133/279（U93）、ALF 120/134；SkillOpt 最终 S4：338、134（U94）、121；GEPA 最终 S4：338、115（U97）、122 | 旁证。SearchQA、ALFWorld 面板就是现在的文件（`/root/fivebench-test-eval-20261005-h/panels/`），Sheet 是 279 题全集（现在的 204 是通过参考工作簿资格检查的子集）；学习顺序含 BCB、KOR，外壳是冻结评测 v8 |
| LiveMath 125 题（已被 ZebraLogic 替换） | c1：空白 50、指令 45、SkillOpt 53、GEPA 48；m4：G C 42 / B 52，D C 50 / B 40；b210：G C 47 / B 50，D C 49 / B 43 | 不是当前 bench |
| coevo5 第 3 版 deepseek（NoSkill-ds、I-ds、E-ds，10/19–20） | 测试集读过但**从未打开**；经 PJLAB 令牌接口的 deepseek，不是 northgate；含 LiveMath，无 ZebraLogic | 不能当 D 链数字 |
| 10/13–10/16 OfficeQA/LiveMath 扩展研究 | 只用开发/验证块；OfficeQA 172 道测试题在那里从未渲染 | 没有测试数字 |

### 1.3 缺口

1. ZebraLogic × {SkillOpt, GEPA} × {G, D}：没有。
2. D 链 × {SkillOpt, GEPA} × 五个 bench：没有（账本 10/19 12:50："SkillOpt、GEPA 只在 GLM 上跑过"）。
3. G 链 SkillOpt/GEPA 在 route B 尺子上的读数：没有；而且 c1 第 3 步是 LiveMath，与当前顺序（SearchQA → OfficeQA → ZebraLogic → 表格题 → ALFWorld）
   一致的只有第 1–2 步（SkillOpt S1 = S2，GEPA S1 = 链末）。
4. route B G 链学习后的 F（main-v6 G，第 3 步已收下 Zebra 求解器）：等链结束、经负责人同意再开。
5. 记忆方向基线：没有。
6. ZebraLogic 上"指令"等于 No-Skill；文字/记忆类基线要在 ZebraLogic 上起作用，外壳得给新臂加一个卡片位（§3.1）。

## 2 记忆方向候选

### 2.1 我们的设定（硬约束）

(a) 只从该 bench 的练习池学（route B 练习池；测试面板只由同意书下的读数单元打开）；(b) 每道测试题每组只答一次，测试时没有标签、没有重试；
(c) 不设可反复使用的验证集做挑选（方法自身设计要用的挑选集只能从练习池切，并写明）；(d) 同一评分器，solver 固定（G = GLM-5.3，D = deepseek-v4-flash/northgate），
方法侧角色用 GLM-5.3（与 route B 工程师一致）；(e) 持续设置：按 SearchQA → OfficeQA → ZebraLogic → 表格题 → ALFWorld 累积，
链末记忆在五个测试面板上各读一次（与 F 同口径），记忆是五个 bench 合在一起、每条带 bench 标签的一份（与 coevo5 I-glm 五分区的先例一致，能测跨 bench 损害）。

### 2.2 逐个候选

**ExpeL（Zhao 等，2024）**。方法：在训练任务上用 Reflexion 式多次尝试收集成功与失败轨迹；用 LLM 对比同一任务的失败/成功轨迹、以及成批的成功轨迹，
以"增、改、赞同、反对"操作维护一份带计数的 insights 列表；评测时把 insights 拼进提示，再按任务相似度检索 top-k 条成功轨迹作示例，测试题只做一次。
原文环境含 ALFWorld 与 HotpotQA，正好对应我们的 ALFWorld 和 SearchQA。映射：存 = 每 bench 的 insights（每 bench ≤2,000 字符，合并 ≤4,000）
+ 成功轨迹池（练习题公开文本摘要 + solver 自己答对的回答；ALFWorld 为动作序列）；每题 = 用本题公开文本（题面、表格题指令、ALFWorld 目标句）
对轨迹池做 BM25，取 top-2（ALFWorld top-1）；提示 = 卡片位里"指令卡 + Insights 段 + Similar solved examples 段"。
成本：建库每链约 5–6M（复用 route B run 批轨迹当第一次尝试，只给失败题补 2 次重试；insights 抽取约 30 次 GLM 调用/bench），读一遍每链 11–14M。
工作量：中（约 2 天 Codex 写 + 审）。**建议：跑（第一优先），同运行加读 retrieve-only 臂。**

**Dynamic Cheatsheet（Suzgun 等，2025）**。方法：推理时维护一份不断改写的 cheatsheet（可复用策略、代码片段、易错点），每答一题后由 curator 依据本题输入
和模型自己的回答改写，不用标签；变体 DC-Cu（累积）与 DC-RS（检索相似历史后每题合成）。映射：主版本 = **冻结 DC-Cu**：在练习流上
（SearchQA 200、OfficeQA 74、ZebraLogic 100、表格题 91、ALFWorld 60 局；按种子哈希排序，五个 bench 依次）逐题改写一份 ≤6,000 字符的 cheatsheet，
不读标签，流结束即冻结，测试时放卡片位，每题读一次。可选版本 = 测试流上在线 DC-Cu（仍每题一次、无标签，但用测试输入更新记忆，属转导设定，只能串行）。
它存代码片段，是与 route B 可执行程序最接近的"文字记忆"。成本：整理（串行）每链约 9M，读一遍每链 10–14M；在线版另约 15–20M/链。
工作量：低–中（1–1.5 天）。**建议：跑冻结 DC-Cu（第二优先）；在线版由负责人定。**

**Agent Workflow Memory，AWM（Wang 等，2024）**。方法：从成功轨迹归纳可复用的 workflow（带变量的子流程）放进记忆，指导后续任务；离线版从训练样例归纳，
在线版从测试流中模型自判成功的轨迹归纳；原文在 Mind2Web、WebArena。映射：离线版，与 ExpeL 共用同一成功轨迹池，GLM-5.3 按 bench 归纳
（ALFWorld 按 6 种任务类型），合并 ≤4,000 字符放卡片位，不做逐题检索。成本：归纳 <1M/链，读一遍 9–11M/链。工作量：低（0.5–1 天，复用 ExpeL 设施）。
**建议：第三个、可选**；对 ALFWorld 和表格题最自然，对 SearchQA/ZebraLogic 映射较弱。

**Reflexion（Shinn 等，2023）**。方法：同一任务失败后写自我反思存入情景记忆，下一次尝试读入；依赖同一任务的重试和成败信号。映射：测试时每题只读一次、没有反馈，
测试阶段不成立；只能在练习池上当 ExpeL 的收集步骤（已包含）。**建议：不单独跑，论文写明不适用的原因。**

**轨迹/示例检索记忆（kNN few-shot；KATE，Liu 等，2022；Synapse，Zheng 等，2024）**。方法：存已解样例（输入 + 正确输出或轨迹），每道新题按相似度检索 top-k 作示例。
映射：就是 ExpeL 去掉 insights 的 retrieve-only 臂（同一轨迹池、同一 BM25、同一格式）。成本：建库 0，读一遍 8–10M/链。工作量：低（随 ExpeL 实现）。
**建议：作为 ExpeL 的消融臂跑（第二档）。**

**Voyager 式可执行技能库（Wang 等，2023）**。方法：自动课程 + 迭代提示（执行错误、环境反馈、自我验证）写可执行代码技能，存进按描述嵌入检索的技能库。
映射：与 route B 最近——route B 的包就是程序库，区别是 Voyager 不做统计验收、自我验证通过就收、按描述检索；在本代码库里等于"route B 去掉 J1–J7 验收、改成自我验证即收"
的一个配置。成本：一条 route B 链的量级（30–40M/链）。工作量：高（要改训练循环）。**建议：不当外部基线，以后作 route B 的消融。**

**MemoryBank（Zhong 等，2024）、A-MEM（Xu 等，2025）、Mem0（2025）**。方法：面向长对话与个性化的长期记忆（遗忘曲线、Zettelkasten 式互链笔记与记忆演化）。
映射：在彼此独立的 benchmark 题上，它们退化成"写笔记 + 相似度检索"，与 ExpeL/kNN 的检索部分重合，独有机制（遗忘、链接演化、用户画像）在这里没有可检验的假设。
**建议：不跑，放相关工作。**

### 2.3 汇总

| 候选 | 存什么 | 每题检索 | 提示怎么变 | 建库/链 | 读一遍/链 | 工作量 | 建议 |
|---|---|---|---|---|---|---|---|
| ExpeL | insights + 成功轨迹 | BM25 top-2（ALF top-1） | 卡片位 = 卡 + insights + 示例 | 5–6M | 11–14M | 中 | 跑（1） |
| ExpeL retrieve-only（kNN） | 成功轨迹 | 同上 | 卡 + 示例 | 0 | 8–10M | 低 | 跑（消融，第二档） |
| Dynamic Cheatsheet（冻结 DC-Cu） | 一份 cheatsheet | 无 | 卡 + cheatsheet | ~9M | 10–14M | 低–中 | 跑（2） |
| AWM（离线） | workflows | 无 | 卡 + workflows | <1M | 9–11M | 低 | 可选（3） |
| Reflexion | 同题反思 | — | — | — | — | — | 不适用 |
| Voyager 式 | 可执行技能 | 描述检索 | 程序挂钩 | 30–40M | 6–9M | 高 | route B 消融 |
| MemoryBank / A-MEM | 对话笔记 | 相似度 | 卡 + 笔记 | — | — | 中 | 不跑 |

推荐理由：ExpeL 是"经验学习记忆"的标准基线，原文环境与我们两个 bench 重合，一次实现同时给出抽象记忆（insights，相当于 SkillOpt/GEPA 的文字规则）
和情景记忆（检索示例）两种对照；DC 不用标签、不用验证集、会存代码片段，是与 route B 程序最接近的文字记忆，也是审稿人会期待的新方法；
两者都与我们"不需要验证集"的故事线同口径（GEPA/SkillOpt 则要用练习池切出的挑选集），对比清楚。AWM 边际成本低，可补 ALFWorld/表格题的"流程记忆"一格。

### 2.4 推荐基线的分 bench 花费（每条链，百万 token，估算）

| 项 | SearchQA | OfficeQA | ZebraLogic | 表格题 | ALFWorld | 合计 |
|---|---|---|---|---|---|---|
| C 读一遍（登记锚点 `CELL_ANCHORS` 低–高） | 0.61–1.36 | 0.90–1.36 | 0.68–1.06 | 0.52–0.87 | 4.8–6.0 | 7.5–10.7（实测每组约 5–7） |
| ExpeL 建库（补收集 + 重试 + insights） | 0.5 | 1.0 | 1.0 | 0.6 | D 1.8 / G 3.1 | 4.9–6.2 |
| ExpeL 读（比 C 多） | +0.7 | +0.3 | +0.5 | +0.4 | +3.2–5.4 | +5.1–7.3 |
| kNN 读（比 C 多） | +0.3 | +0.1 | +0.3 | +0.2 | +1.2–2.0 | +2.1–2.9 |
| DC 整理 | 1.7 | 1.2 | 1.35 | 1.05 | 3.8 | 9.1 |
| DC 读（比 C 多） | +0.6 | +0.26 | +0.3 | +0.31 | +3.0–5.0 | +4.5–6.5 |
| AWM 归纳 / 读（比 C 多） | 0.1 / +0.4 | 0.1 / +0.17 | 0.1 / +0.2 | 0.1 / +0.2 | 0.3 / +2.0–3.4 | 0.7 / +3.0–4.4 |

估算依据：每格 token 按 route B 登记锚点（`protocol.py` 的 `CELL_ANCHORS`，ZebraLogic 在 `profiles.py`）；实测 implant-v5 读 F、C、B 三组 G 15.58M、D 16.99M；
ALFWorld 每局按 15–25 步、每步 system 都带记忆；记忆上限见 §3.1。ALFWorld 占读数花费的六成以上。

## 3 在本代码库里的实现方案

### 3.1 共用评测通路：route B 读数外壳

- **入口**（route B 开发树 `/data/execskill-dev-zpc`，本机 `<workspace>/execskill-v29`）：`scripts/run_execskill.py` 的
  `v214-{snapshot,selftest,s0,manifest,structural-smoke,smoke-run,smoke-summary}` + `run --manifest M --chain G|D`，加一个新的 `--configuration`；
  `skillopt/execskill/cells.py`（`Arm`、`_shell` 决定卡片文字）、`v219_read.py`（cross-v5 的卡片替换臂，新臂照它写）、`v218_read.py`（请求复用规划）、
  `readout.py`（登记的配对差与第二分析）、`instruction_start.py`（卡片 pin）、`profiles.py`（配置登记、读哪些 bench、`TEST_READ_CELLS`、上限）、
  评分在 `judge.py`、`zebralogic.score` 与表格题 q23 资格。操作脚本照 `/data/execskill-20261102-cross5-ops/x5-{env,prep,smoke,launch,run,go}.sh`。
- **请求**：包为空时 route B 外壳逐字节发冻结请求（`solver.py` 文档串）；卡片位 = `solver._system` 的 "Frozen skill guidance (use only where applicable):" 段，
  QA 与表格题是 contract-first-v2 排版，ALFWorld 每一步都带 system。把学到的 Skill 或记忆当卡片读，就是"同一外壳、同一请求格式、只换卡片位文字"。
- **不走 procedure notes**：notes 有词表筛查（`protocol.LEXICON_TERMS` 含 "answer"、"<answer"、"```"、"output"、"return"、"json"、"format" 等），示例与代码会被拦。
- **新臂**：`T_<名>` = 固定文字（卡 + 冻结记忆，或只有学到的 Skill）；`M_<名>` = 逐题文字（卡 + 冻结记忆 + 本题检索结果），检索在读数单元内（TestAccess 下）
  只用本题公开视图计算，确定性（标准库 BM25，k1 = 1.2、b = 0.75，固定分词，平局按 task_id 哈希）。
  字符上限（登记值，可在简报里改）：insights 合并 ≤4,000；示例每条 QA/表格题 ≤1,500、ZebraLogic ≤3,000、ALFWorld ≤2,400；cheatsheet ≤6,000；workflows 合并 ≤4,000。
- **ZebraLogic**：现在 `solver._system` 对 ZebraLogic 只返回 QA_SYSTEM（卡片不发），所以 C = B；新配置只对 `T_`/`M_` 臂在 QA_SYSTEM 后接 guidance 段，C、B 请求不变（要有逐字节测试）。
- **计分**：表格题评分器判不了的产物，C/B 记对（H 侧）、方法臂记错（L 侧）；新臂按方法臂登记为 L 侧。ALFWorld 按 4 个房间聚类，OfficeQA 按出处文件成组。
- **配对与报告**：每次读数同运行重读 C（是否重读 B 由负责人定）；主对比 M−C、T−C（配对），再给相对 B；与 route B 的 F 只能跨运行比，统一写"各自相对同一运行 C 的差"并注明读数。
- **同意书**：形状照 cross-v5（`multi_arm_arms` 列出臂、`sheet_test_qualification: true`、`test_evaluation: true`、by owner、日期、备注）；只由负责人写，或负责人明确授权代写。

### 3.2 记忆基线：新文件（都在 route B 开发树；不改任何冻结配置）

| 文件 | 内容 |
|---|---|
| `skillopt/execskill/membase/__init__.py` | 版本号；各基线超参数、字符上限、练习流顺序与种子（登记值） |
| `membase/retrieval.py` | 标准库 BM25、分词、确定性平局；只接受练习池路径（含 final/test/holdout/held_out/sealed/reserve 的路径一律拒绝，照 `zebralogic.FORBIDDEN_POOL`） |
| `membase/experience.py` | 用 `trajectories.whitelisted` 读 route B 训练侧轨迹（练习题、成败位）；补收集与 Reflexion 式重试单元（C 卡、同 solver、同外壳） |
| `membase/expel.py` | insights 抽取（GLM-5.3；增/改/赞同/反对的严格 JSON 解析、计数、上限）；各 bench 示例渲染 |
| `membase/cheatsheet.py` | 冻结 DC-Cu：练习流逐题"生成（卡片位 = 卡 + 当前 cheatsheet）→ curator 改写"；curator 不接收任何标签字段；输出冻结文件 + sha256 |
| `membase/awm.py` | 离线 workflow 归纳（GLM-5.3），按 bench，ALFWorld 按 6 种任务类型 |
| `membase/arms.py` | `T_`/`M_` 臂的卡片文字构造（照 `v219_read.card_text`）与复用规则（照 `v218_read.plan`） |
| `skillopt/execskill/v2xx_read.py`（版本号由负责人/登记员定） | 新配置的读数规划、上限算术、readout 的 baseline 段 |
| `profiles.py`、`solver.py`、`cells.py`（改） | 登记新配置；ZebraLogic guidance 只对新配置的 `T_`/`M_` 臂生效；`_shell` 接新臂 |
| `scripts/run_execskill.py`（改） | v214 路径加新配置；新子命令 `mem-build --method {expel,dc,awm} --chain {G,D}`、`mem-show` |
| `tests/test_execskill_membase_*.py`、`tests/fixtures/execskill/membase_*`、`v2xx_parents_before.json` | 见 §3.6 第 3 步 |

### 3.3 GEPA / SkillOpt 补格

| 步 | 做什么 | 复用 | 新东西 | 花费（估） |
|---|---|---|---|---|
| G1 重读 | 抽出 c1 冻结 Skill：SkillOpt S1（7,526 B，= 第 1–2 步）、链末 S3（15,177 B，含 LiveMath）；GEPA S1（4,325 B，= 链末）。当 `T_` 臂在 route B 尺子上读五个面板（G 链）；S1 正好是当前顺序第 1–2 行 | `/data/coevo5-20261017-run/{SkillOpt-glm,GEPA-glm}/s{1,3}/learning/unit.json` 的 `skill` 字段 | 一个零调用抽取脚本（写字节数、sha256） | GEPA S1 9–12M，SkillOpt S1 11–15M，S3 17–23M |
| G2 接着学（G 链） | 按当前顺序从 S2 的 Skill 接着学：第 3 步 ZebraLogic → 第 4 步表格题 → 第 5 步 ALFWorld，每步新 Skill 读五个面板 | 冻结学习器 `skillopt/continual_learning/{gepa,skillopt}.py`（官方 GEPA 源 pin d771eb21…，开发机 `/root/continual-learning-env-20260928/gepa-source`，11/03 已核）；coevo5 `baseline.py` 的清单写法（`BASELINE_BUDGET`、32,000 字节、seed + k） | **派生学习器**（冻结文件不改）：`continual_eval` 加 zebralogic 分支（渲染与评分委托 `execskill.zebralogic`）；练习池转学习面板（ZebraLogic：train = smoke + run 70 题，挑选 = accept 100 题）；派生源码逐字节对照脚本（先例：F 的派生评测源码）；驱动 `scripts/run_textskill_baselines.py` | 学习约 10M，读 25–70M |
| G3 D 链 | D 链从空 Skill 跑完整五步 | 同 G2 | 派生客户端加 northgate（照 `execskill/client.py` Route B：temperature 0、`reasoning_effort: "none"`、显式 PJLAB 网关、`trust_env=False`） | 50–120M |
| 最小版 | 两方法 × 两链只学 ZebraLogic 一步（从空 Skill），只读 ZebraLogic | 同 G2 | G2 + G3 的客户端 | 10–20M |

冻结代码与产物不改（`skillopt/continual_learning/*`、`skillopt/validator_pilot/api.py` 绑定身份；[项目状态](../project-status.md) §1），派生版本用新版本号与新目录。
注意 GEPA 的设计本身要用一个挑选集（Pareto），SkillOpt 也有挑选；它们是"用练习池切出挑选集"的基线，论文里与"不用验证集"的方法分开写。

### 3.4 数据文件（开发机路径）

| 用途 | 路径 | 备注 |
|---|---|---|
| 练习池 | `/data/execskill-20261021-pre/pools/{searchqa,officeqa,spreadsheetbench,alfworld}.json` + `pools.json`（各文件 sha256） | SearchQA 600（train 400 / val 200）、OfficeQA 74（50 / 24）、表格题合格 91（58 / 33，共 120）、ALFWorld 3,514 局（108 房间） |
| ZebraLogic 练习池 | `/data/probe-data-20261025/split-v1/zebralogic/pool.json`（sha256 059dba6a…）、`/data/probe-data-20261025/split-v1/split-manifest.json` | 500 题，登记域（5–6 户 × 2–6 列）200 题，去掉 27 道 v3 探针题后 173（smoke 10 / run 60 / accept 100 / spare 3）；同目录 `sealed-holdout.json` 不打开 |
| 可复用训练轨迹（C 卡第一次尝试） | `/data/execskill-20261031-main-v5/{G,D}/s{1..4}-*/run/attempt-1/trajectories/`；`/data/execskill-20261101-main-v6/D/s{1..4}-*/run/attempt-1/trajectories/`；`/data/execskill-20261028-alfworld-v11/D/s1-alfworld/run/attempt-1/trajectories/` | 每条链 SearchQA 300、OfficeQA 36、ZebraLogic 60、表格题 62；ALFWorld 只有 D 链 60 局，G 链要新收集 |
| ALFWorld 环境与供应 | `ALFWORLD_DATA=/root/continual-alf-prep-20260928/data`；`/data/execskill-history/supply/alfworld-xs.json`、`alfworld-xs-views.json` | route B 训练与验收一直用它；与测试 134 局的排除记录今晚顺手核一次 |
| 表格题资格 | 训练侧 `/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json`；测试侧每个新快照重做 q23（新目录 `/data/execskill-2026110x-sheet-q23-<标签>`） | 10/30 教训：资格按快照绑定 |
| 指令卡 | `execskill-v29/docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json`（指令 sha256 657edd0d…；SearchQA 1,846 字符、OfficeQA 2,926、表格题 2,907、ALFWorld 2,301） | ZebraLogic 只有中性卡，外壳不发 |
| c1 冻结 Skill | `/data/coevo5-20261017-run/{SkillOpt-glm,GEPA-glm}/s*/learning/unit.json` | 只取 `skill`、`skill_bytes`；同级 `evaluation/` 是测试读数，不打开 |
| 测试面板（只记名字） | `/root/fivebench-test-eval-20261005-h/panels/{searchqa,spreadsheetbench,alfworld}.json`；OfficeQA 由 `/root/officeqa-upstream-20261013` 按 `/root/extension-20261013/officeqa/layout.json` 渲染；ZebraLogic `sealed-holdout.json` | 只由同意书下的读数单元经 TestAccess 打开 |
| Python | `/root/continual-alf-prep-20260928/env/bin/python`（3.11.16，继承系统包：numpy 2.4.6、openpyxl；**没有** sklearn、rank_bm25、sentence-transformers、torch） | BM25 用标准库写，不装新依赖；要用嵌入检索须负责人批准（下载或调用嵌入接口） |

### 3.5 凭据（只写路径，绝不打印内容）

| 用途 | 路径 |
|---|---|
| G 链 solver 与所有方法角色（GLM-5.3，BigModel） | 凭据仓库 `/root/continual-noskill-bcb-20260928-a`（其中 `.env`） |
| D 链 solver（deepseek-v4-flash，northgate） | `<deepseek-credentials-file>` |
| 不用 | `/root/.config/weak-solver/elucid.env`（10/26 填充事故后停用）；`router.env`、`pjlab-token.env` 与本计划无关 |
| 网络 | 显式 PJLAB 网关、`trust_env=False`（route B 客户端已如此）；需要 shell 代理时 `bash -ic 'proxy_on && <命令>'` 在同一个 shell 里 |

### 3.6 运行手册（标【负责人】的步骤要负责人决定；标【付费】的步骤不在今晚做）

0. **登记（零调用）**：写简报（建议 `execskill-v29/docs/handoff/v29-20261026/BRIEF-membase-v1.md`）：臂、超参数、字符上限、练习流顺序与种子、主对比、第二分析、
   表格题 L 侧、ZebraLogic 卡片位、诚实事实（这些面板 route B 已读过多次：ALFWorld G 5 次 / D 8 次，SearchQA 与 OfficeQA G 5 / D 6，表格题 G 4 / D 5，ZebraLogic G 3 / D 5，另有路线 A 的读取；不在测试集上调任何超参数）。【负责人】批准范围、档位、总额度。
1. **环境检查（零调用、只读）**：ssh 可达；`df -h /data`（11/03 19:4x 可用 381 GB）、`df -i /tmp`，`/tmp/pytest-of-root` 为空；Python 与依赖（§3.4）；
   GEPA 源 `git rev-parse HEAD` = d771eb21…；凭据只 `ls` 存在；看运行中的实验：main-v6 G（与本计划共用 GLM 的 10 个并发、表格题步占 `memory-heavy.lock`）、
   `sq6-go` 在等 main-v6 G、旧机器 main-v7；看 `/data/execskill-slots/*.lock` 与 `memory-heavy.lock.holder-*.json` 的时间（锁等待不写日志）。
   再做两项可比性核对：route B 清单与 c1 清单（`/data/coevo5-20261017-run-manifest.json`）里 SearchQA/表格题/ALFWorld 面板的 sha256 是否相同；c1 清单 `baseline.model` 与 route B `client.py` 的 GLM 参数是否逐项相同。结果写进简报。
2. **实现（零调用）**：Codex（`codex exec -m gpt-6-astra -c model_reasoning_effort='"ultra"'`）按简报写代码和测试，Claude 审 diff；另开 Codex 会话审查一轮；冒烟失败才有第二轮。
3. **离线测试（零调用）**：本机 pytest（假模型、无网络）——旧配置逐字节不变（parents 指纹）；`T_`/`M_` 臂的请求 = 把 C 的卡片位换成同一文字后 C 会发的请求（逐字节，fixture 题）；
   ZebraLogic 的 C、B 请求不变；BM25 确定性与路径拒绝；字符上限与截断；ExpeL 操作解析拒绝非法 JSON；DC curator 拿不到标签；上限算术；readout 的 baseline 段（含共享格与第二分析）；
   route B 既有 v214–v219、zhp/zpc 选择回归。`TMPDIR` 名字不能含 "test"；本机 `tests/test_execskill_step.py` 已知 5 个 macOS 失败。
   开发机：从开发树切新快照 `/data/execskill-code-2026110x-<配置>`，`verify-snapshot`，跑 S0（`TMPDIR=/tmp/execskill-s0-<标签>`、`chmod 1777`、跑完删；不与别的 S0 同时跑）。
4. **建记忆冒烟（5 题）【付费，小额】【负责人：额度】**：每 bench 5 道练习题（ALFWorld 5 局）、每条链：ExpeL 重试 + 1 次 insights 抽取；DC 5 题生成 + 整理；AWM 1 次归纳。
   核对第一个真实回执（HTTP 200、模型回显、`stop`、usage 齐全）、JSON 解析、字符上限、每题 token，用实测替换 §2.4 的估算。
5. **正式建记忆【付费】**：按简报的练习流建 ExpeL / DC / AWM，冻结文件与 sha256 写进清单；新运行目录 `/data/membase-2026110x-<链>`；永不自动续跑，暂停的单元只由负责人写的 recovery 恢复。
6. **读数冒烟（只用练习题）【付费，小额】**：照 cross-v5 的 S0、S2、SE6：每 bench 每臂 5 道练习题，检查请求形状、复用、记录字段（卡片来源、记忆 sha256）、token；SE6 投影整次读数的花费并写进上限。
7. **正式读【付费】【负责人：同意书、时间与机器】**：同意书就位后启动；照 `x5-run.sh` 的习惯先确认一条链的首个真实调用再放另一条
   （G 链若要等 main-v6 G 结束或改去第二台机器，可改成先 D 后 G，启动脚本里的顺序检查要跟着改）；
   每条链一次读完五个面板的全部臂；成败看日志最后一行（EXIT 检查陷阱）；tmux 一律 `-t =名字`。
8. **读数（零调用）**：登记的配对差（M−C、T−C、相对 B、第二分析）、各 bench 分母与区间；账本、项目状态、亮点页由主会话更新。

GEPA/SkillOpt：G1 只需在第 7 步多加 `T_gepa_s1`、`T_skillopt_s1`（可选 `T_skillopt_s3`）几个臂；G2/G3 的派生学习器另走一遍第 0–3 步，
学完的每步 Skill 再按第 6–8 步读（可与记忆基线同一次读，也可第二波，各自配对 C）。

### 3.7 需要负责人决定的事

1. 跑哪几个、哪一档：第一档（C、ExpeL、DC，两条链；G 链加 G1 重读）约 1.0–1.3 亿 token；第二档（kNN、AWM、B）再加约 0.5–0.6 亿。
2. 经验来源：复用 route B run 批轨迹（同一 solver、同一卡、零成本，等于和 route B 看到同样的经验）+ 只给失败题补重试（推荐），还是全部重新收集。
3. DC 的 curator：GLM-5.3（与 route B 方法角色一致，推荐）还是本链 solver（与原文一致）；要不要加测试流在线版（转导、串行）。
4. 记忆合成一份带 bench 标签（推荐，能测跨 bench 损害）还是按 bench 分开（等于给了路由）。
5. ZebraLogic 外壳只对新臂加卡片位（C、B 不变）。
6. 是否在同一运行里重读 B（每链 +5–7M）。
7. GEPA/SkillOpt 范围：G1 / 最小版 / G2 / G3。
8. 时间与机器：G 链等 main-v6 G 结束，还是放到第二台机器 PJ-CL4MIND（有销毁风险，结果要及时同步）。
9. 同意书（读测试集）由负责人写，还是授权代写。
10. 只读链末一次（推荐），还是每一步之后都读五个面板做 5×5（每臂成本约 ×5）。**负责人 2026-11-04 09:3x 已定：基线范围与定位按默认，但不做 5×5；记忆方向的基线各自单独跑每个 bench、每个 bench 读一次，把数记下来即可。**
11. 新配置的版本号（v2.22 已留给 main-v8 的卡片拆分）。

## 4 今晚清单（只做环境与代码准备，不发任何付费调用、不读任何测试面板、不碰运行中的实验）

| 优先 | 事项 | 产出 |
|---|---|---|
| P0 | 零调用核对测试面板身份：route B 读数清单（如 `/data/execskill-20261102-cross-v5-manifest.json`）与 c1 清单里 SearchQA/表格题/ALFWorld 面板 sha256、OfficeQA 172 题号列表的哈希是否相同（只比哈希，不打开面板） | 一行结论进简报：c1 数字是否"同题" |
| P0 | 零调用核对 GLM-5.3 求解参数：c1 清单 `baseline.model` 与 route B `client.py`（thinking low、max_tokens 65,536、读超时 2,400 s） | 同上 |
| P0 | 抽出 c1 冻结 Skill（SkillOpt S1/S3、GEPA S1）的文本、字节数、sha256 到本机 fixture（不碰 `evaluation/`） | `tests/fixtures/execskill/membase_c1_skills.json` |
| P0 | 清点可复用训练轨迹，写路径 + 文件数 + sha256 清单（§3.4 那一行） | 经验池清单 |
| P1 | 写简报 `BRIEF-membase-v1.md`（臂、超参数、上限、主对比、诚实事实、负责人决定位） | 简报 |
| P1 | Codex 写 `membase/` 模块与测试（§3.2），Claude 审；一轮 Codex 审查 | diff + 审查记录 |
| P1 | 本机 pytest 全过（含旧配置指纹） | 测试报告 |
| P2 | 开发树同步、新快照目录名占位；S0（遵守 /tmp 规则，避开别的 S0） | S0 记录 |
| P2 | 写好但不启动：建记忆冒烟脚本、读数冒烟脚本（照 x5 脚本）、未签的同意书模板、事件式监视脚本 | ops 目录 |
| P2 | 派生学习器（GEPA/SkillOpt + ZebraLogic、northgate）的简报草稿与逐字节对照脚本设计；实现排在记忆基线之后 | 简报草稿 |

## 附：引用的文献（名称与年份）

- ExpeL: LLM Agents Are Experiential Learners（Zhao 等，2024）
- Reflexion: Language Agents with Verbal Reinforcement Learning（Shinn 等，2023）
- Agent Workflow Memory（Wang 等，2024）
- Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory（Suzgun 等，2025）
- Voyager: An Open-Ended Embodied Agent with Large Language Models（Wang 等，2023）
- What Makes Good In-Context Examples for GPT-3?（Liu 等，2022）
- Synapse: Trajectory-as-Exemplar Prompting with Memory for Computer Control（Zheng 等，2024）
- MemoryBank: Enhancing Large Language Models with Long-Term Memory（Zhong 等，2024）
- A-MEM: Agentic Memory for LLM Agents（Xu 等，2025）
- Mem0（2025）
- GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning（Agrawal 等，2025）
