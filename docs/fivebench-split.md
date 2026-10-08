# 五域标准划分 fivebench-split-v2（10/5，零调用）

**用途**：今后所有基线（No-Skill、SkillOpt、GEPA）与主实验方法都按这份划分逐个评测bench。`train`只用于学习，`val`只用于选择（可反复使用），`test`只用于最终报告（不得用于学习、选择或调参），`reserve`暂未分配。

清单：[data/fivebench_split/split_manifest.json](../data/fivebench_split/split_manifest.json)（`fivebench-split-v2`，record `c459c242…`；只含task_id与family_id，不含题面、答案或测试）；生成脚本：[make_fivebench_split.py](../scripts/make_fivebench_split.py)。v1是审查前草稿（保留在开发机`/root/fivebench-split-20261005-v1`，勿再使用）：题目归属与v2完全相同，v2补上了与研究F的绑定和历史暴露说明。开发机上的v2清单：`/root/fivebench-split-20261005-v2/split_manifest.json`。

| 域 | train | val | test | reserve | 来源 |
|---|---:|---:|---:|---:|---|
| BigCodeBench | 400 | 128 | 484 | 128 | 项目9/28四分区：development / skill_confirmation / final / verifier_calibration（v0.1.4 instruct全部1,140题） |
| SpreadsheetBench | 80 | 40 | 280 | 0 | 项目分区 development / skill_confirmation / final，逐ID等于原生SkillOpt的train/val/test（Verified 400） |
| SearchQA | 400 | 200 | 400 | 1,000 | 原生SkillOpt train/val；test为原生1,400题中按固定种子抽取的400题，其余1,000题为reserve |
| KOR-Bench | 500（50条规则） | 250（25条） | 250（25条） | 250（25条） | 项目9/28按规则族四分区（每类10/5/5/5条规则），val/test的规则从未出现在train中 |
| ALFWorld | 39 | 18 | 134 | 0 | 原生SkillOpt：train / valid_seen / valid_unseen |

规则：
- 沿用项目已有分区：development → train，skill_confirmation → val，final → test，verifier_calibration → reserve。SearchQA与ALFWorld没有项目分区，用原生SkillOpt划分。
- 任务族与面板导入器一致（KOR一条规则、ALFWorld一个场景、SearchQA完全相同的问题、BCB与Sheet沿用分区中冻结的family_id）。生成时校验：任一题或任一族都不跨部分。
- **与研究F的绑定**：清单记录了F的协议哈希、各域参照计划哈希与学习面板哈希，并校验F评测的正是各域的train（BCB 400、Sheet 80、QA 400、KOR 500、ALF 39），学习只用了train内的题（129、80、128、200、39）；val、test、reserve从未被F用于学习、选择或评测。因此F学出的Skill可以直接在test上评测。此前C/D/E/F表中的分数都是train（开发集）上的分数，不是test分数。
- **“对F留出”不等于“历史上从未暴露”**（清单`exposure`字段逐域记录）：SearchQA原生train/val/test在项目早期的GPT原生SkillOpt复现中都产生过预测（见[9/28基线说明](skill-validation-baselines-20260928.md)）；BCB与KOR的val/test/reserve分区在开发机运行计划中查不到评测记录（10/5按面板路径检索，不构成未暴露的证明）；Sheet与ALFWorld在F之外的使用未审计。因此test上的结果是“对所评方法留出的测试集结果”，**不是经暴露过滤的独立final**。
- **已知不可计分的测试题**：SpreadsheetBench 42930的发布数据把标准答案文件误命名为`1_43930_golden.xlsx`，无法与`1_42930_init.xlsx`配对。它仍属于test，但评测时排除（Sheet按279题计分），不做数据修补；其他方法评测时应同样排除并注明。
- 原BCB的skill_confirmation分区在本划分中作val（可反复选择）；主线若还需要一次性的确认集，应从reserve中另行约定。

## 在test上评测基线（已完成，10/6 07:43）

**10/5 17:58启动**（Codex八轮审查后ACCEPTABLE；零调用准备与30格冒烟通过；首批28个真实回执全部HTTP 200/`stop`/`glm-5.3`/流完整）。开发机：tmux `f-test-eval`，工具`/root/fivebench-test-eval-20261005-tools-h`，输出`/root/fivebench-test-eval-20261005-h`（`-pre`、`-b`…`-g`为审查前目录，已作废）。评测顺序：No-Skill → SkillOpt最终Skill（S4）→ GEPA最终Skill（S4）→ SkillOpt S1、S3 → GEPA S3；每个策略内按QA、ALF、Sheet、BCB、KOR。

**10/5 23:45停止、10/6 00:46继续**：一次开发机瞬时卡顿使一个BCB评分容器“清理未确认”，交接检查按设计停下队列；人工复核后存档该格第一次尝试并从头重测，其余已完成格子零调用回放，工具代码未改。详见[F报告的test表“事件”](fivebench-f-skillopt-gepa-20261003.md)。

[evaluate_fivebench_test.py](../scripts/evaluate_fivebench_test.py)（`fivebench-test-eval-v8`）把F的6个不同策略（No-Skill、SkillOpt S1/S3/S4、GEPA S3/S4；Skill未变的阶段与上一阶段是同一策略）在五域test上各评测一次（每题1次），共30格、约2.3万次调用。每格沿用F该域冻结的评测配置，只改三处：面板换成test面板、分区`final`、重复1次；在F的派生评测源码与同一解释器中运行，并校验代码与运行环境身份等于F自己评测时记录的身份，test面板只能来自生成划分时的同一批源文件（按哈希），每个worker操作前都重新校验全部输入。

调度：模型调用始终只有一格在生成（10路并发，即key的并发上限）；本地评分在另一线程进行，与下一格**纯API**的生成重叠；Sheet与ALFWorld的生成本身要跑容器/原生回合，会先等评分空闲，因此任何时刻只有一种本地负载，与F的串行流程一致。控制器是单线程的：每一轮先收集已退出的worker，任一格失败后不再启动新的worker，已在运行的worker跑完。停止运行属于人工操作，处理方式与F的编排器相同、不承诺更多：worker是控制器进程组里的普通子进程，关闭tmux会话或Ctrl-C会直接到达它们；控制器自身出错或被SIGINT中断时会先杀掉正在运行的worker再退出；worker自己的子进程（容器、原生回合进程）不追踪。已开始的格子不会自动续跑；运行中途停止时，所有已生成但尚未评分的格子（评分慢时最多可达四个）的预测都保留，需人工复核后再处理。结果见[F报告的test表](fivebench-f-skillopt-gepa-20261003.md)与[汇总JSON](results/fivebench-test-eval-20261006.json)：两种方法都只在QA上有可信提升（+47题）。
