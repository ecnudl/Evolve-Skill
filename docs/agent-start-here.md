# 无上下文代码代理接手指南

**新测量仪器：KOR无标签适用性验证器（10/4，零调用，Codex四轮后ACCEPTABLE）**——见[验证器报告](kor-applicability-verifier-20261004.md)；Linux冻结源码`/root/kor-applicability-20261004-v4-source`，结果`/root/kor-applicability-20261004-v4-{e,f-s1}`（v1–v3目录为审查前版本，勿引用）；**v5加入9条cipher规则（Codex两轮后ACCEPTABLE）**：冻结源码`/root/kor-applicability-20261004-v5-source`，结果`/root/kor-applicability-20261004-v5-{e,f-s3}`（`-v5pre-*`为审查前试跑，勿引用）。cipher探针`/root/kor-probes-20261004-v5`（生成器v5，Codex两轮ACCEPTABLE）与v8备选试点目录`/root/kor-probe-pilot-20261004-h`（冻结源码`/root/kor-probe-pilot-20261004-v8-source`；启动需用户批准标记`user-approved-v8`）。

**10/4夜间值守与待运行队列**：见[值守记录](overnight-status-20261004.md)——F进度与原因分析、两个已审查待付费的试点（BCB反馈内容、KOR探针阶段，均等F完成）、以及提案。

**待运行：BCB反馈内容试点（10/4）**——代码已审查、零API冒烟通过，Linux冻结源码`/root/feedback-pilot-20261004-source`；F的S1阶段记录生成后才`prepare`，F全部结束后才付费`run`，见[试点报告](feedback-ablation-pilot-20261004.md)。

**最新运行：新 F（10/3 18:57启动）**——SkillOpt后GEPA、学习v7、32,000字节接口、派生评测源码；先读[新 F 报告](fivebench-f-skillopt-gepa-20261003.md)再接手，运行中的进度不是结果。

建立：2026-10-02。项目对外名称为 **Evolve-Skill**，代码包仍为 `skillopt`，基于 Microsoft SkillOpt。先读 [AGENTS.md](../AGENTS.md)，再用本页辨明目标、证据和入口；当前流程与结论以[当前完整流程](current-workflow.md)、[结果账本](results-and-lessons.md)为主，不从某个历史 `coevolution_vXX` 目录推断进度。

## 当前会话工作中 / 待更新

**新接手入口：[新 E：SkillOpt五域补跑](skillopt-generalization-e-20261003.md)。** 18:13归档终态为完整学习4/5、全域矩阵闭合5/5：只有S1更新Skill，S2/S3/S5候选超长而无更新，S4 Pending携父，最终Skill与S1相同。见[绑定结果](results/skillopt-generalization-e-final-20261003.json)。本地新增[learning v6工程修复](learning-v6-engineering-repairs-20261003.md)，只做离线验证，未修改E冻结v5、未启动v6正式实验。后续需新manifest与输出；不可将本地代码同步覆盖E源码。旧D和C的SkillOpt/GEPA均完整学习0/5，见[D终态](results/skillopt-generalization-final-20261003.json)与[C终态](results/fivebench-sequence-c-final-20261003.json)。连通和代理操作遵循AGENTS.md，按当前路由核实，不重启或关闭Clash。

**旧 C 与新 D 分开。** [旧 C baseline 接续报告](baseline-continuation-20261002.md)保留原五域尝试；旧 C 的 SkillOpt 五阶段尝试已全部终止，完整学习 **0/5**，25格都是携空父后引用旧 No-Skill，不能称为学习收益。新 D 使用独立目录，不覆盖原 Pending。此前[阻塞修复报告](skillopt-blocker-repairs-20261002.md)中的Coding/QA/KOR小闭环3/3、24调用、0unknown且均未接受候选，只是工程smoke，不是正式全规模效果。

**历史快照（10/2 18:31，不是当前进度）：** 当时 `continual-learning-v3` 五域适配及双方法有限阶段队列已实现，完整离线回归为 **4,264 passed / 15 skipped**，属于工程证据。被动链接 B 通过41＋18＋2资格，但160位置重评仍 **79/55/26**，134旧已知保持、没有额外覆盖收益；v9c窄display修复已测试/独审并排队，43＋18＋4真实资格当时尚未执行。SkillOpt于 **10/2 17:51 在Linux实际启动**，截至18:31前三阶段因反思解析、工作簿unknown和服务sensitive分别Pending携空父，当时正在KOR第4域、GEPA排其后；首候选36/65低于空父42/65。该快照的15个矩阵格仅引用既有空策略数据，不是新观测或有效学习。后续以对应运行报告和实际回执为准。

若实现或运行产生新结论，先补齐会话报告中的协议、完整分母、模型、数据来源、未知与成本，再同步[当前流程](current-workflow.md)和[结果账本](results-and-lessons.md)。不要用更新日期替代内容维护，也不要覆盖旧结果。本指南不另立第三份完整实验账本。

## 项目最终要证明什么

目标是 **Cross-Domain Safe Skill Evolution**：通过有依据的 Coding Rubric 和有界 Research，改善 Skill 的解题机制、适用条件及例外，使目标任务受益，并控制其他任务的回归。目标不是每域达到最高分，也不是让模型在 Skill 中自行宣称“可泛化”。

主线设计为：开发配对发现问题 → Research/Rubric 提出验证改进 → 冻结并独立校准验证器 → 获准后生成开发反馈 → 更新 Skill → 冻结候选与范围 → 独立确认 → Skill Gate → 固定决策后的 final。

- **Verifier Gate**判断一套完整验证流程可在哪些义务和范围提供反馈；接受验证器不等于接受 Skill。
- **Skill Gate**比较 No-Skill / Current / Candidate，决定 Local Commit / Restrict / Reject / Pending；保留或回退空父不等于学会泛化。
- `development train`、可反复选候选的 `development selection`、`verifier_calibration`、`skill_confirmation` 和 `final` 各有用途。不得把 selection 改名为独立 final，也不得将隐藏测试或答案伪装成 Research 找到的公开知识。

当前 Research 是限定来源与预算的研究模块；公开双门 CLI 中仍有 scripted 工程控制。历史真实更新、独立校准接口和工程准入不能拼接成一场不存在的自然端到端实验。

五域持续学习的目标顺序为 **BigCodeBench → SpreadsheetBench → SearchQA → KOR-Bench → ALFWorld**。S0 是共同空 Skill；每完成一个来源学习阶段，冻结 S1…S5，并在每个阶段评全部五域，形成每方法/历史的 **6 个检查点 × 5 域**矩阵。需要同时报告来源收益、前向/后向迁移、最差域、回归与 unknown。**五域 baseline 适配和队列已实现，不代表五阶段实际训练已跑完，更不代表 Research 双门主线已完成。**

## 已核验的起点，以及不能据此声称什么

10/1共同长流式 No-Skill 使用 BigModel `glm-5.3`、`low`、每调用上限65536、read300/wall1800。五域开发基线共 **1,419 个任务条目 × 2 次重复＝2,838 个位置**，不是2,838道独立题，也不是新独立 final。原始成绩保留如下：

| 域 | 任务 × 重复 | pass / fail / unknown |
| --- | ---: | ---: |
| BigCodeBench | 400 × 2 | 400 / 399 / 1 |
| SpreadsheetBench | 80 × 2 | 63 / 44 / 53 |
| SearchQA | 400 × 2 | 560 / 234 / 6 |
| KOR-Bench | 500 × 2 | 746 / 243 / 11 |
| ALFWorld | 39 × 2 | 65 / 13 / 0 |

来源：[五域完整摘要](results/noskill-fivebench-long-20261001.json)。模型调用、HTTP尝试、tokens、缺失usage和容器成本见摘要及其来源链接；任务位置不是API次数，ALFWorld一条轨迹有多次交互。运行完成也不表示所有任务的评分环境已通过资格。

以下是截至10/1已归档的 **Coding / BigCodeBench 单阶段**自然学习结果：旧开发划分为65条训练任务（64族）＋64条选择任务（64族），当时适配仅支持该域，不是五域学习。本次 v3 使用新协议与新任务族划分，不冒充原阶段的无损续训：

| 方法或分支 | 已归档结果 | 可得结论 |
| --- | --- | --- |
| 官方 GEPA 适配 | 两次循环；完整选择候选28/64，空父33/64，官方选择保留空父 | 没有新的非空选中 Skill，没有已执行 S1 跨域结果 |
| 原 SkillOpt 长输出运行 | 反思JSON格式问题导致 Pending | 原状态不因后续诊断而解除 |
| SkillOpt 有限重提分支 | 新协议下候选31/64，对空父33/64被拒 | 保留空父；不是原优化器无损续训或新的被接受 S1 |

证据：[GEPA](results/gepa-long-learning-20261001.json)、[SkillOpt原Pending](results/skillopt-long-pending-20261001.json)、[有限重提终态](results/skillopt-reproposal-final-20261001.json)。条件化归纳shadow为32/64；普通归纳另行补齐为34 pass/29 fail/1 unknown，原Pending不改。单历史、小分差及已消费选择集不足以认定方法优劣；不应反复调提示直到同一选择集通过。

10/2工作簿诊断只重评原80题×2产物。旧v8b为70/48/42；冻结参考缓存H的B负结果为51/41/68，C经34项引擎＋18项评分控制后为 **79/55/26**。C相对v8b恢复16个未知，原118个已知结果保持；这些是评分覆盖改善，没有新模型调用或新答案。参考缓存只是冻结数据标签，不是独立的新鲜真值；候选仍须隔离重算并通过兼容检查。原No-Skill表格不回写。

C另有明确标为**回顾性**的端到端侧车 **79/61/20**：仅5个证据确认的程序失败＋1个完整闭合的预算耗尽从内容unknown列为交付fail，内容成绩仍为79/55/26；契约歧义和提取器问题仍未知。它不是原实验预登记指标，更不是Skill收益。[完整解释](unknown-recovery-results-20261002.md#午后恢复冻结h参考标签与交付分轴) · [C语义终态](results/unknown-sheet-frozen-gold-c-replay-final-20261002.json) · [C交付侧车](results/unknown-sheet-frozen-gold-c-delivery-20261002.json)

既往实验支持“存在真实局部更新、工程校验和评分覆盖问题”，尚不支持稳定语义正迁移、Research独有信息收益、完整五阶段协同学习或跨域部署授权。答案修订、交付恢复、空父回退、fixture通过和方法效果必须分别报告。

## 从哪里读、改哪里

阅读顺序：[AGENTS.md](../AGENTS.md) → [当前完整流程](current-workflow.md) → [结果账本](results-and-lessons.md) → [新 D 运行报告](skillopt-generalization-20261002.md)，再结合本页代码地图。按任务补读[研究索引](research-overview.md)、[旧 C 历史接续](baseline-continuation-20261002.md)、[阻塞修复](skillopt-blocker-repairs-20261002.md)、[五域评测接口](skill-validation-continual-evaluation-20260928.md)与[baseline适配边界](continual-baseline-adapters-20260928.md)。日期报告中的启动中/Pending可为历史快照；以绑定实际运行的最新终态为准，不改写历史快照。

| 要处理的工作 | 代码入口 | 当前边界 |
| --- | --- | --- |
| 冻结面板、检查点、生成/评分/报告 | [continual_eval/cli.py](../skillopt/continual_eval/cli.py)、[core.py](../skillopt/continual_eval/core.py)、[runner.py](../skillopt/continual_eval/runner.py) | `checkpoint`登记外部Skill，不训练，不授予部署权；评测分数默认禁止回流 |
| 五域公开输入与原生执行 | [backends.py](../skillopt/continual_eval/backends.py)、[datasets.py](../skillopt/continual_eval/datasets.py) | 前四域共同一次生成；ALF是交互轨迹，不能悄悄给某方法增加修订机会 |
| baseline学习与公开反馈适配 | [run_continual_learning.py](../scripts/run_continual_learning.py)、[contracts.py](../skillopt/continual_learning/contracts.py)、[feedback.py](../skillopt/continual_learning/feedback.py)、[ledger.py](../skillopt/continual_learning/ledger.py)、[gepa.py](../skillopt/continual_learning/gepa.py)、[skillopt.py](../skillopt/continual_learning/skillopt.py) | 学习v1/v2仍限Coding；v3允许五域，v4显式增加有界恢复；只投影公开输入、模型产物及标量反馈，unknown不作失败反馈 |
| 五阶段有限队列 | [continue_fivebench_baselines.py](../scripts/continue_fivebench_baselines.py)、[新 D 配置](../configs/continual_learning/fivebench_sequence_v2.pjlab.json) | 序列v1对应旧C，序列v2对应新D的SkillOpt-only学习v4；冻结祖先、源码/环境和角色，学习/评测服务分别核验；相同策略引用不算新独立重复，安全Pending携父但不计完成 |
| 已学习检查点与配对诊断 | [prepare_learned_checkpoint.py](../scripts/prepare_learned_checkpoint.py)、[compare_baseline_checkpoints.py](../scripts/compare_baseline_checkpoints.py) | 需实际选中的非空Skill及完整来源；不能重新采样空父来制造S1效果 |
| Rubric、Research、校准与Skill准入 | [stage2.py](../skillopt/skill_validation/stage2.py)、[calibration.py](../skillopt/skill_validation/calibration.py)、[admission.py](../skillopt/skill_validation/admission.py)、[closed_loop.py](../skillopt/skill_validation/closed_loop.py) | 原生baseline队列不是Research双门自然端到端闭环；先核对真实/fixture角色 |
| 冻结H评分与交付分轴 | [replay_sheet_frozen_gold.py](../scripts/replay_sheet_frozen_gold.py)、[sheet_frozen_gold.py](../skillopt/continual_eval/sheet_frozen_gold.py)、[report_sheet_delivery_outcomes.py](../scripts/report_sheet_delivery_outcomes.py) | 新目录独立诊断，不自动替换学习评分器、原输出或原分数 |
| 真实运行只读观察与对比导出 | [monitor_experiment_jobs.py](../scripts/monitor_experiment_jobs.py)、[report_fivebench_generalization.py](../scripts/report_fivebench_generalization.py) | 观察不代替正式回执；报告写入研究目录外的新快照，分开全矩阵与学习族排除子集；不自动恢复、重抽或宣布成功 |

仓库常有未提交研究文件；先看 `git status --short`，保留无关修改。新行为、源码、评分器或预算需要新版本和输出目录；不要直接用当前开发源码续写历史冻结目录。

旧 C 的一个阻塞是可选 `json_repair` 缺失时非法JSON转义解析失败。新 D 学习v4已通过[严格JSON桥](../skillopt/continual_learning/reflection_json.py)只保留非法转义的字面反斜线，并另存审计；不依赖宽松修复库、不改原始回执或旧 Pending。有限交付恢复见[显式策略](../skillopt/continual_learning/recovery.py)。这不保证消除所有解析、过滤、工作簿或预算未知，仍不得在共享冻结环境静默安装依赖。

## baseline与上游方法的关系

GEPA适配固定官方commit `d771eb21b5dd3228bc3f567293d2ccfc423fc900`，调用真实官方搜索、Pareto选择、反思变异和完整selection，保留官方最优候选选择；本项目固定 `use_merge=False`、仅优化不超过6000 UTF-8 bytes的Skill、共同模型/solver与开发划分。SkillOpt复用仓库原生反思、聚合、排序、裁剪、应用与gate，增加受限开发轨迹和调用账本适配。**这是项目配置下的算法适配，不是原论文数字复现。**

历史共同协议只对齐预设预算上限：GEPA使用minibatch，SkillOpt使用全量训练反思，实际调用与算力不相等。新 D 仅运行SkillOpt且另立恢复/预算，不与旧GEPA冒充等算力对照。unknown触发Pending、独立有限重提、单次生成协议等差异须随结果注明。9/27的DSL可靠求解/一次公开修订不等于本轮原生五域协议。TextGrad尚未接入；普通反思或压缩经验不能直接冠名为原版TextGrad/Reflexion。具体来源与约束见[适配记录](continual-baseline-adapters-20260928.md)，当前实际结果以封存JSON为准。

## 安全核验与续跑顺序

1. **先查已有证据。** 对照当前用户任务和会话报告，读取实际plan/protocol、源码与环境身份、intent、call/receipt、位置结果、终态报告、进程/容器及共享锁。失败启动要保留；有intent无终态先核实，不自动重抽。已完成记录使用冻结版本的只读检查/report，不能当新模型样本。
2. **准确判断远端连接。** 先试用户原命令 `ssh PJ-CL4MIND-DULIN`，再用 `ssh -O check PJ-CL4MIND-DULIN` 区分现有ControlMaster与新握手；不要结束用户master。先分清网络/TLS和API授权失败，不凭超时判断密钥失效。
3. **在Linux同一shell启用代理。** 下载或调用外部API前执行Linux上的 `proxy_on`；非交互时可用 `ssh PJ-CL4MIND-DULIN "bash -ic 'proxy_on && YOUR_COMMAND'"` 的形式。`trust_env=False`客户端需显式已批准代理，且写入新协议/缓存身份；不是在Mac或另一SSH会话里开代理就生效。首次真实响应确认后才释放并发。
4. **执行边界不能退化。** 生成代码、官方表达式评分和真实候选工作簿只能在经资格验证的隔离环境运行，缺环境保留unknown；不裸跑宿主、不在日常Excel中打开候选、不开宏或联网外链。原生任务共用冻结的`native.lock`；长任务采用Linux后台运行。精确暂停/恢复能力因入口而异，GEPA/SkillOpt旧中断阶段不支持自动恢复完整优化器状态。
5. **不得用网络或数据改写掩盖失败。** 不停止、重启或全局改Clash，不修改默认路由。VPN网关临时路由仅按AGENTS重新核验当前地址、接口和用户授权，记录精确回滚；活动实验期间不移除。禁止输出`.env`、API密钥、代理凭据、私有API缓存、隐藏答案或未经审查的第三方数据；发布脱敏汇总而非原始缓存。

文档说明、只读检查和工程fixture不需要付费实验。运行命令必须来自实际冻结协议和本次用户授权，示例配置不是运行许可；已有授权的正常续跑不应因本指南额外重复索要确认。每次交接说明完成项、剩余项、实际成本及证据路径，让下一代理可以先核验再行动。
