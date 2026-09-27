# 当前完整流程：Skill 与验证器如何协同进化

更新：2026-09-27。9/27接通统一可靠求解配置及Linux工程smoke；历史实验未重跑或改分，评测体系未调整。

本文是**当前流程的主文档**：实现或数据流改变时同步更新。实验数字集中维护在[结果与经验账本](results-and-lessons.md)，历史协议和日期报告原样保留。[研究索引](research-overview.md)用于查找历史材料。

## 1. 目标与当前完成程度

目标不是每个 benchmark 都最高分，而是学到有增量收益、较少负迁移的 Skill：验证其底层机制、成立条件和例外，再根据行为证据决定是否接受、限制或扩大适用范围。

**目前有可组合的实现、真实的局部实验和工程闭环，但还没有完成“新生成任务上的规则学习＋获授权 Research 验证＋跨域推广”的真实端到端验证。**

| 部分 | 当前已有 | 尚未完成或证明 |
| --- | --- | --- |
| Skill 内容学习 | 明确空初始化/来源导入；条件规则更新；真实修复轨迹已产生候选并完成后续执行 | 新任务上稳定的语义增益；来源训练父版本接入课程；跨域提升 |
| 验证器进化 | 条件 Rubric、资料研究、检查实例化、执行前审阅、独立校准接口 | Research 相对无资料对照的可靠信息增量 |
| 协同进化 | 历史 V16 实际发生多轮 Skill/验证策略更新；新双门闭环通过工程控制实验 | 真实自然数据上“新增有效检查→更好 Skill→更好准入”的完整证据链 |
| 历史驱动课程 | 全量开发摘要→能力目标已真实调用；6 个模型生成任务家族通过隔离资格检查 | 公平的 Generic/Targeted 学习对照尚未完成，A–D 均在准备阶段 Pending |
| 同课程机制归纳 | 44族资格与3历史完整确认已完成；local出现少量交付/产物可用性改善，mechanism全no_update | 未证明机制策略优势；只覆盖Coding，且无有效条件禁用 |
| 范围控制 | 当前 Coding 的 Local Commit / Restrict / Reject / Pending 接口 | Cross-Domain Commit、自动 Split、自然跨域部署授权 |
| 共同求解协议 | 9/27可靠配置统一初稿/修订预算、格式、一次修订和公开回归保护；真实工程验收完成 | 新配置下的独立方法比较；不能用工程smoke推断总体通过率提高 |

以下把**应该如何连接**与**哪些入口实际连接了**分开说明，不能把不同实验拼成一次已经成功的运行。

### 9/23–9/27：本阶段实际新增了什么

- **初始化与演化边界**：区分可追溯但弱的历史父、空规则包与来源训练导入；规则更新绑定父版本、公开证据、适用条件和例外，不因文本写得通用就获得更大授权。
- **可用于学习的反馈**：由最终布尔结果扩展到全量配对摘要、逐例观察、初稿→修订轨迹；被修复或被回退的错误经验不再随最终成功而消失。F→T已真实走完“修复证据→规则提案→冻结→后续任务执行”，但没有Research参与，也未证明正迁移。
- **验证反馈的质量控制**：先审查测试依据和适用性，再执行；具体外部事实缺口有有界Research接口。盲审有真实过滤错误检查的信号，按缺口Research的独有增量仍待新数据验证。
- **公平、可归因的共同执行**：将交付失败、语义失败、执行未知分开，并把预算及修订保护统一给Base和候选。它减少实验混淆，不应记作某个Skill独享的方法改进。

对应证据与局限见[结果账本](results-and-lessons.md)；完整归档见[9/23审阅](skill-validation-admissibility-20260923.md)、[9/25学习与归因](skill-validation-mechanism-study-20260925.md)、[9/27可靠性验收](skill-validation-solver-reliability-20260927.md)。

## 2. 先区分六个对象

| 对象 | 是什么 | 不是什么 |
| --- | --- | --- |
| 任务契约 | 原任务要求、公开例子、输入输出约定、必须满足的义务 | 可以由 Research 为提高分数随意改写的标准 |
| Skill | 给 Solver 的可复用解题指导；新表示是带条件、例外和证据引用的规则包 | 模型参数训练，也不是题目标准答案 |
| 可复用 Rubric / 验证策略 | 检查什么义务、何时适用、需要什么证据、如何生成及汇总检查 | 某一道题的几个测试输入 |
| 任务级检查 / probe | 把冻结策略应用到具体任务后得到的调用、预期结果或关系 | 新 benchmark 任务，也不自带正确性保证 |
| Research | 针对验证知识缺口查阅限定资料，提出或支持检查 | 最终评分 oracle；目前也不是开放式长程 DeepResearch Agent |
| 能力任务家族 | 为某项待检验能力生成的新任务及契约变体，用来学习或确认 | 给原题多加几个输入；与 probe 生成是两个模块 |

## 3. Skill 从哪里来、数量多少、如何调用

### 初始化

[skill_seed.py](../skillopt/skill_validation/skill_seed.py)提供三种来源接口：

| 来源 | 输入 → 输出 | 当前用途 |
| --- | --- | --- |
| `cold` | 学习历史 ID → 空 Skill / 空规则包 | 9/25固定面板对照已实际使用共同空 `RuleSkill`；9/24历史目标课程A–D仍未进入真实学习 |
| `source_trained` | SkillOpt 源域 best/checkpoint、宿主审阅的来源与选择声明、文件哈希 → 冻结 seed | 导入与测试已实现，尚未接入当前课程 driver；不按 final 选父 Skill，不自动认证训练效果或转换成结构化规则 |
| `legacy_diagnostic` | 历史文本与来源指纹 → 诊断 seed | 保留弱父版本，不能冒充成熟、独立验证过的源域 Skill |

9/22–23 自然实验的 Current 来自 **V16 第一条历史、第一轮、fixed 分支**：模型从空文本、两道合成 Coding 题的轨迹中生成。它可追溯，但不是 SkillOpt 充分训练后选出的 best Skill。[来源核对](skill-validation-feedback-repair-20260923.md)

历史目标课程`curriculum_study`仅把该旧父及其历史当作**发现假设的背景**。driver 设计为让 Generic 与 Targeted 都另从相同空规则包开始，重新收集各自证据；该入口真实试跑尚未到达学习阶段，旧父的产物不能作为新父的行为证据。另一个固定面板入口`mechanism_study`已完成真实空父更新，两者不能混称同一次课程实验。

### 优化对象与调用

- 一条学习历史维护一个 Current 规则包，再生成 Candidate；不是大量独立 Skill 等待向量检索。
- [RuleSkill](../skillopt/skill_validation/rule_skill.py)最多 8 条规则、渲染不超过 6,000 UTF-8 bytes；每次最多 2 项新增、替换或删除。规则包含机制、操作、适用条件、例外、scope 和证据引用。
- 固定 JSON 交付要求、工具权限和一次公开修订机会属于执行协议，不作为“学出的 Skill”。
- [rule_solver.py](../skillopt/skill_validation/rule_solver.py)将规则渲染为文本交给 Solver。`raw` 使用全部规则；`conditional` 仅按执行前公开义务类型筛选，不是学习型语义路由，也不等于获得部署授权。
- **历史目标课程配置为用 `raw` 强制使用候选**，以观察内容本身的收益/损害；该入口尚未产生真实确认成绩。固定面板A/C另有已完成的raw/conditional比较，T为raw；不按隐藏成绩选择是否启用Skill。
- 冷启动 Current 与 No-Skill 文本完全相同；相同请求可共享缓存，不能称为两次独立学习证据。不同版本/实际注入文本均绑定各自哈希。

## 4. 数据与证据边界

| 数据用途 | 输入与允许用途 | 禁止用途 |
| --- | --- | --- |
| `development` | 发现缺口、产生 Rubric/Skill/适用条件候选 | 把开发效果当独立泛化成绩 |
| `verifier_calibration` | 冻结验证管线后决定是否授予限定反馈权限 | 按结果反复改同一提案直到过门 |
| `verifier_audit` | 冻结后独立评价验证器判断质量 | 回流修改待评验证器 |
| `skill_confirmation` | 冻结 Candidate 与范围后进行配对准入 | 用确认结果改范围，再用同批数据宣称已确认 |
| `final` | 评价冻结 Skill、验证器和部署决策 | 决定当次路由、修改 Skill 或门槛 |

这是用途划分，不代表每个历史实验都有五套数据。9/22 自然先导为 **64/24/24/40** 四分区（开发/验证器校准/Skill 确认/final），没有额外独立 verifier_audit。最新课程只有开发与共同确认的 shadow 对照，未接入正式两道门。

可见证据 **V** 包括公开契约、允许查看的代码和公开执行回执；独立审计 **H** 包括隐藏检查、参考实现结果或人工核验。验证与更新使用白名单视图，不把整个宿主记录放进 prompt。开发 H 的漏检/误判摘要只有专门接口可以使用，必须标成“宿主开发诊断”，不能归功于 Research 自主发现。最新历史课程规划只读公开 V。

原任务/近重复族强制隔离；项目隔离仅在 `project_disjoint=True` 时启用。重复执行、同题三种 Skill 条件、家族内条件变体不是独立新任务。消费锁作用于当前 ledger/output，跨实验目录仍需统一曝光记录；新建目录不使旧数据重新成为独立数据。来源区分真实模型、fixture、人工 mutant、生成规格；旧记录来源不完整不能用来正式验收。[可见视图](../skillopt/skill_validation/views.py) · [分区实现](../skillopt/skill_validation/partitions.py)

## 5. 主线 A：从历史表现到更有针对性的 Skill 学习

当前入口：[curriculum_study.py](../skillopt/skill_validation/curriculum_study.py)。下面是该入口已经写好的顺序，**不是本次真实运行已经走完的顺序**。

| 步骤 | 输入 | 处理 | 输出 / 当前状态 |
| --- | --- | --- | --- |
| A1 回放历史 | 旧父版本、development 任务/产物/公开回执 | 校验绑定，汇总所有配对，分层展开案例 | 64 题×2 次的 128 对摘要＋10 对详情，已有真实记录 |
| A2 定义能力目标 | 同一公开历史、固定执行协议 | 模型列失败假设、竞争解释、证据与所需任务角色，可 no_update | 1–3 个能力目标；真实调用已完成，不把单次失败判成 Skill 过拟合 |
| A3 提议开发课程 | Generic 不看目标；Targeted 看预登记的首个历史目标 | 模型选择受限操作规格，宿主编译任务 | 每臂默认 6 个结构家族；真实生成存在格式/预算失败 |
| A4 资格、隔离与冻结 | 两组开发规格、随后生成的共同确认规格 | 参考实现交叉核对、控制产物、结构/有限行为去重 | 冻结任务池；两组开发可重叠但须报告，开发与确认不得重复；完整步骤目前仅 fixture 贯通 |
| A5 开发求解 | 同一空父、各臂开发任务、相同执行预算 | No-Skill/Current 求解，公开执行，再给一次修订机会 | 最终产物、初稿/修订稿、公开证据、调用成本 |
| A6 汇总反馈 | 与当前父版本匹配的全部开发配对 | 全量摘要＋预算内详情，区分改善/回归/共同失败/unknown | 更新器可见反馈及证据目录，不含 H 答案 |
| A7 更新规则 | 父规则包、公开反馈、相同 updater | 最多两项编辑；核对父哈希、引用与 scope | 新候选 / no_update / invalid；元数据变化不计行为学习 |
| A8 共同确认 | 冻结 Generic/Targeted 候选、共同确认任务 | No-Skill 与两候选强制使用，各自干净执行，之后宿主 H 评分 | 配对胜负、逐族结果、unknown 与成本；真实试跑尚未到达 |

历史摘要由 [development_feedback.py](../skillopt/skill_validation/development_feedback.py)形成，能力目标由 [capability_goals.py](../skillopt/skill_validation/capability_goals.py)提出，规则由 [rule_learning.py](../skillopt/skill_validation/rule_learning.py)更新。还有 `whole_text` 更新对照接口，但最新课程比较的是 **Generic vs Targeted 课程**，不是规则式 vs 全文式 Skill 的真实效果实验。

目标规划另存一个删除历史结果/代码的 `outcome_blind` 消融；它仍使用同一批历史案例契约，不是完全随机选题的无历史基线，也不是额外完整学习臂。

### 任务究竟怎样生成

[curriculum_tasks.py](../skillopt/skill_validation/curriculum_tasks.py)目前只支持有界整数列表 DSL：过滤、变换、排序/去重、聚合；模型选 2–3 个操作，不提交任意判分代码或标准答案。每个结构家族编译成三个完整契约任务：

1. 必须保留输入。
2. 必须原地修改为指定变换结果。
3. 不限制输入是否被修改。

输入范围是长度0–8、元素为−9到9的整数列表（不含bool）。每题4个公开示例、175个宿主审计输入，其中3个与公开输入重合。任务资格检查每规格使用176个输入×3个契约角色，共528次参考/角色比较，并检查错误返回、错误状态与正确替代解；这**不是528个独立任务，更不是Verifier Gate**。

默认开发每臂6家族×3契约×2次=36个配对，No-Skill/Current两条件共72个逻辑产物位置，冷启动同prompt可共享缓存。共同确认12家族×3契约×2次，在No-Skill/Generic/Targeted三条件下共216个评分位置。它们只是预定预算，不是统计充分性保证，也不是当前已完成数量。

目前覆盖同机制与状态条件反转；“不限制输入”不等于真正无关机制任务。尚无完整表面迁移、数学近似条件反转或跨域适配。生成目标超出 DSL 能力时必须报告缺口，不能拿代理任务高分代替目标达成。

### 反馈怎样改变 Skill

新规则必须引用当前开发证据，可新增、删除或条件化已有规则。替换同一规则 ID 时只允许保持或收窄语法 scope；扩大范围是待验证请求，不自动生效。证据引用正确只是来源保证，**不证明模型归纳正确**。

举例（说明机制，不是新增实验结果）：若任务明确要求保留输入，而代码原地排序，反馈应指向实际状态差异；更新可提出“显式要求保留时使用不变换原对象的实现，并检查前后状态”，同时保留“要求原地修改时不适用”的例外。不能从这次失败推出“任何任务都不能修改输入”。

当前课程仅使用注册公开检查，所有候选为 **shadow**：可以研究其原始效果，但未经授权不能宣称可以部署。Research 反馈臂仍为 Pending、未运行。

检查器新增独立状态观察版本：普通异常使返回义务失败，但仍根据调用后的真实输入判断状态义务；不能把“抛异常”自动归因为“修改输入”。MemoryError/TimeoutError等资源异常仍为unknown。5个真实Docker工程控制已通过；冻结历史检查器及原分数不改写。

公开修订适配器另有默认关闭的`allow_clean_timeout_revision=True`：只有来源绑定、隔离条件匹配且清理确认的公开执行超时，才可得到同样一次修订机会。反馈只说明“隔离调用未在预算内完成，语义结果未知”，不把超时判成算法错误，不放行SSH/容器一般故障或资源异常，不补答案、不重抽。真实单案例工程smoke已完成unknown→公开pass，回放不新增调用；它没有更新Skill、执行H或改变既有实验，不能算泛化效果。

另有默认关闭的`public_selection_policy="public_nonregression_v1"`。输入为同一任务初稿/单次修订的公开检查：若初稿pass而修订fail/unknown，则输出`retained`及原稿；完整保留被拒的修订、执行证据和已消费修订机会。没有H参与，不增加请求或检查，不能把公开pass当全面正确。新政策的反馈额外保留attempt代码与attempt transition，避免回退遮蔽错误经验；超时→pass仍为unknown转移而非语义修复。默认历史行为不变；真实C原响应的2次Linux公开重执行已验证保护，0新模型/0H，未改C分数。未来方法对照必须为所有Solver条件统一冻结该政策，不能仅对候选启用。

### 9/27 三项可靠性修复：统一求解配置，不改变评测标准

[solver_profile.py](../skillopt/skill_validation/solver_profile.py)定义显式的`reliable_v1`。输入为预先声明的配置、公开任务及当前规则；[rule_solver.py](../skillopt/skill_validation/rule_solver.py)冻结实际注入文本和配置后，输出初稿、公开执行证据、至多一次修订、选择结果及完整被拒尝试。

| 环节 | 新配置的行为 | 边界 |
| --- | --- | --- |
| 输出预算与交付 | 初稿/修订默认各4096 tokens；`compact_json_v1`提示完整、紧凑、严格JSON | 不抽取半截代码、不放松解析；不因失败自动加预算重抽；其他角色不扩额 |
| 一次公开修订 | 既有公开检查反馈；另允许隔离与清理均已确认的执行超时获得一次机会 | 超时仍为unknown，不放行SSH断连、普通容器故障；不读H |
| 公开回归保护 | 初稿pass、修订fail/unknown时保留初稿，记录`retained` | 完整保留被拒修订、成本和失败证据；公开pass不保证隐藏正确 |

两学习入口`mechanism_study`与`curriculum_study`均支持`--solver-profile reliable_v1`，在开发/确认、No-Skill/Current/各Candidate上统一生效。`--solver-max-tokens`只允许在运行前固定共同上限；Updater仍2048，课程规格生成仍6144。初稿的完整HTTP截断是终态交付unknown，不再被误当整个API服务不可用；真正网络失败仍停下核实。

历史调用默认仍为`legacy`，新行为必须用**新输出目录＋显式配置**，不会默默改变旧实验。协议、规则暴露、初稿及修订回执均绑定预算/格式；调用前检查实际API健康策略与两阶段预算，错配在付费前拒绝。同目录更换配置不能重新采样。下游`public_repair_feedback`按新元数据重建请求并保留attempt，旧F反馈重建仍逐字段一致。

[真实smoke入口](../scripts/smoke_solver_reliability.py)只检查工程链路：一个手工选定DSL家族的保留/原地/无状态约束三变体，各跑三条件，至多18次请求；Current/Candidate故意共用同一手写测试规则，不是学习实验。9/27 Linux Docker运行的9/9位置公开通过，12次唯一模型请求、0交付失败；完整结果与保护分支控制见[验收报告](skill-validation-solver-reliability-20260927.md)。这不证明通过率的统计提升或Skill泛化。

```bash
# 需已有.env及Linux上的源码快照/隔离镜像；不会修改评测集
python -m scripts.smoke_solver_reliability \
  --output outputs/skill_validation/reliability_new_run \
  --remote-repo /absolute/linux/source/snapshot

# 原学习命令在新的输出目录显式追加：
# --solver-profile reliable_v1
```

### 9/25 新对照：先固定课程，再比较如何学习

[mechanism_study.py](../skillopt/skill_validation/mechanism_study.py)是同一主线下的受控入口，不覆盖上述课程实验。输入为固定seed和任务预算；[任务目录](../skillopt/skill_validation/mechanism_tasks.py)编译开发30题、确认78题。相关家族分别8/24个，每个包含保留、原地修改、无状态要求三种契约；另各6个不同算法控制任务，仍全部为Coding。

数据流是：**完整面板冻结→Linux参考/控制资格检查→共同空父开发执行→同一公开反馈包→两种归纳策略各更新一次→全部候选冻结→共同确认→分区域配对统计**。默认3条请求独立历史×2次重复，共享任务面板，不把历史数当新增任务数。

A原始更新器读取的是**最终产物与最终公开检查**；初稿和修订记录虽已保存，该入口没有提供完整修复轨迹。包装检查主要返回布尔值。此限制已在下述F独立提案对照中接通，不能回写成A当时已经使用修复轨迹。

[local与mechanism更新](../skillopt/skill_validation/mechanism_learning.py)共用规则schema、证据、最多两项编辑及预算；仅后者显式要求对比失败、正确替代解、条件反转与保留行为。因此这是归纳策略对照，不是完整SkillOpt基线或规则表示消融。真实API格式smoke发现遗漏嵌套字段后，新共享提示增加完整骨架，不放松解析器或自动补答案。

确认同时保存`raw`强制使用与`conditional`公开义务筛选。前者评价内容，后者本拟评价禁用/覆盖；此次唯一规则的scope覆盖所有任务，两暴露完全相同，因此没有检验出条件控制作用，不能把回退收益写成Skill自身学会泛化。[统计接口](../skillopt/skill_validation/mechanism_metrics.py)保留Base/Current、未知和缺失分母、族聚类区间与成本；非劣诊断不签发授权。A已全部完成，主要差异来自输出截断和一例不终止代码，不是已建立的语义泛化；详见[9/25报告](skill-validation-mechanism-study-20260925.md)。

本轮没有使用Research新增反馈，也不评价历史目标选题；目的是避免再次把课程生成可靠性、学习策略和路由同时改变。

### 9/25 开发诊断后的薄修正（不写回冻结的 A）

- `mechanism_learning` v3将已有证据ID直接放进对应案例，并核对未标注内容的哈希；减少跨列表抄错，但**不认证引用能支持结论**。A中已发生一次语义错引，保留原样。
- `mechanism_tasks` v2按照保留／原地修改／无状态要求各自真正可观察的行为去重。固定有限输入上的469项仍不是语义独立证明；A沿用原747项目录，不中途换题。
- [public_case_feedback.py](../skillopt/skill_validation/public_case_feedback.py)对已注册公开例子逐一执行，输出期望、实际返回、异常和前后输入状态，再回放回执形成模型视图。它没有生成新题或Research信息；明确保持义务才能把状态改变判失败，缺少结构化原地修改后置条件则保留unknown。资源不足与语义错误分开。
- B反馈粒度对照使用同一批最终开发产物和同样的详情选择：原布尔反馈保留，实验臂仅增加绑定同产物的逐例观察；两臂同updater、同内联ID。B仍不包含初稿→修复轨迹。这里只能先检验提案质量，不能靠“更多candidate”证明泛化提高。
- [逐例候选确认入口](../skillopt/skill_validation/mechanism_case_confirmation.py)只回放预登记的第0次提案，全部冻结后对共同78题重新求解；不读取A确认成绩或复用其产物。相同题目仍是共享面板扩展，不是新独立数据；无更新的历史保留父版本，不挑其他重复中更好的候选。首次启动的输出截断被旧健康屏障误判为服务故障，已保留原记录；新v2协议显式区分模型交付失败与API服务故障，完整HTTP响应的截断仍记unknown但不阻断其他任务。C已完成3,744位置及逐回执复核；case_details净增9个通过均涉及交付变化，没有完整H语义胜负，也没有实际条件禁用。

### 9/25 修复轨迹进入更新：独立 F 对照

[public_repair_feedback.py](../skillopt/skill_validation/public_repair_feedback.py)读取A的公开初稿、公开执行回执和实际修订记录，严格回放任务/父版本/产物绑定；不读取H、不重新执行、不检索资料。输入180条独立请求轨迹（360个冷启动条件位置），输出全量公开转移摘要，以及按固定规则选出的最多6对详情；优先展开改坏、修好、未解决和unknown，并为未解决错误保留一个同题成功重复（若存在）。

两臂都看相同转移摘要、最终代码和引用目录；`trajectory`额外获得初稿与修订细节，`summary_only`没有这些细节。随后调用共同mechanism updater，各历史2次提案，预定只使用第0次；重复1只测稳定性。F真实12次提案已完成，2/3主历史的trajectory生成规则、summary为0/3，**这只说明产生了候选，尚不是效果结论**。新增规则证据仍集中于同一道区间边界修复，不能说已有多机制学习。

独立[源码修改难度诊断](../skillopt/skill_validation/patch_diagnostic.py)使用[24个固定任务](../skillopt/skill_validation/patch_tasks.py)：12个同作者小模块，每个有“保留旧默认行为”和“替换旧政策”契约，公开初始代码与4例；12个H案例只由宿主执行。No-Skill每题2次、同样一次公开修订，初稿/最终均48/48通过。该面板缺少正向提升空间，只适合作为目前候选的条件反转/非干扰诊断，不充当泛化成功证据或新独立校准。所有任务、失败和记录保留，不按成绩删题。

[repair_transfer.py](../skillopt/skill_validation/repair_transfer.py)已真实完成F主候选→固定24题→新No-Skill基线与候选求解→初稿/最终H分项。先重放全部12提案回执，仅取预定repeat0，再冻结并完成576位置；无规则的条件保留空父并报告缓存别名。只使用raw，不按宿主Near-Miss标签路由。实际注入规则的96轨迹全部通过，但相对Base的两项改善均为格式差。此次是已消费Coding开发集的探索性干扰诊断，不是已证正迁移、独立确认或获授权部署。

### 输出预算归因：不把交付差异当语义学习

[delivery_budget_diagnostic.py](../skillopt/skill_validation/delivery_budget_diagnostic.py)固定A的h0原始候选与完整78题，交叉No-Skill/候选、2048/4096输出上限，每题2次，共624个预登记新初稿请求。保留原提示词，所有请求先冻结、按固定顺序交错调用，全部初稿完成后才执行H；本诊断不进行公开修订、更新Skill或Research，不针对旧失败请求重抽。

输出分别给交付/解析/执行状态、已知结果下的配对差异、实际token和隔离执行成本。G已完成624次新请求及独立回执复核，显示输出预算确实影响原始分差。原提示词仍提及以后可能修订，而本次刻意只观察初稿，不能称完整Solver协议的复现；候选及面板来自已消费实验，不能称独立效果确认。运行中未按结果加题或改预算。

## 6. 主线 B：Coding Rubric 与 Research 怎样验证、怎样进化

Rubric 不直接给 Skill 文本打分，而是验证 **Skill 引导下的产物是否满足原任务义务**。同一批三条件产物的差异，才用于判断 Skill 的增量作用。

| 步骤 | 输入 | 处理 | 输出 |
| --- | --- | --- | --- |
| B1 找验证缺口 | 当前 Rubric、公开开发产物/执行，或明确标记的开发审计摘要 | 识别未覆盖义务、疑似误拒、证据不足 | 待研究问题；假设与已观察错误分开 |
| B2 提议可复用策略 | 相同开发证据，Research 臂额外允许限定资料 | 定义机制、义务、适用/例外、证据、检查生成和不确定性 | 版本化 Rubric/策略，或 no_update/invalid |
| B3 实例化检查 | 冻结策略、公开任务、匿名配对产物 | 生成该题 probes；同一组适用检查用于全部条件 | 调用、expected/关系、依据，不读取 H 补答案 |
| B4 执行前审阅 | 公开任务、固定 probes | 机械校验，再语义审阅依据、合法输入、预期与关系 | keep / abstain / unknown、原因码；不改 expected |
| B5 按事实缺口研究 | 只有 `missing_external_fact` 的具体检查 | 查限定官方资料、选择片段、再审**原检查** | 有来源的再审结论或保留未知，不自动采纳 |
| B6 隔离执行 | 保留检查、每个绑定产物 | 在安全执行器中实际调用 | 观察结果、状态变化、执行回执；动态 probe 的 match/mismatch/unknown |
| B7 聚合与校准 | 共同任务义务上的报告、宿主独立 H、冻结配置 | 比较检错、误拒、适用性、覆盖率、配对方向与成本 | Verifier Gate 结论和限定权限，不等于 Skill 准入 |

### 当前相关 Research 与策略实例化接口

- [research.py / stage2](../skillopt/skill_validation/research.py)：有界问题规划→最多三页 Python 3.11 官方资料→条件化检查提案，最多两次模型调用。受限检查方式包括公开示例、输入状态、公开不变量。
- [natural_policy.py](../skillopt/skill_validation/natural_policy.py)：可复用七字段策略→任务级 probes；目前每题最多两个，支持单调用 expected、双调用输出相等。后者不能表达所有复合/幂等关系，更不是通用可执行 Rubric 语言。
- [probe_fact_research.py](../skillopt/skill_validation/probe_fact_research.py)：执行前审阅发现具体外部事实缺口才调用，最多两个官方 URL、两次模型调用。模型选择片段 ID，宿主恢复原文；查询、来源、片段、缓存均绑定当前问题与检查。

Research 允许没有新增信息、检索失败或 no_update；不能检索当前任务答案、修复 PR 或隐藏测试。资料必须支持已有任务义务，不能把一般建议提升为新要求。引用可核对只证明出处，不证明推理成立。

审阅器不直接看实现、执行结果、Skill 条件或 H；但 proposal 的 rationale 可能带入产物感知生成器的观察，不能声称完全信息独立。算术错误、格式问题或题面歧义也不都需要外部 Research。

近期真实模型为 **BigModel `glm-5.3`**，审阅实验为 low reasoning；历史 PJLAB 运行单独记录。模块通过 transport 注入模型，并没有默认使用更强的独立评审模型。最新任务教师也使用 GLM-5.3，已暴露推理 token 耗尽而没有正文的问题。

### 执行检查与独立校准，分别在评什么

**执行检查**问：“这一产物在这条有依据的检查上观察到了什么？”主线结果为 `pass / fail / unknown / not_applicable`。通过只覆盖该项证据；API/解析/环境失败不是已确认语义错误；probe mismatch 也必须先有合法检查依据，不能自动宣判答案错。

**独立校准**问：“这套完整验证流程，相对 H 是否减少漏检且不过度误拒？”校准对象绑定可复用策略、检查生成、执行、适用性、聚合与源码版本；不能每题改标准却沿用旧授权。新版本须重新冻结与校准。[calibration.py](../skillopt/skill_validation/calibration.py)

风险约束、覆盖率要求与最低样本在运行前冻结；unknown 和成本独立报告，各版本使用共同义务分母。新增 [verifier_readiness.py](../skillopt/skill_validation/verifier_readiness.py)已统计独立错误/漏检任务族，但它只做充分性诊断；通用校准的 `min_natural_errors` 仍按产物/义务位置计数，**尚未全面替换成任务族级准入规则**。

自然运行另有 `natural_metrics.calibrate_policy`，只授权对应 Coding 开发反馈；它不等于 `admission.py` 的 Skill Gate。已消费面板回放与新审阅实验均不签发新授权。

## 7. 两道门与协同闭环如何连接

完整设计顺序为：

> 开发配对暴露问题 → Research/Rubric 候选 → 冻结并独立校准验证器 → 获准后重新生成开发执行反馈 → 更新 Skill → 冻结 Candidate/范围 → 独立三条件确认 → Skill Gate → 冻结后 final。

| 门 | 输入 | 决定什么 | 不能代替什么 |
| --- | --- | --- | --- |
| Verifier Gate | 冻结验证管线、独立校准 V/H、覆盖/风险配置 | accepted / rejected / pending；在哪些义务和条件下可提供反馈 | 不批准某个 Skill，更不证明跨域安全 |
| Skill Gate | 获授权验证器、No-Skill/Current/Candidate 配对、冻结范围 | 当前实现 Local Commit / Restrict / Reject / Pending | 不因某答案得分高就批准整个 Skill |

[admission.py](../skillopt/skill_validation/admission.py)区分目标收益区、原能力保持区、不适用区。范围只读执行前公开义务，不读隐藏机制标签、答案或执行后成败。新 Skill 不能继承旧版本授权；当前没有获准 Current 的继承部署路径，未获准/不适用时使用干净 No-Skill，而不是污染环境之后再“回退”。当前注册入口明确不支持跨域区域授权。

[closed_loop.py](../skillopt/skill_validation/closed_loop.py)已顺序连接两道门：验证器不足则不调用 updater；通过后生成真实执行反馈；候选冻结后才确认；final 只评价固定决策。**公开 CLI 使用 scripted Research/updater/Solver 和工程审计标签**，配合真实 Docker 执行；预注册 `reverse_list` 检查配方不是 Research 发明的算法。

历史 V16 则是真实多轮 Skill 与验证策略更新，但没有新主线的 Skill 准入/跨域部署链，且自然新增检错为 0。不能用 V16 的真实更新与新 CLI 的 fixture 准入拼出不存在的完整效果实验。

## 8. 各入口的实际状态与执行环境

| 入口 | 当前实际用途 | 最近状态 |
| --- | --- | --- |
| [natural_study](../skillopt/skill_validation/natural_study.py) | HumanEval+ 自定义自然面板、文本候选、策略校准 | 9/22 已完成；自适应分支未授权，共享固定反馈候选 |
| [natural_verifier_replay](../skillopt/skill_validation/natural_verifier_replay.py) / [probe_review](../skillopt/skill_validation/probe_review.py) | 同一批冻结产物比较验证器和事后盲审 | 真实旧数据诊断，不更新 Skill / 不读 final / 不部署 |
| [admissibility_study](../skillopt/skill_validation/admissibility_study.py) | 先审检查、再隔离执行 | 9/23 完成；`gap_research=false`，不是逐检查 Research 增益实验 |
| [development_repair_study](../skillopt/skill_validation/development_repair_study.py) | 同父分叉、全量反馈、一次公开修订 | 9/23 完成；已消费的 7 道回归诊断题，不是独立泛化 |
| [rule_learning_smoke](../skillopt/skill_validation/rule_learning_smoke.py) | 空规则包→反馈→规则修改/条件渲染 | 全部 scripted fixture，0 API、0 真实执行 |
| [curriculum_study](../skillopt/skill_validation/curriculum_study.py) | 历史目标→新任务家族→规则学习→共同确认 | A–D 共14次模型调用均 Pending；0真实 Skill 更新、无确认成绩 |
| [mechanism_study](../skillopt/skill_validation/mechanism_study.py) | 固定课程→同父同反馈更新→raw/conditional完整确认 | 44/44族资格、3,744评分位置完成；没有机制策略优势或有效条件禁用 |
| [public_repair_feedback](../skillopt/skill_validation/public_repair_feedback.py) | 绑定公开初稿与修订→摘要/轨迹对照→规则提案 | F共12次真实提案已完成；只证明轨迹进入更新，未证明迁移收益 |
| [solver_profile](../skillopt/skill_validation/solver_profile.py) | 共同预算/格式→单次公开修订→非回归选择 | 9/27显式接入两学习入口；真实工程smoke已完成，不是方法效果 |
| [patch_diagnostic](../skillopt/skill_validation/patch_diagnostic.py) | 固定初始源码与保留/替换契约→No-Skill难度诊断 | 24题×2次初稿/最终均48/48；明显天花板，不是学习收益 |
| [repair_transfer](../skillopt/skill_validation/repair_transfer.py) | F主候选冻结→原24题新基线/候选→初稿和最终分项审计 | 576个raw位置完成，实际注入96轨迹未观测干扰；+2通过来自格式差，非语义正迁移 |
| [closed_loop](../skillopt/skill_validation/closed_loop.py) | 校准→授权反馈→更新→准入→final | 工程控制路径已通过，未证明自然端到端效果 |

近期实验由本机 Python 调度、经 SSH 在 Linux Docker 执行代码。Docker 用于执行 Solver 产物、公开检查、参考/控制资格检查及宿主审计；不是调用 LLM 的替代品。镜像/调用/源码/回执有绑定，执行后需确认清理；隔离环境不可用时返回 unsupported/unknown，不裸跑候选代码。

相同请求可从完整终态回执回放；只有 intent 而没有终态时暂停核实，不自动重抽以改善成绩。源码或协议改变使用新输出目录；本机调度仍会受休眠/SSH 影响，不能视为已经部署到不间断远端调度。

9/25增加[专用SSH配置适配](../skillopt/skill_validation/mechanism_transport.py)：可连接本地Linux VM或其他明确指定的Linux执行器，仍复用原Docker策略、主机密钥检查及回执协议。没有macOS裸执行回退路径。当时PJLAB握手失败，9/25实验改用不挂载macOS主目录的专用Linux VM；当次未改变Clash路由或全局SSH配置。Docker29兼容修复生成执行器v2，旧快照和失败不改写。9/27可靠性验收已使用恢复连接的PJLAB Linux Docker，仍由本机调度；不同执行镜像与源码身份分别绑定各自协议。

可离线查看的入口（仓库根目录、激活 `skill` 环境后）：

```bash
# 已公开的真实记录摘录，零 API、不执行候选代码
python scripts/replay_research_demo.py

# 新规则更新的工程链路；全部 fixture，不是方法效果
python -m skillopt.skill_validation.rule_learning_smoke \
  --output outputs/skill_validation/rule_learning_doc_smoke

# 主线离线回归；此命令不是付费自然实验
python -m pytest -q tests/test_skill_validation_*.py
```

真实课程启动参数见[9/24 课程报告](skill-validation-capability-curriculum-20260924.md)；不要用新的源码直接续写旧目录。原始 `outputs/` 与 API 缓存不公开，公开 demo 只是精选材料。

## 9. 下一步与维护约定

逐例候选确认和预算归因已完成，主要分差仍与交付有关；9/27已将共同预算、一次修订和公开回归保护接成新配置。9/27这一轮完成的是可靠性修复与工程验收，评测体系调整等待进一步确定。下一项方法比较应保留修复轨迹学习，先确认新任务具有目标机制错误空间，再同父、同任务、同updater分叉反馈，在未消费任务上分别评价相关收益、条件反转和无关任务损害；不再重复接近满分的小题，也不把回退率当学习效果。任务来源、公开契约、原生评分与隔离兼容性需先核实，确认数据及可接受退化界需另行冻结。教师课程生成与Research增量仍是独立问题，未经独立校准的Research不能伪装成获授权反馈。新配置不自动赋予Skill或验证器任何准入权限。

每次修改初始化、反馈、任务生成、Rubric/Research、判分、门控或运行入口时：更新本文对应输入/输出、实际连接方式、状态与限制；不要只改日期。新重要结果写入[账本](results-and-lessons.md)，保留分母、对照、成本、证据等级与存档链接。历史协议/结果不回写，新版本不继承旧授权。
