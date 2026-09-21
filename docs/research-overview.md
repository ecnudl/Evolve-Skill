# 跨域安全 Skill 进化：研究索引

更新：2026-09-21。目标是通过 **Coding Rubric + 有界 Research** 提高 Skill 学习与范围判断的质量，兼顾多领域收益和负迁移，而不是逐域追求最高分。

## 阅读顺序

1. [最新进展与实验汇总](research-progress-20260921.md)：实现状态、实际观察、当前断点。
2. [新主线接口](skill-validation-mainline.md)：证据、分区、检查、授权与命令。按日期保存的章节反映当时状态，以最新章节为准。
3. [最小准入闭环](skill-validation-gated-loop-20260920.md)：两道门与工程控制实验。
4. [自然任务协议](skill-validation-natural-pilot-20260920.md)、[初期结果](skill-validation-natural-results-20260920.md)、[开发诊断](skill-validation-natural-development-diagnostic-20260920.md)：真实实验设计与目前不能继续作效果推断的原因。
5. [机器可读结果摘要](results/skill-validation-20260921.json)：已核对的聚合数字、来源标识与记录哈希，不包含原始产物。
6. [真实记录 demo](../examples/research_evidence/README.md)：现已公开精选模型产物、实际反馈、父／候选 Skill 和完整单轮逐题评分摘录，可离线重算摘要；不是完整私有缓存或新的效果实验。

## 核心问题与方法边界

需要依次证明三件事：Research 提供普通验证器缺少的有效检查；这些检查改善对 Skill 增量与回归的判断；反馈和准入进而改善新任务及跨域表现。目前不能将其中一环的工程完成当作三环均成立。

验证器面对的是产物和执行证据，而不是给 Skill 文本主观打分。任务义务不能随 Rubric 改写，引用存在不代表规则成立。Research 可以返回 no_update；缺少证据保留 unknown。

验证器校准门与 Skill 准入门不同：前者限定一条验证管线可以在什么范围提供反馈，后者决定特定候选版本的使用范围。实现检查策略、实例化输入、执行器、适用性或聚合方法改变，都不能无条件继承旧授权。

当前 Coding 是 Python/JSON 函数任务，不是完整仓库修复。历史 Spreadsheet 机制任务多为公式 DSL，不等于真实工作簿。新主线没有自然跨域效果结论，也没有 Cross-Domain Commit 授权。

## 代码地图：从输入到输出

以下路径相对仓库根目录。新主线集中在 `skillopt/skill_validation/`，不另建 V19。

| 环节 | 代码 | 输入 → 输出 |
| --- | --- | --- |
| 契约、身份和隔离 | `models.py`、`views.py`、`partitions.py` | 任务／来源／产物 → 白名单 V 视图；H 留在宿主 |
| 公开检查与执行 | `engine.py`、`checks.py`、`sandbox.py`、`remote_executor.py` | 可见契约与受限检查 → 绑定任务、产物和运行的四状态证据 |
| Research 与可复用 Rubric | `research.py`、`stage2.py` | 固定开发证据与允许的摘要 → 条件化提案及来源追踪 |
| 自然任务策略与新探针 | `natural_policy.py`、`task_probes.py` | 冻结策略＋匿名产物 → 同题公共探针及实际执行结果 |
| 验证器校准 | `calibration.py`、`natural_metrics.py` | 冻结提案、独立校准 V/H → 有范围的 accepted / rejected / pending |
| Skill 内容更新 | `single_round_feedback.py`、`conditional_feedback.py` | 父 Skill＋公开配对证据 → 条件化更新提示；不直接读取 H 答案 |
| 候选准入与闭环 | `admission.py`、`closed_loop.py` | 获授权验证器＋冻结候选＋独立确认 → 决策、执行前选择与下一轮状态 |
| 自然实验编排 | `natural_data.py`、`natural_study.py` | 冻结数据、父 Skill、模型与预算 → 对照产物、诊断、条件更新及评测记录 |
| 面板诊断与历史适配 | `panel.py`、`legacy_panel.py` | 固定产物池／历史记录 → 宿主诊断；历史回放不计入新自然验收 |
| 运行恢复 | `reused_calls.py`；`scripts/resume_natural_validation.py` | 相同请求与已闭合回执 → 原样重放；新请求限流，断点不重抽失败 |

`closed_loop.py` 已完成 fixture 控制路径；`single_round.py` 已有真实小实验；`natural_study.py` 尚停在开发采集。三者不是三份已经完成的效果验证。

## 证据账本

| 实验 / 报告 | 数据与主要观察 | 允许的解读 |
| --- | --- | --- |
| [V9 SearchQA](coevolution-v9-source-results-20260913.md) | No-Skill EM 71.88%，选中 Skill 75.78%；普通门与新门选择相同 | 有来源学习信号，不能归因于 Research 或新门 |
| [V11 迁移回顾](skill-validation-quality-and-evolution-20260918.md) | 强制迁移 74.22%，No-Skill 77.34%；门控后 77.34%，启用覆盖率 0 | 回退保护，不是学会迁移 |
| [V8 反馈与校准](coevolution-v8-results-20260913.md) | 共同 64 初稿：简略反馈修订 51/64，结构化修订 59/64；校准旧＋旧 45/48、旧＋新 46/48，候选拒绝 | 答案修订有信号；不是 Skill 泛化或可靠 Research 增量 |
| [V12/V14 内容更新总结](experiment-report-skill-validation-coevolution-20260916.md) | 普通更新有局部收益；配对反馈未稳定优于普通反馈；局部更新仍有 Rule 退化 | 内容学习有潜力，新增组件优势未成立 |
| [V16](coevolution-v16-clean-resume-results-20260916.md) | No-Skill 100%；固定 96.30%、自适应 94.44%、Research 98.15%；自然新增检错 0 | 天花板面板，不能证明协同进化更优 |
| [V18 协议](coevolution-v18-protocol.md) | SearchQA + MBPP-sanitized；整体式／分层式；Research 不启用 | 双域适配，不是未见域；发布时完整离线审计链未闭合，不列效果结论 |
| [9/18 单轮真实更新](skill-validation-single-round-results-20260918.md) | 16 个最终任务 × 2 次：No-Skill 30/32、Parent 26/32、Candidate 27/32 | 重复方向相反；三种反馈收敛为同一候选，不能比较 Research 效果 |
| [9/20 准入工程闭环](skill-validation-gated-loop-20260920.md) | 四场景、162 次隔离执行，0 API；无新证据／样本不足阻止 updater | 工程流程正确性的证据，不是自然学习收益 |
| [9/20 自然面板](skill-validation-natural-pilot-20260920.md) | 152 个任务；169/256 开发位置，87 待采集 | 未完成对照和 final，不报告最终方法准确率 |

历史统计来自相应报告；这次重新核对了新主线本地汇总记录，并未重新运行全部历史实验。不同面板、重复次数、交付契约、评分器之间不能直接比较百分点。

## 数据边界与评价口径

- V 是模型可见的契约、产物、公开执行；H 是独立参考／隐藏审计。开发 H 摘要仅经显式接口使用，并标记其来源，不能归功于 Research 独立发现。
- 通用接口区分 development、verifier_calibration、verifier_audit、skill_confirmation、final。自然先导采用 64/24/24/40 四分区，没有额外独立 verifier_audit：校准上的改善是选择证据，不是冻结后独立效果估计。
- 按原任务／近重复族划分，不按同题产物随机划分。当前词面去重不能保证语义独立，更不保证公开题未进入模型预训练。
- 报告共同任务义务分母、正负迁移、unknown、覆盖率和成本；重复调用不是独立任务。预算相同不等于实际 token 成本相同。
- 准入安全与内容泛化分别评价：强制使用效果、条件部署效果和回退率不能混合。全部回退产生零新增学习收益。

## 复现与发布边界

- **离线测试**：README 的测试使用 fixture／模拟 API，不需密钥。CI 分开运行上游显式清单与研究离线测试；不等于所有历史外部集成均测试。
- **隔离执行**：新主线提供固定镜像的 Linux Docker 和 SSH 适配，见 [Linux 说明](skill-validation-linux-runtime-20260918.md)。无可用隔离环境时停止，不裸跑生成代码。
- **真实实验**：配置 `.env.example` 所列字段，自行准备有权使用的数据、父 Skill 及来源记录。已运行先导使用 `glm-5.3`；替换模型或冻结组件需要新协议。
- **数据版本**：HumanEval+ v0.1.10 使用自定义兼容分区和比较器，不是官方完整 pass@1。MBPP 单轮也只是静态兼容子集。SearchQA 等历史来源见各自协议。
- **历史材料**：`outputs/`、原始 API 日志、父实验缓存与完整执行证据包未公开。汇总 JSON 只摘录数字和原记录指纹，不能单凭 clone 独立重算所有结果；指纹不是真实性认证。
- **冻结恢复**：部分协议对全部主线模块计算源码哈希。最新 Git 代码不保证可直接写入旧运行目录；必须使用匹配快照。恢复脚本仅变更调度，不冒充另一种执行传输。
- **隐私与许可**：不公开 `.env`、密钥、私有机器配置、第三方数据快照；旧 SkillEvolBench 素材见[来源说明](../configs/validator_pilot/tasks/README.md)。

## 给进一步分析者的问题

优先核验：新增检查是否受公开义务支持；是否只发现 H 已经告诉模型的错误；在真实正确替代解上是否误拒；是否提高 Skill 改善／退化方向判断；最终收益来自内容还是回退。当前尚缺自然 Research 增量、可靠 Skill 准入质量、独立多历史和跨域结果，不应跳过这些直接宣称方法有效。

历史 `cross_domain/`、`scope_evolution_v2/`、`validator_pilot/` 和 `coevolution_vXX/` 保留用于依赖与审计，不是所有版本都推荐继续扩建。
