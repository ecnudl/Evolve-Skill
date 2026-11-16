# 同家族迁移：姐妹数据集调查（2026-11-06）

这是设计调查，不是实验结果。没有调用模型，没有打开任何测试集。调查由一个子代理在 HF、GitHub 和论文页上核实。
V 表示 11/06 当天核实过，P 表示论文里的数字、没有复核。

## 目的

负责人 10/17 定的目标是：在一个数据集上学到的技能，要能帮到同类的其他数据集，不伤害不同类的数据集，学了新的也不忘旧的。

现在的五个 bench 彼此都不相似，ZebraLogic 和谁都不像。所以每步之后读的五乘五表只能检验“不伤害”和“不遗忘”，检验不了“帮到同类”。

姐妹数据集补上这一块。做法是在 A 上学，在同类但来源不同的 A' 上直接读，A' 上不学，看技能有没有带来提升。

负责人 11/06 定：同一数据集内部的拆分、改问法都不算姐妹。

## 已有证据（结果账本 10/21 06:02）

10/21 的 E4 和 E9 直接测过整段任务说明的跨数据集迁移。登记的相似对预测不了迁移：相似减不相似为 +0.1，区间 [−5.6, +5.5]。

问答说明通用约 +7 个点。作答格式冲突掉 8 到 27 个点，例如 LiveMath 说明用在 OfficeQA 上掉 9.5。

所以正确的对照是“目标集自己的格式块 + 迁移来的技能”对“目标集自己的格式块”，不能拿 A 的整张卡替换 A' 的卡。

## 候选

| 我们的 bench | 候选 | 来源 | 许可 | 可用测试量 | 判分 | 移植难度 | 主要风险 |
|---|---|---|---|---|---|---|---|
| SearchQA | TriviaQA-unfiltered | HF `mandarjoshi/trivia_qa` | HF 写 unknown，代码 Apache-2.0 | 验证集 11,313（V），测试答案不公开 | 别名精确匹配 | 低 | 2017 年数据，DeepSeek-V3-Base 闭卷 82.9，可能见过、余量小 |
| SearchQA | HotpotQA distractor | HF `hotpotqa/hotpot_qa` | CC BY-SA 4.0 | 验证集 7,405（V） | EM/F1 | 低 | 多跳、维基段落，比 SearchQA 远一些 |
| SearchQA | Quasar-T | GitHub `bdhingra/quasar` | BSD-2（V） | 3,000（P） | EM/F1 | 中 | 官方下载地址当天连不上 |
| OfficeQA | DocMath-Eval CompLong | HF `yale-nlp/DocMath-Eval`（需点击同意） | HF 卡片写 MIT | 测试 1,200 + testmini 300，答案 2026-07 起公开（V） | 数值匹配 | 中：每份文档要切到 8 万字符内 | GPT-4o 41.5，人 76（P，2024） |
| OfficeQA | DocFinQA | HF `kensho/DocFinQA` | MIT（V） | 测试 922（V） | 数值 | 中高：文档平均 12 万词，要检索 | 题目沿用 FinQA |
| OfficeQA | TAT-QA | HF `next-tat/TAT-QA` | CC BY 4.0（V） | 测试 1,663（V） | 片段或数值 + 单位词 | 低 | 上下文短，接近天花板 |
| ZebraLogic | BBEH zebra_puzzles | GitHub `google-deepmind/bbeh` | Apache-2.0（V） | 200（V），dl 上 10/25 已有副本 | 一个整数，精确匹配 | 低 | 5×5 到 8×8 格，有干扰线索，生成器不同 |
| ZebraLogic | LR²Bench Logic | GitHub `ZNLP/LR2Bench` | 未声明，题目来自 printable-puzzles.com | 200（V） | 每格都对 | 低 | 只能内部使用 |
| ZebraLogic | GridPuzzle | GitHub `Mihir3009/GridPuzzle` | 代码 MIT，题目来自 Puzzle Baron | 274（V） | 每格都对 | 低到中 | 题目是第三方内容 |
| SpreadsheetBench | SheetCopilot | GitHub `BraveGroup/SheetCopilot` | GPL-3.0（V） | 221 题来自 67 个种子，去掉图表和透视表 150 题（V） | 对照参考工作簿逐项检查 | 中 | 同一种子的题多，有效样本小于 221 |
| SpreadsheetBench | SpreadsheetBench 2 | HF `KAKA22/SpreadsheetBench-v2` | HF 卡片写 MIT | 321（V） | 要求的格子对、其他格子不动 | 高：要多轮智能体 | 与我们的 bench 同名同作者 |
| ALFWorld | TextWorldExpress 的 TWC | GitHub `cognitiveailab/TextWorldExpress` | Apache-2.0（V） | 测试划分可按需生成 | 成功或分数 | 低到中：要 Java 1.8 | 强模型上接近天花板，要用最难设置 |
| ALFWorld | ScienceWorld | GitHub `allenai/ScienceWorld` | Apache-2.0（V） | 约 1,800 个测试变体（P） | 0 到 100 分 | 中高：一局最多 100 步，费 token | 程序要换适配器 |

不收的候选包括：J! Archive 系列（与 SearchQA 同源）、ZebraLogic 选择题版、ALFRED 系列（与 ALFWorld 同源）、FinQA（与 DocFinQA 同题）。
还不收 FinanceBench（150 题，非商用许可，靠评审打分）、InstructExcel（要 Excel）、Knights-and-Knaves（题型不同）和 MultiHiertt（没找到许可）。

## 每个 bench 推荐一个

| 我们的 bench | 推荐的姐妹集 |
|---|---|
| SearchQA | TriviaQA-unfiltered |
| OfficeQA | DocMath-Eval CompLong |
| ZebraLogic | BBEH zebra_puzzles |
| SpreadsheetBench | SheetCopilot 的 150 题子集 |
| ALFWorld | TextWorldExpress 的 TWC（最难设置） |

ALFWorld 一项，如果 20 局试跑到顶，就换 ScienceWorld。

最便宜的两个起点：ZebraLogic → BBEH（数据已在 dl，一题一次调用，判一个整数），SearchQA → TriviaQA（沿用同一套外壳和判分）。

19:0x 补充：最便宜不等于最有信息量。ALFWorld 是路线 B 唯一真学到东西的 bench（10/29 `alfworld-v11` 留出集 F 112 对 C 96，共 134 局，+11.9），
所以 ALFWorld → TextWorldExpress 最可能看到正面迁移；代价是动作写法不同（东南西北移动、没有加热冷却清洗），要写适配器，
读数会部分测到适配器。建议先在最难设置上跑约 500 万 token 的 20 局小试，看是否已接近满分。OfficeQA、表格题上方法还没学到过东西，先不做。

## 设计上的限制

- **读数可能按构造为空。** 路线 B 的 ZebraLogic 求解程序只认 ZebraLogic 固定的线索写法，ZebraLogic 的历史卡又是空的，所以只迁移程序时 BBEH 上带技能和不带技能的请求会逐字节相同。只有学到的指令卡才可能带来差别。
- **前提是先学到东西。** 以往各次主实验在非 ALFWorld 的 bench 上都没有收下包。如果 main-v9 在 SearchQA 或 ZebraLogic 上也没收下东西，这两个迁移读数就没有意义，不应花钱。v2.24 的 SkillOpt、GEPA 每个 bench 都会产出提示词，可以作为基线读。
- **ALFWorld 的程序是按 ALFWorld 的命令写的。** 换环境要写适配器，读数会部分测到适配器。
- **表格题没有同形态的公开数据**，而且到现在还没有收下过表格题程序。
- 2025 年以前发布的数据可能在模型的训练数据里。

## 调查笔记

完整链接与计数方法在本机任务目录 `tmp/sister/notes.txt`（不入库）。
