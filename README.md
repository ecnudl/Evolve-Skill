# Evolve-Skill

基于 [Microsoft SkillOpt v0.2.0](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0) 的研究项目：**通过 Coding Rubric 与有界 DeepResearch 协同改进 Skill 的内容、验证和适用范围，降低跨领域负迁移。**

我们不要求每个 benchmark 都达到 SOTA，而是希望 Skill 学到可迁移的解题机制，在改善目标任务的同时保留其他领域的能力。泛化范围应由行为证据确认，不能由模型在 Skill 文本中自行宣称。

**截至 2026-09-27：同课程归纳、修复轨迹学习、候选确认及预算诊断已完成，共同 Solver 可靠性修复已通过 Linux 工程验收。** 修复细节促成两份主候选，后续96个实际注入位置未观察到干扰，但没有证明语义正迁移。普通归纳多20个通过位置，19个来自截断差异；另一逐例候选净增9项也全部涉及交付。预算扩大后原始分差缩小，不能把交付稳定性当作泛化提升。历史目标课程A–D仍Pending；Skill稳定增益、Research独有信息增量与跨域收益均待证明。这不是已完成全部实验的论文复现包。

## 给首次阅读仓库的 AI / 研究者

9/27补充：[求解可靠性修复与Linux验收](docs/skill-validation-solver-reliability-20260927.md)已接通共同输出预算、一次公开修订及回归保护；完整工程smoke 9/9公开通过，另验证超时修订和保留正确初稿。没有调整评测体系，也不将这些工程检查算作泛化增益。

建议按下面顺序阅读，不必从全部历史 `coevolution_vXX` 开始：

1. [当前完整流程](docs/current-workflow.md)：持续维护的主文档，说明初始化、每步输入输出、Rubric/Research、反馈更新及两道门；明确真实与 fixture 状态。
2. [结果与经验账本](docs/results-and-lessons.md)：持续维护的重要实验表格、正向信号、反例、成本和数据存档索引。
3. [研究索引与证据边界](docs/research-overview.md)：更多历史报告与代码地图；日期报告不改写为新结果。
4. [主线接口与运行说明](docs/skill-validation-mainline.md)：按实现阶段保留的详细说明；最新对照见 [9/25 报告](docs/skill-validation-mechanism-study-20260925.md)，历史目标课程见 [9/24 报告](docs/skill-validation-capability-curriculum-20260924.md)。
5. [真实实验材料与离线 demo](examples/research_evidence/README.md)：已有真实 Skill、反馈、4 个配对代码案例与96个单轮评分位置；新增9/25真实“修复轨迹→规则→条件反转执行”及负例摘录。不是所有实验的完整原始数据。

分析时请区分**算法设计、工程 fixture、历史回放、真实模型实验**；给出的改进建议应指向具体代码或证据缺口，而不是默认方法已经有效。现在提供经过筛选的真实记录摘录；完整原始运行缓存仍未公开，记录回放不等于重新执行或独立认证。

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

新工作集中于 [`skillopt/skill_validation/`](skillopt/skill_validation/)：`stage2.py`（验证器比较）、`closed_loop.py`（带准入的一轮流程）、`natural_study.py`（自然任务对照）；本轮增加 `natural_verifier_replay.py`（真实固定产物诊断）、`probe_review.py`（盲审消融）、`public_examples.py`（公开示例覆盖诊断）。历史入口保留，不改写冻结协议。

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
