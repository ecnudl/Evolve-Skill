# 跨域安全 Skill 进化：研究索引

索引更新：2026-10-02。目标是通过 **Coding Rubric + 有界 Research** 提高 Skill 学习与范围判断的质量，兼顾多领域收益和负迁移，而不是逐域追求最高分。

从现在起优先维护两份主文档：[当前完整流程](current-workflow.md)记录每环节输入输出、初始化及实现状态；[结果与经验账本](results-and-lessons.md)精选重要实验、完整关键对照及数据来源。本页保留历史导航，以下代码地图和证据表为截至 9/23 的索引，不代替主文档的最新状态。9/24 新增规则学习与课程的真实试跑仍 Pending，尚无新 Skill 确认成绩，见[课程报告](skill-validation-capability-curriculum-20260924.md)。

9/25[同课程机制归纳对照及后续实验](skill-validation-mechanism-study-20260925.md)已完成：30题开发/78题确认、3历史。local比Base多20个通过位置，19来自截断减少、1来自不终止代码消失；mechanism全no_update，没有机制策略优势。修复轨迹已真实进入更新，96个后续实际规则注入位置未观察到干扰，但没有语义增益证据；新增源码修改面板No-Skill满分，再次暴露难度天花板。C逐例候选确认净增9项均涉及交付；G预算诊断显示预算扩大后原始分差从18/156降至8/156。独立回执复核完成，[结果JSON](results/skill-validation-mechanism-20260925.json)保留分母/成本。无Research独有增益或跨域结论。

## 阅读顺序

首次接手按 [AGENTS.md](../AGENTS.md) → [当前完整流程](current-workflow.md) → [结果与经验账本](results-and-lessons.md) → [新 D：SkillOpt 五域补跑与 No-Skill 对比](skillopt-generalization-20261002.md)阅读；[无上下文代码代理指南](agent-start-here.md)补充目标、代码地图和安全边界。两份主文档维护当前状态，日期报告及实际回执提供具体证据，本索引不另立实验账本。

**10/2 22:18 核验：新 D 前三来源阶段 Pending，KOR 阶段进行中，尚无完整五阶段学习或方法收益结论。** 新序列 v2 显式启用学习 v4，仅运行原生 SkillOpt；学习端有限恢复与新资格化 v7 工作簿评分另立身份，全域评测仍匹配原 No-Skill 的模型、预算、源码、环境和评分器。它不是 Research/Rubric 双门主线完成，也不是独立 final。

[旧 C baseline 接续实录](baseline-continuation-20261002.md)保留17:51启动及后续历史快照；旧 C 的 SkillOpt 五阶段尝试已终止、完整学习 **0/5**，25格只是携空父后复用旧观测。新 D 使用新目录，不改旧 C。工作簿被动链接 B 的独立诊断仍为79/55/26，工程资格通过未产生该面板的新覆盖收益；它及下文 H-C 评分诊断不等于学习阶段结果。

10/2[未知结果修复与复测](unknown-recovery-results-20261002.md)：最新冻结参考标签H v3经34＋18项资格，完整80题×2旧产物零API重评为**79通过/55失败/26未知**；较v8b70/48/42恢复16未知，118旧已知保持。过粗元数据预筛B为51/41/68，负结果保留。交付分轴另列回顾性79/61/20，不改内容分或旧基线；H缓存标签不等于新鲜真值。KOR10次截断恢复7/2/1。两项均为环境/交付诊断，不是Skill进化收益。[全量新终态](results/unknown-sheet-frozen-gold-c-replay-final-20261002.json)

10/1[长输出配置、新基线与工作簿兼容性](long-response-baselines-20261001.md)、[夜间监控与修复](overnight-baselines-20261001.md)：共同65,536-token配置下五域1,419题×2已完成，[聚合数据](results/noskill-fivebench-long-20261001.json)保留分母/成本。Coding No-Skill为400通过/399失败/1未知，SearchQA为560/234/6，各400题×2且无截断；KOR全500×2为746/243/11，ALF全39×2为65/13/0，Sheet80×2为63/44/53。Sheet未知中45项是交付后兼容限制、8项未交付，只有1次截断，仍不适合用总体平均掩盖覆盖不足。GEPA候选28/64、SkillOpt有限重提31/64、条件化shadow32/64，均未超过空父33/64；普通归纳34通过/29失败/1未知，原Pending不改，不能凭小分差断言效果。全400参考的数据层修复后397通过/2失败/1未知，5个资源缺口修复，但1个原通过参考超时使资格仍Pending；24控制发现已有进程池安全包装兼容问题，不改旧成绩。公式预览/ALF日志已补可选工程修复、未部署为新效果实验；下一步优先可信具体反例反馈对照，不把环境和交付改善当泛化收益。

最新评测入口：[9/28五基准、六检查点评测流](skill-validation-continual-evaluation-20260928.md)。统一数据导入、冻结检查点、公开求解、原生隐藏评分和迁移/配对报告。它接收外部冻结Skill，不替代协同进化和两道门；真实资源就绪范围见报告。

9/29[五域No-Skill开发面板](noskill-baseline-results-20260929.md)全部终态已齐备，[聚合JSON](results/noskill-fivebench-20260929.json)保留1419题×2的分母、unknown及成本缺失。Sheet大量不可判定、ALF中断等限制不能被平均分隐藏；这不是五域独立final。SkillOpt第一轮选择28/64低于空父39/64、被gate拒绝；第二轮截断Pending，GEPA未启动。[最新结果总表](experiment-results-20260929.md)与[学习JSON](results/skillopt-learning-20260929.json)保留完整/部分结果，暂无独立方法收益结论。

后续[No-Skill SearchQA开发基线及基线安排](skill-validation-baselines-20260928.md)已完成：400题×2、EM69.00%，0Skill/Research更新；[聚合数据](results/noskill-searchqa-20260928.json)保留重复差异、6个HTTP400未知和不完整成本。不能把这项单域已曝光数据结果称为五域独立评测。

最新工程补充：[9/27可靠求解配置与Linux验收](skill-validation-solver-reliability-20260927.md)；[验收JSON](results/skill-validation-solver-reliability-20260927.json)。它统一预算/格式、单次公开修订和回归保护，不改变9/25的历史效果结论，不改评测体系。

1. [9/23 执行前审阅与验证](skill-validation-admissibility-20260923.md)：执行前审阅、事实研究连接、真实旧产物重新执行、代码 review 和候选新数据；[9/23 反馈修订诊断](skill-validation-feedback-repair-20260923.md)与[9/24 规则更新实现](skill-validation-rule-learning-20260924.md)记录后续内容学习工作；[9/22 自然实验复盘](skill-validation-analysis-20260922.md)保留来源运行。
2. [新主线接口](skill-validation-mainline.md)：证据、分区、检查、授权与命令。按日期保存的章节反映当时状态，以最新章节为准。
3. [最小准入闭环](skill-validation-gated-loop-20260920.md)：两道门与工程控制实验。
4. [自然任务协议](skill-validation-natural-pilot-20260920.md)、[初期结果](skill-validation-natural-results-20260920.md)、[开发诊断](skill-validation-natural-development-diagnostic-20260920.md)：真实实验设计与目前不能继续作效果推断的原因。
5. [9/23 机器可读摘要](results/skill-validation-admissibility-20260923.json)：执行前审阅、格式与语义弃用、配对方向、Research 工程 smoke 及新数据盘点；[9/22 摘要](results/skill-validation-20260922.json)保留来源实验的分母、成本及记录哈希。
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
| 固定产物验证器诊断 | `natural_verifier_replay.py`、`natural_documents.py`、`probe_review.py` | 相同真实产物、受限资料、冻结探针 → 检错／误拒／配对方向与盲审消融；旧面板不产生新授权 |
| 执行前检查审阅与逐项 Research | `admissibility.py`、`probe_fact_research.py` | 固定检查 → 合法性审阅；仅外部事实缺口触发资料研究 → 再审同一检查 → 保留项执行；不改写 expected |
| 新管线充分性与回放 | `verifier_readiness.py`、`admissibility_study.py` | 真实固定产物 → 独立任务／错误族、误拒、unknown 和 Skill 配对方向；充分性不等于授权 |
| 面板诊断与历史适配 | `panel.py`、`legacy_panel.py` | 固定产物池／历史记录 → 宿主诊断；历史回放不计入新自然验收 |
| 运行恢复 | `reused_calls.py`；`scripts/resume_natural_validation.py` | 相同请求与已闭合回执 → 原样重放；新请求限流，断点不重抽失败 |

`closed_loop.py` 已完成 fixture 控制路径；`single_round.py` 已有真实小实验；`natural_study.py` 的 BigModel 运行已完成，但旧 Research 提案无效、回退分支共享候选，不能据此比较 Research 效果。三者不是三份已证实有效的方法。

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
| [9/20–21 自然面板历史断点](skill-validation-natural-pilot-20260920.md) | 当时 152 个任务；169/256 开发位置，87 待采集 | 仅为旧断点；后续完整运行见下一行，勿当作当前进度 |
| [9/22 BigModel 完整运行与复盘](skill-validation-analysis-20260922.md) | 同一 152 题划分；最终 No-Skill 70/80、Current 69/80、固定反馈候选 71/80 和 69/80 | 未证明稳定收益或跨域效果；71/80 的配对差异涉及 unknown，旧 Research 分支并非独立成功对照 |
| [9/22 固定探针盲审消融](skill-validation-analysis-20260922.md#8-后续消融冻结测试只审阅其可采纳性) | 无 Research 分支误拒 33→0，保留 72/80 个检查及新增检出；Research 分支新增 3 个检出位置来自同一共同错误任务 | 有检查质量改进信号；已消费面板、不同实际成本、无新授权，不是 Skill 泛化收益 |
| [9/23 执行前审阅与新执行](skill-validation-admissibility-20260923.md) | 81 次 API／682 次隔离调用；无 Research 来源误拒 33→0，Research 来源 10→0 但其中 6 个靠格式弃权消除；676 个保留探针执行一致 | 能减少错误反馈；Candidate 相对 Base 的退化仍 0/2 被识别。两来源 reviewer 都不读资料，不是新 Research 因果实验 |

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
