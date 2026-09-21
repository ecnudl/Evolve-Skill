# Evolve-Skill

基于 [Microsoft SkillOpt v0.2.0](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0) 的研究项目：**通过 Coding Rubric 与有界 DeepResearch 协同改进 Skill 的内容、验证和适用范围，降低跨领域负迁移。**

我们不要求每个 benchmark 都达到 SOTA，而是希望 Skill 学到可迁移的解题机制，在改善目标任务的同时保留其他领域的能力。泛化范围应由行为证据确认，不能由模型在 Skill 文本中自行宣称。

**截至 2026-09-21：最小闭环已通过工程测试；真实单轮内容更新已运行；Research 带来稳定跨域泛化收益仍未得到证明。** 这不是一个已经完成全部实验的论文复现包。

## 给首次阅读仓库的 AI / 研究者

建议按下面顺序阅读，不必从全部历史 `coevolution_vXX` 开始：

1. [研究索引与证据边界](docs/research-overview.md)：研究问题、代码地图、历史结果及不可支持的结论。
2. [最新进展与实验汇总](docs/research-progress-20260921.md)：上次推送后新增了什么、实际跑到了哪里、下一步缺什么。
3. [主线接口与运行说明](docs/skill-validation-mainline.md)：可见验证 V / 独立审计 H、分区、授权和入口。
4. [自然任务实验协议](docs/skill-validation-natural-pilot-20260920.md)与[公开汇总 JSON](docs/results/skill-validation-20260921.json)：对照、预算、分母和原始记录指纹。

分析时请区分**算法设计、工程 fixture、历史回放、真实模型实验**；给出的改进建议应指向具体代码或证据缺口，而不是默认方法已经有效。原始运行缓存未公开，汇总指纹不等于独立复核。

## 方法如何工作

1. **发现问题**：No-Skill / Current 在相同开发任务上执行，保留产物、公开检查和配对差异。
2. **进化验证器**：Research 针对验证缺口查阅限定资料；Rubric 表达任务义务、适用条件、例外和证据要求，实例化为可执行检查。
3. **先校准验证器**：独立校准检查新增检错、误拒、覆盖率与成本；没有可靠新证据，不授予相应反馈权限。
4. **再更新 Skill**：用绑定实际执行的反馈指导 Preserve / Repair / Restrict，允许删除或条件化父 Skill 中冲突的规则。
5. **独立确认与最终评价**：冻结 Candidate，与 No-Skill / Current 配对，决定 Local Commit / Restrict / Reject / Pending；分别报告强制使用和条件部署效果。final 不回流更新。

这是主线设计，不代表每个实验均启用了全部步骤：`closed_loop.py` 已用工程样例接通两道门；`natural_study.py` 是真实 Coding 单轮对照，目前只采集到部分开发产物，**不授予部署或跨域范围**。当前 Research 是限定来源和预算的研究模块，不是完整自主 DeepResearch。

## 最重要的实验结果

| 实验 | 观察 | 能说明什么 |
| --- | --- | --- |
| 历史 V8，64 个共同初稿的答案修订 | 简略反馈 51/64，结构化反馈 59/64 | 结构化执行反馈有价值信号；不是 Skill 进化或跨域效果 |
| 历史 V16，三域协同进化 | No-Skill 100%，固定验证器 96.30%，自适应 94.44%，Research 自适应 98.15% | 尚未优于 Base；面板有天花板，不能证明 Research 泛化收益 |
| 9/18，真实 MBPP-sanitized 单轮更新 | No-Skill 30/32、Parent 26/32、Candidate 27/32；16 题 × 2 次 | 更新链可运行，但两次重复的收益方向相反；三种反馈合并为同一候选 |
| 9/20，四组最小闭环 smoke | 162 次隔离执行；限制、拒绝、无新证据、样本不足路径均运行 | 工程验证，0 次模型 API；不是自然效果或部署授权 |
| 9/20–21，HumanEval+ 自定义自然面板 | 152 题划分 64/24/24/40；已保存 169/256 个开发位置 | 尚未完成验证器对照、Skill 更新和最终评测，不报告最终准确率 |

详见[最新汇总](docs/research-progress-20260921.md)及[历史三部分报告](docs/experiment-report-skill-validation-coevolution-20260916.md)。不能将不同任务面板直接横比；重复执行不等于新增独立任务，unknown 不等于语义错误。

## 代码入口与离线运行

新工作集中于 [`skillopt/skill_validation/`](skillopt/skill_validation/)，主要入口是 `stage2.py`（冻结产物验证器比较）、`closed_loop.py`（带准入的一轮流程）和 `natural_study.py`（自然任务对照）。历史版本与上游训练入口保留，不改写冻结协议。

Python 3.10+，建议使用独立环境：

```bash
python -m pip install -e ".[dev,searchqa,cross-domain,validator-pilot]"
python -m pytest -q tests/test_skill_validation_*.py tests/test_resume_natural_validation.py tests/test_spreadsheetbench_evaluator.py
python -m skillopt.skill_validation smoke --output outputs/skill_validation/first_offline_smoke
```

上述测试与第一阶段 smoke 不需要密钥，不调用模型。真实产物执行需要匹配的 Linux Docker 隔离环境；不可用时返回 unsupported / unknown，不退回宿主裸跑。真实实验还需要数据、父 Skill、冻结源码及来源回执，见[复现与发布边界](docs/research-overview.md#复现与发布边界)。

API 字段参考 [`.env.example`](.env.example)，密钥只放本地 `.env`。仓库发布代码、测试、协议、精选报告与脱敏聚合结果；不发布密钥、原始 API 日志、运行缓存或未确认授权的第三方数据。

## 接下来要证明什么

优先解决自然任务的检查覆盖与参考审计争议，完成已冻结的开发采集；再检验**相同预算下 Research 是否增加真实有效证据 → 是否改善 Skill 准入和更新 → 是否带来跨领域保持与迁移收益**。当前不以扩大多轮实验或全部回退替代这些证据。

## 致谢

原始训练框架来自 [Microsoft SkillOpt](https://github.com/microsoft/SkillOpt)，上游指南见 [docs/index.md](docs/index.md)。保留原项目 [MIT License](LICENSE)；第三方任务遵循各自授权，不自动适用本仓库许可。
