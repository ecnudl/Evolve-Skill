# Evolve-Skill

**10/3 18:57：新 F（序列 v4 / 学习 v7）运行中**：SkillOpt 与官方 GEPA 依次在五域进化，Skill 接口提高到 32,000 字节，用于得到 No-Skill / SkillOpt / GEPA 的完整五域对比；尚无成绩，见[新 F 报告](docs/fivebench-f-skillopt-gepa-20261003.md)。

无上下文的代码代理请先读 [AGENTS.md](AGENTS.md) 和[接手指南](docs/agent-start-here.md)，再核对两份主文档：[当前流程](docs/current-workflow.md)、[结果账本](docs/results-and-lessons.md)。本轮运行以[新 E：SkillOpt 五域补跑](docs/skillopt-generalization-e-20261003.md)及实际回执为准，不把历史快照当当前状态。

基于 [Microsoft SkillOpt v0.2.0](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0) 的研究项目：**通过 Coding Rubric 与有界 DeepResearch 协同改进 Skill 的内容、验证和适用范围，降低跨领域负迁移。**

我们不要求每个 benchmark 都达到 SOTA，而是希望 Skill 学到可迁移的解题机制，在改善目标任务的同时保留其他领域的能力。泛化范围应由行为证据确认，不能由模型在 Skill 文本中自行宣称。

**10/3 18:13 终态：新 E 五阶段尝试结束，完整学习4/5、五域矩阵闭合5/5，只有S1更新了Skill。** 最终相对No-Skill的Coding确认正确400→421/800，但KOR746→721/1000，收益与跨域退化并存；S2/S3/S5候选超长而无更新，S4 Pending携父，后20格复用S1观测。已公开[分母、unknown、成本和复用标记](docs/results/skillopt-generalization-e-final-20261003.json)。这是已曝光开发面板上的受预算SkillOpt适配baseline，不是独立final或Research/Rubric主线效果。

新[v6工程修复](docs/learning-v6-engineering-repairs-20261003.md)显式隔离清理失败、过滤重试、健康检查与未知成本上限；未覆盖E的冻结v5，也未启动v6正式实验。unknown选择策略的统计局限仍保留并如实记录。[旧C/D终态](docs/skillopt-generalization-20261002.md)仍为完整学习0/5，不能与E混写。

**历史快照（截至 2026-09-27）：同课程归纳、修复轨迹学习、候选确认及预算诊断已完成，共同 Solver 可靠性修复已通过 Linux 工程验收。** 修复细节促成两份主候选，后续96个实际注入位置未观察到干扰，但没有证明语义正迁移。普通归纳多20个通过位置，19个来自截断差异；另一逐例候选净增9项也全部涉及交付。预算扩大后原始分差缩小，不能把交付稳定性当作泛化提升。历史目标课程A–D仍Pending；Skill稳定增益、Research独有信息增量与跨域收益均待证明。这不是已完成全部实验的论文复现包。

## 给首次阅读仓库的 AI / 研究者

10/2傍晚[旧 C baseline 接续实录](docs/baseline-continuation-20261002.md)保留五域适配、双方法队列及当时启动快照。旧 C 的 SkillOpt 五阶段尝试现已终止，完整学习为 **0/5**；25格均是携空父后引用旧 No-Skill，不是新观测。新 D 只运行 SkillOpt，使用新版本和目录，不续写旧 C。工作簿链接兼容 B 的独立诊断仍为79/55/26、134旧已知保持，不算 Skill 收益。

10/2[未知结果修复与复测](docs/unknown-recovery-results-20261002.md)：最新冻结参考标签H v3通过34＋18项资格，同80题×2原产物零API重评为**79通过/55失败/26未知**；较v8b70/48/42恢复16未知，原118个已知保持。过粗元数据预筛的B负结果51/41/68亦保留。交付失败另列回顾性端到端79/61/20，不改内容分或原基线；这些是评测覆盖与归因修复，不是Skill收益。KOR10次截断恢复7/2/1，仍有131072输出tokens截断。[完整新数据](docs/results/unknown-sheet-frozen-gold-c-replay-final-20261002.json)

10/1新增：[夜间监控、五域新基线与学习结果](docs/overnight-baselines-20261001.md)，[聚合数据](docs/results/noskill-fivebench-long-20261001.json)保留1,419题×2的分母与成本。通过/失败/未知分别为：Coding 400/399/1，SearchQA 560/234/6，KOR 746/243/11，ALF 65/13/0，工作簿63/44/53。全部完成，但工作簿仍有兼容性覆盖不足，Coding新环境资格仍Pending，不把完成执行当环境完全修好。GEPA、SkillOpt有限重提及条件化归纳shadow均未选出优于空父的Skill；小分差不足以判断方法优劣。下一步优先比较可信具体反例反馈与仅成败反馈，而非继续扩写Skill。新公式预览/ALF日志修复仅工程验收、未宣称方法收益；最新状态见[当前流程](docs/current-workflow.md)和[结果账本](docs/results-and-lessons.md)。

9/28新增：[五基准持续评测框架](docs/skill-validation-continual-evaluation-20260928.md)，支持BigCodeBench、SpreadsheetBench、SearchQA、KOR-Bench、ALFWorld的冻结S0–S5评测、配对比较和断点回放。它接收外部冻结Skill，不等于已经实现五阶段协同学习。

9/29[五域No-Skill开发基线](docs/noskill-baseline-results-20260929.md)已全部落盘：1419题×2，共2838位置；Sheet的62/160 unknown已做原因诊断，未重算。Coding单阶段SkillOpt第一轮候选28/64、空父39/64，gate拒绝；第二轮因响应截断Pending，GEPA未启动。[最新实验结果总表](docs/experiment-results-20260929.md)区分完整与部分结果、未知和成本；没有新的独立final或泛化效果结论。

9/27补充：[求解可靠性修复与Linux验收](docs/skill-validation-solver-reliability-20260927.md)已接通共同输出预算、一次公开修订及回归保护；完整工程smoke 9/9公开通过，另验证超时修订和保留正确初稿。没有调整评测体系，也不将这些工程检查算作泛化增益。

建议按下面顺序阅读，不必从全部历史 `coevolution_vXX` 开始：

1. [当前完整流程](docs/current-workflow.md)：持续维护的主文档，说明初始化、每步输入输出、Rubric/Research、反馈更新及两道门；明确真实与 fixture 状态。
2. [结果与经验账本](docs/results-and-lessons.md)：持续维护的重要实验表格、正向信号、反例、成本和数据存档索引。
3. [新 D 五域 SkillOpt 对比](docs/skillopt-generalization-20261002.md)：本轮协议、进度、No-Skill参照与数据重叠边界；实际完成以绑定回执和终态为准。
4. [研究索引与证据边界](docs/research-overview.md)：更多历史报告与代码地图；日期报告不改写为新结果。
5. [主线接口与运行说明](docs/skill-validation-mainline.md)：按实现阶段保留的详细说明；历史对照见 [9/25 报告](docs/skill-validation-mechanism-study-20260925.md)，历史目标课程见 [9/24 报告](docs/skill-validation-capability-curriculum-20260924.md)。
6. [真实实验材料与离线 demo](examples/research_evidence/README.md)：已有真实 Skill、反馈、4 个配对代码案例与96个单轮评分位置；新增9/25真实“修复轨迹→规则→条件反转执行”及负例摘录。不是所有实验的完整原始数据。

分析时请区分**算法设计、工程 fixture、历史回放、真实模型实验**；给出的改进建议应指向具体代码或证据缺口，而不是默认方法已经有效。现在提供经过筛选的真实记录摘录；完整原始运行缓存仍未公开，记录回放不等于重新执行或独立认证。

部分归档报告保留了当时的 `outputs/…` 本地证据引用，这些私有运行产物不随仓库发布；请优先使用 `docs/results/` 的脱敏摘要和明确标注的公开 demo，不把缺少原始回执的摘要视为独立复现证明。

无需 API 即可查看真实记录并重算结果：`python scripts/replay_research_demo.py`。它不执行模型生成的代码。

## 方法如何工作

1. **发现问题**：No-Skill / Current 在相同开发任务上执行，保留产物、公开检查和配对差异。
2. **进化验证器**：Research 针对验证缺口查阅限定资料；Rubric 表达任务义务、适用条件、例外和证据要求，实例化为可执行检查。
3. **先校准验证器**：独立校准检查新增检错、误拒、覆盖率与成本；没有可靠新证据，不授予相应反馈权限。
4. **再更新 Skill**：用绑定实际执行的反馈指导 Preserve / Repair / Restrict，允许删除或条件化父 Skill 中冲突的规则。
5. **独立确认与最终评价**：冻结 Candidate，与 No-Skill / Current 配对，决定 Local Commit / Restrict / Reject / Pending；分别报告强制使用和条件部署效果。final 不回流更新。

这是主线设计，不代表每个实验均启用了全部步骤：`closed_loop.py` 已用工程样例接通两道门；`natural_study.py` 的真实 Coding 单轮对照已完成，但两类自适应验证器未获反馈授权，实际共享固定反馈候选。随后 `natural_verifier_replay.py` 和 `probe_review.py` 冻结相同产物，只比较验证器与测试提案盲审，**不更新 Skill、不读取 final、不授予部署或跨域范围**。当前 Research 是限定来源和预算的研究模块，不是完整自主 DeepResearch。

## 最重要的实验结果

结果统一维护在[精简账本](docs/results-and-lessons.md)，包含 SearchQA 来源学习、V12/V14 内容更新、V8 结构化答案修订、9/23 执行前审阅与反馈修订、9/24 课程 Pending、9/25 机制学习与归因，以及9/27工程验收。正向信号与必要反例、分母和实际成本一起保存，避免多份摘要逐渐不一致。

H 指冻结的独立宿主审计，本身仍有契约争议。不能将不同任务面板直接横比；重复执行不等于新增独立任务，unknown 不等于语义错误。

当前需要优先解决的问题：

- **公开检查有遗漏，也有契约冲突。** 扫描 64 道开发题找回 4 题的 7 个示例；其中一题揭示真实覆盖缺口，另一题的示例与参考实现冲突，不能全部按模型错误计分。恢复提取器已做成独立入口，未改写历史评分。
- **Research 贡献尚未被分离。** 盲审后的 Research 分支比固定检查多检出 3 个位置，但均来自同一题的三条件共同错误，不是三个 Skill 回归；没有证据把这项收益归因于所读资料。
- **校准数据不足且已经消费。** 24 题校准只有 6 个 H 错误位置、来自 3 题；一律预测通过也能有 93.75% 表面准确率。下一步看检错、误拒、覆盖率与配对方向，不只看 acc；新管线授权仍为 Pending。

## 代码入口与离线运行

新 D baseline 入口为[五阶段编排](scripts/continue_fivebench_baselines.py)、[显式 v2 配置](configs/continual_learning/fivebench_sequence_v2.pjlab.json)、[学习器](skillopt/continual_learning/skillopt.py)及[只读对比报告器](scripts/report_fivebench_generalization.py)。学习端恢复策略与原评测身份分开冻结；相同 Skill 的评测引用不算新增独立样本。已有运行不可通过重执行启动脚本覆盖，操作边界见本轮报告。

新评测流可零API运行：`python -m skillopt.continual_eval smoke --output outputs/continual_eval/offline_demo`。这是5基准×6阶段的编排fixture，不是真实benchmark分数；[配置模板](configs/continual_eval/five_benchmarks.json)与[Linux原生运行环境](skillopt/continual_eval/runtime/README.md)供下一步采集基线使用。

Research 双门主线集中于 [`skillopt/skill_validation/`](skillopt/skill_validation/)：`stage2.py`（验证器比较）、`closed_loop.py`（带准入的一轮流程）、`natural_study.py`（自然任务对照）；另有 `natural_verifier_replay.py`（真实固定产物诊断）、`probe_review.py`（盲审消融）、`public_examples.py`（公开示例覆盖诊断）。它与新 D 原生 baseline 分支分开，历史入口保留，不改写冻结协议。

9/23 新增 `admissibility.py`（执行前审阅）、`probe_fact_research.py`（逐检查外部事实研究）、`verifier_readiness.py`（独立错误族与配对方向诊断）及 `admissibility_study.py`（真实旧产物实验）。Research 连接的工程验证与自然效果分开报告，不把可运行接口当作 Research 增益。`scripts/inventory_mbpp_full.py` 已盘点 424 个潜在新任务／394 个词面族，尚未形成正式独立分区。

9/24 新增 `skill_seed.py`、`rule_skill.py` / `rule_learning.py`、`capability_goals.py` 和 `curriculum_study.py`：来源可追溯初始化、有限规则编辑、历史能力诊断及生成任务家族的 shadow 学习入口。当前课程不使用 Research 反馈，不签发跨域部署权限；各步状态见[完整流程](docs/current-workflow.md)。后续维护约定见 [AGENTS.md](AGENTS.md)。

9/25–27 的 `mechanism_study.py`、`public_repair_feedback.py` 和 `mechanism_case_confirmation.py` 接通共同课程对照、真实修复证据到规则更新、冻结候选确认；`solver_profile.py` 提供显式 `reliable_v1`，统一初稿/修订预算、一次公开修订及回归保护。新行为使用新输出目录，不改写历史协议或评分。

Python 3.10+，建议使用独立环境：

```bash
python -m pip install -e ".[dev,searchqa,cross-domain,validator-pilot]"
python -m pytest -q tests/test_skill_validation_*.py tests/test_resume_natural_validation.py tests/test_spreadsheetbench_evaluator.py
python -m skillopt.skill_validation smoke --output outputs/skill_validation/first_offline_smoke
```

上述测试与第一阶段 smoke 不需要密钥，不调用模型。真实产物执行需要匹配的 Linux Docker 隔离环境；不可用时返回 unsupported / unknown，不退回宿主裸跑。真实实验还需要数据、父 Skill、冻结源码及来源回执，见[复现与发布边界](docs/research-overview.md#复现与发布边界)。

API 字段参考 [`.env.example`](.env.example)，密钥只放本地 `.env`。本轮模型为 BigModel `glm-5.3`，显式新 provider 与旧 PJLAB 运行分开记录，不能混用缓存身份。仓库发布代码、测试、协议、精选报告与脱敏聚合结果；不发布密钥、原始 API 日志、运行缓存或未确认授权的第三方数据。

## 接下来要证明什么

确认与预算归因、公共修订回归保护均已完成；下一步统一使用可靠求解配置，保留真实修复轨迹学习，并接入具有真实依赖及目标机制错误空间的新任务，而非继续增加接近满分的小题。历史目标课程保持独立；另用未消费数据校准执行前审阅与逐缺口Research，按实际成本区分资料增量。未授权Research不进入正式学习/准入反馈，shadow探索另行标记。再接Skill准入与Coding→Spreadsheet迁移，不以反复使用旧确认集或全部回退替代泛化证据。

## 致谢

原始训练框架来自 [Microsoft SkillOpt](https://github.com/microsoft/SkillOpt)，上游指南见 [docs/index.md](docs/index.md)。保留原项目 [MIT License](LICENSE)；第三方任务遵循各自授权，不自动适用本仓库许可。
