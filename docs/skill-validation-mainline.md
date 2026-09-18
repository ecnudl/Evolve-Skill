# Research-driven Skill Validation：新主线

目标仍是 **通过 Coding Rubric 与 Research 改进 Skill 的验证、进化与适用范围判断**，降低跨域负迁移。阶段一的固定产物回放与证据隔离保持不变；阶段二已增加有界 Research 提案、公开契约检查、Linux 隔离执行、独立校准和审计的工程入口。**尚未证明 Research 的真实增量效果，尚未接入新主线的 Skill Gate／Skill 更新。**

下面先保留阶段一接口说明；阶段二入口、局限与后续边界见文末。历史 VXX 源码和冻结实验不修改。

## 本阶段的数据流

固定公开任务契约＋实际产物＋绑定的公开执行回执 → 固定 Rubric 实例化 → 逐义务检查 → 可回放报告。

独立审计 H 保存在另一份宿主文件中，不是上述验证器的输入。历史私有分数不进入公开验证视图。

新入口为 `python -m skillopt.skill_validation`，代码位于 `skillopt/skill_validation/`。历史 `coevolution_vXX`、协议和结果原样保留，不复制一套新的 VXX 实验。

| 文件 | 职责 |
| --- | --- |
| `models.py` | 严格、可序列化的任务、产物、证据、Rubric、单题检查实例、结果、报告结构 |
| `views.py` | 验证器可见视图、显式开发缺口摘要、Skill 反馈预览；宿主身份绑定 |
| `partitions.py` | 数据用途、原任务／近重复任务族隔离与来源资格 |
| `legacy.py`、`importers.py` | 对已闭合 V15/V16 Coding development 记录进行薄适配 |
| `engine.py` | 固定公开证据回放、条件适用判断、按任务义务聚合 |
| `replay.py`、`__main__.py` | JSON 导入、不可覆盖输出、CLI |
| `fixtures.py` | 明确标记的工程假数据，不是模型运行记录 |

复用早期 Rubric 的义务／证据／四状态语义，复用 `validator_pilot.api` 的规范哈希与不可变 JSON 写入，复用 V5 的 `seal/verify`，由 V15 `project_development_feedback` 核对历史依赖。没有直接复用旧的模型提示词序列化或旧 Coding 执行器：前者只做顶层白名单，后者可能读取参考实现。

## 1. Rubric 与单题检查分开

- `RubricVersion` 是可复用的检查策略，绑定生成、执行、适用性判断、聚合策略及相关实现源码指纹。
- `CheckInstance` 是该策略在某个任务／产物上的实例，绑定原始 Rubric、任务、产物和证据。
- 未来校准授权必须绑定整个可复用管线，不能把单题测试清单当作可迁移 Rubric，也不能每题改写标准却沿用原授权。
- `GateDecision` 本阶段只能返回 `pending`，不能批准任何 Rubric 或 Skill。
- 字段和哈希用于一致性核对，不证明引用蕴含、观察真实、源码未受训练污染或任务契约完整。任务义务由可信导入端给定；引用在原文中出现只是最低限度的来源检查。

当前固定检查仅做三件事：回放已有公开测试通过／失败记录，比较已有公开输入前后指纹，比较明确要求字节不变的公开文件。**不搜索新测试、不执行产物、不调用隐藏 oracle 补答案。** 缺少相应回执就是 unknown。

## 2. 四种信息视图

| 使用者 | 可以读取 | 不可以读取 |
| --- | --- | --- |
| 盲评验证器 V | 公开契约、实际代码、选定公开执行观察 | H、参考实现、私有测试、条件标签、Skill 哈希、任务族及机制标签 |
| Research 开发接口 | V＋单独标记的 development 漏检／误拒／不确定摘要 | 隐藏测试正文、参考答案、校准／审计／最终集诊断 |
| Skill 更新器 | 本阶段仅提供 V 的反馈预览；后续须由获授权验证器提供 | 额外直接投喂 H 答案或私有测试明细 |
| 宿主 | 条件映射、完整来源、H 与所有结果 | 不得把整份宿主 dict 序列化成模型输入 |

模型视图逐层显式重建，嵌套字典不能冒充文本或源文件。真实任务语义和代码仍会保留，不能声称消除了代码注释等带来的全部语义身份线索。模型视图不是防止恶意模型访问宿主文件的运行时沙箱。

每条公开观察必须绑定任务、实际产物字节、**确切产物运行记录**、repeat 与来源种类。两个条件即使生成完全相同代码，也不能默默互换回执。未来若要共享实际执行，必须显式记录受核对的别名。

信息来源分别标记为 `public_contract`、`submitted_artifact`、`recorded_public_execution`、`development_audit_summary`。H 已提供的诊断不是 Research 独立发现。

## 3. 五类用途与来源

| 分区 | 用途 |
| --- | --- |
| `development` | 提出检查、诊断、未来的 Skill 更新 |
| `verifier_calibration` | 候选验证器准入选择 |
| `verifier_audit` | 冻结后独立评价验证器效果，不能兼作选拔集 |
| `skill_confirmation` | 冻结候选及适用条件后的 Skill 准入 |
| `final` | 冻结后独立最终评价 |

同一个原任务、近重复任务族不能跨用途。同项目是否整体隔离由协议明确指定，不能把普通任务隔离宣传为未见项目泛化。识别近重复任务仍依赖正确的来源清单，本模块不是语义去重模型。

来源区分 `model`、`fixture`、`mutant`。完整来源记录是宿主核验结果，不是认证签名。旧记录即使闭合也已被开发过程使用，只能作 development 兼容性诊断；缺少源码／协议清单会明确标记 `provenance_complete=false`，不能成为正式验收数据；缺少实际运行回执则拒绝导入，不能补造。

## 4. 结果语义与统计口径

- `pass`：仅在相应证据覆盖范围内通过，不等于证明整个产物正确。
- `fail`：绑定证据确认义务违反。
- `unknown`：缺少证据、API 失败、解析失败或执行不可用；这些原因保留，不伪装成语义错误。
- `not_applicable`：任务没有对应义务，例如明确原地修改的任务没有“不修改输入”的要求。不能以此掩盖任务本来存在但没有检查的义务。

聚合分母来自同一份 `TaskContract.obligations`，不随某验证器增加多少检查而变化。缺少检查的关键义务仍是 unknown。误拒与条件误用是未来风险约束；**unknown 不采用“只能减少”规则**，覆盖率、unknown 与成本分别报告，并在研究协议中提前冻结最低覆盖要求。

报告反序列化仅检查结构与绑定，不构成准入证明。未来门控消费报告时必须从原始记录重新执行回放并核对，不能相信任意传入的总体分数。

## 可运行命令

使用已有 `skill` 环境；不需要 `.env`、API Key、网络或沙箱。

```bash
python -m pytest -q tests/test_skill_validation_*.py
python -m skillopt.skill_validation smoke --output outputs/skill_validation/stage1_smoke
python -m skillopt.skill_validation replay \
  --input outputs/skill_validation/stage1_smoke/preserved/case.json \
  --output outputs/skill_validation/stage1_smoke/preserved
```

真实历史记录示例（原始缓存没有公开发布，缺少时不能伪造）：

```bash
python -m skillopt.skill_validation import-v15 \
  --run-root outputs/coevolution_v16/pilot_20260915_a_clean_resume_20260916 \
  --solve-id 11abc4a5491a01588134af3faa138f9c0d0a3d9ecdc3f86002f423cef9ba33aa \
  --source-kind model \
  --output outputs/skill_validation/stage1_legacy
```

每个案例输出 `case.json`、`rubric.json`、`verifier_view.json`、`report.json`、`summary.json`；历史导入另存 `host_only/audit.json`。重复回放必须内容一致，不能覆盖不同的结果。源码改变导致管线指纹改变时，使用新输出目录。

阶段一入口不执行代码。阶段二仅在满足约束的 Linux Docker 中执行；无沙箱不能转为宿主直接执行。`unsupported` 回执保留为 unknown。运行产物放 `outputs/`，不提交密钥、历史调用缓存或私有审计数据。临时路径若包含系统符号链接，应先使用真实路径；导入导出拒绝符号链接证据路径。

## 阶段二：工程链路与适用边界

新增入口为 `python -m skillopt.skill_validation.stage2`，不复制历史 VXX。数据流为：

1. 宿主冻结同一组三条件产物、共同任务义务、完整分区清单；H 另存 `host_only/audit.json`。
2. 固定检查在 development 上执行；两个自适应对照获得**相同的匿名化公开证据及显式 H 缺口摘要**。
3. `research.py` 做问题规划、按问题选择限定的 Python 3.11 官方资料、综合条件化检查提案；允许无更新、检索失败、非法提案。
4. `checks.py` 把可复用检查配方实例化为宿主已登记的公开调用／关系；`sandbox.py` 在固定镜像、无网络、非 root、只读文件系统中执行。
5. 提案、完整执行管线、预算与阈值冻结后，`calibration.py` 在 verifier_calibration 比较检出、误拒、覆盖率、Near-Miss 与配对方向；再在 verifier_audit 独立报告。

`accepted` 只代表一次有限数据下的验证器校准检查点，**不授予部署、跨领域使用或 Skill 准入权限**。fixture／mutant／历史不完整记录不计入自然效果验收，证据不足为 Pending。

| 新文件 | 职责 |
| --- | --- |
| `research.py` | 两个自适应对照的共同提案接口、文档白名单、隔离缓存、引用来源与成本记录 |
| `checks.py` | 公开例子的精确 JSON 比较、整个调用参数的状态保持、显式重复一致性关系；回执绑定与持久缓存 |
| `sandbox.py`、`sandbox_worker.py` | Linux Docker 限制资源执行；不可用时保留 unsupported，绝不在宿主退化执行 |
| `calibration.py` | 按共同义务比较、自然／工程数据分开、配对诊断、冻结与一次性校准 |
| `stage2.py`、`stage2_fixtures.py` | 固定产物导入导出、三组比较与可回放 smoke；合成数据明确标记 |
| `stage2_transport.py` | 可选 PJLAB／glm-5.3 提案接口验收；固定四次逻辑调用上限，分开记录 HTTP 重试和 token 用量 |

运行无 API 的集成 smoke：

```bash
python -m skillopt.skill_validation.stage2 --output outputs/skill_validation/stage2_local
```

macOS 或没有固定镜像时，执行记录为 unsupported／检查为 unknown，这是失败关闭路径，不是代码执行成功。在已配置的 Linux 上使用：

```bash
python -m skillopt.skill_validation.stage2 \
  --image sha256:b8fe4ce3655e95f7f22c2a87d8e03a2f1f0cedc488a8e9adf18cc5a18cfdf401 \
  --output outputs/skill_validation/stage2_docker
```

再次执行同一命令复用原有提案与执行回执。未闭合 intent 不自动重试；改源码／预算／数据不能覆盖原输出。`--common-evidence` 使用新的独立输出目录，仅共享原始公开调用，新增重复探针没有证据时仍为 unknown。`--pool DIR` 导入 `export_pool()` 冻结的数据，宿主负责核验真实来源，哈希不能认证自然运行。

输出包括 `protocol.json`、分开的冻结产物／H、`development_views.json`、提案与 trace、逐产物执行回执、比较、校准决策和 `summary.json`。结果记录全流程唯一执行成本；脚本回调与真实模型／网络调用不能混算。部署细节见 [Linux 运行环境](skill-validation-linux-runtime-20260918.md)。

需要显式验证真实 API 接口时，可运行下面的**付费、联网**小测试；读取本地 `.env` 中专用 PJLAB 配置，不执行产物、不校准或更新 Skill：

```bash
python -m skillopt.skill_validation.stage2_transport \
  --repo /absolute/path/to/SkillOpt \
  --output /absolute/path/to/SkillOpt/outputs/skill_validation/stage2_live_proposal
```

每次最多四次逻辑调用、单 worker、每次输出上限 2,048 tokens；现有客户端每次允许最多三次 HTTP attempts，分别计数。重复调用只读终态缓存；多次重试前序的 token 用量未知时，不能把终态用量当作全部成本。模型提案被拒绝属于正常结果，不为获得合法／正向输出自动重试。

### 尚未完成的研究能力

- 当前 Research 在三种预注册检查配方中提出组合／修订，不生成任意新检查器，也没有新的任务级模型探针生成器。不能把它称为完整自主 DeepResearch。
- 资料按问题选择，但仍限定于少量官方文档；引用核验只证明来源，未建立自动逻辑蕴含证明。
- `CallableTask` 是 Python／JSON 函数，不是仓库修复、真实工作簿或多工具 Agent。公开期望采用精确 JSON 比较；非空对象级保持 target 暂不支持。
- 输入保持检查覆盖调用前后的 JSON 可见状态，不证明对象身份、执行中间状态或不可见外部副作用保持。
- 原地修改的强制义务没有相应检查时保留 unknown；Near-Miss 不误用主要由公开契约适用性规则约束，不证明学会了泛化路由。
- 容器保护宿主，但产物与观察器在同一 Python 进程，不能保证恶意产物无法伪造测量。正式恶意代码场景需更强执行服务。
- 工程 smoke 只检验链路；需要独立采集并冻结真实 No-Skill／Current／Candidate 产物，才能评价 Research 的检错和决策增益。

## 后续实验与阶段三边界

第二阶段保持 Skill 与真实三条件产物冻结，只比较 fixed、adaptive_no_research、adaptive_research。候选与自然产物的采集规则先冻结，不允许被比较的验证器挑选有利样本。新增配对诊断：Skill 相关回归、Skill 修复、共同错误和不确定情况；单次随机胜败不解释为确定因果。

Research 的隔离必须覆盖查询、搜索摘要、网页、版本与缓存，排除当前任务答案补丁、修复 PR、隐藏测试等答案材料。两个自适应对照共用基础项目上下文和开发诊断；研究来源与 H 诊断、实际执行分别归因。允许 no_update、检索失败与正常拒绝。

三组比较先用共同证据评价适用性与判断，再分别允许生成自己的检查，度量检错增量与实际 token／检索／执行成本。不能仅用相同调用次数宣称等计算量。24／24／48 与三条学习历史仅是先导预算，不是统计充分性保证。

第三阶段仍按 3A 冻结候选准入回放 → 3B 共同父 Skill、不同验证反馈的真实单轮更新。未经相应范围校准的验证器不能批准 Skill。Restrict 只选择预先冻结的子范围，新条件需要新的确认数据。不会把全部回退当作学习收益。

**当前阶段二完成的是工程链路，真实方法效果实验及阶段三尚未完成。** fixture、历史兼容性回放与真实方法效果必须分别报告。下一步先用冻结自然产物验证 Research 是否提供普通自适应对照没有的有效证据；之后才进入 3A 冻结候选决策回放、3B 单轮反馈驱动更新，不自动开启大规模协同进化。
