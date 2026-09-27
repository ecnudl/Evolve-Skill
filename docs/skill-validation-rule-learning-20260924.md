# Skill 初始化与条件化局部进化：实现与工程验证

日期：2026-09-24。性质：代码实现、代码审查、离线工程验证；**不是新一轮模型效果实验**。

## 这轮解决什么

根据此前父 Skill 来源偏窄、Current 可能负迁移，以及错误反馈可能被总结为全局规则的诊断，新增一条小入口：明确父 Skill 的来源，把优化对象从整段全局文本细化为带前提与例外的行为规则，并保留同反馈的全文更新对照。

没有修改历史实验协议、结果、验证器标准或原有求解器。既有 Rubric、公开证据投影、回执重放与准入接口继续复用；没有为规则库另造一套 Research 或审计平台。

## 已实现

| 文件（均在 `skillopt/skill_validation/`） | 作用 |
| --- | --- |
| `skill_seed.py` | 三类初始化：真正空白的 `cold`；有来源文件与宿主选择声明的 `source_trained`；只作诊断的 `legacy_diagnostic`。 |
| `rule_skill.py` | 条件化规则与版本；每条含机制、操作步骤、前提、例外、公开义务条件和证据引用。最多 8 条规则、每次最多 2 项编辑、渲染不超过 6,000 UTF-8 字节。 |
| `rule_learning.py` | 重放既有公开开发反馈，生成局部编辑或全文改写请求；校验父版本、编辑预算、当前证据引用；区分无更新、无效输出、API 失败、仅元数据更新与新候选。 |
| `rule_solver.py` | 将结构化版本映射到实际注入文本，复用 `public_revision` 的生成、公开执行检查及最多一次修订；保留全量注入与条件化注入两种诊断模式。 |
| `rule_learning_smoke.py` | 无 API、无真实代码执行的可重放工程样例。 |

每条学习历史仍是一个小 Skill 规则包，**不是同时部署 8 个已学会的 Skill**。容量上限不是初始化数量，也不是自动检索库；空白初始化从 0 条规则开始。

### 1. 不再把任意父文本当作成熟经验

- `cold_seed(history_id)` 的文本严格为空。
- `import_source_seed(...)` 只读导入上游 SkillOpt 的 `best_skill.md`、训练 checkpoint、summary、history、来源验证结果，并要求精确哈希及宿主审阅声明。
- 选择依据只能是来源开发验证 `valid_seen`，不能用 test/final 选父。上游名为 `final_selection_eval` 的步骤实际使用 `valid_seen`，不能仅因文件名含 final 就误判为测试泄漏。
- 上游文件可被原位更新，因此本接口诚实标注“宿主审阅声明”，**不能自动认证完整训练血缘或训练质量**。
- 导入的长文本不自动变成结构化规则、不自动获得部署权限。超过长度上限时拒绝，不静默截断。warm/legacy 的规则化仍需独立提案与确认，不能冒充已经完成的冷启动闭环。

### 2. 反馈直接作用于局部规则

规则允许 `add / replace / remove / no_update`。候选需引用本次公开反馈目录中的实际条目；旧宿主引用不投影给模型。固定 JSON 交付格式与工具限制属于公共求解协议，不作为新增规则字段。

替换同 ID 规则时，形式化条件只能不变或收窄；`scope_expansion_request` 只保存待验证假设，不改变当前文本。新增规则或删除后新增另一个 ID 仍是**全新未确认候选**，不能继承旧授权。这只是编辑约束，不等价于 Skill Gate 的安全保证。

仅更新证据引用、但模型实际看到的文本不变，标记为 `metadata_only`，不计作新的行为候选。删除全部规则明确记录零学习内容，不把回到 Base 写成学习成功。

### 3. 对照与执行机会保持可比

局部规则更新和全文更新收到**逐字相同的用户侧公开反馈**，仅系统提示的输出表示要求不同。这不意味着 token 成本已经相等，真实实验仍需报告消耗。

No-Skill、Current、Candidate 共用原求解器的固定系统协议，并有同样的公开检查修订机会。No-Skill 在初稿和修订两阶段都为空；非空规则被条件过滤成空，也不能冒充 No-Skill 身份。修订后变差不会被事后择优隐藏。

## 实际数据流与边界

空种子 → No-Skill/Current 开发产物及公开执行回执 → 既有反馈重放与白名单投影 → 带证据引用的局部编辑 → 未确认 Candidate → 相同求解协议的独立评测。

已有校准授权可传给更新入口，并核对验证流水线哈希；无授权时只能形成 `shadow_diagnostic_only` 提案。工程授权另标 `engineering_authorized_diagnostic`。**解析成功不等于规则成立，也不等于 Skill 已接受或 scope 已扩大。**

本次接线刻意保留两项限制：

1. 现有开发反馈绑定完整父文本的哈希，因此用于更新的 Current 开发采集应使用 `exposure="raw"`。条件化注入用于单独诊断，不能修改回执哈希，把不同有效文本混成同一个父 Skill 的开发记录。尚未实现条件化多文本反馈聚合。
2. 条件筛选只使用执行前公开义务类型，不读取隐藏机制标签或审计结果。但它不理解任意自然语言前提和例外，不能宣称已经学会语义路由。真实授权还要经过独立校准及确认。

相同提示、repeat 和协议会由已有 `BoundedCalls` 复用响应；不同 history ID 不自动创造独立模型调用。特别是冷启动 Current 与 No-Skill 文本完全相同，不应把缓存副本当作独立样本或技能因果差异。

## Review 与测试

独立代码审查加主代理复核，修正了：

- 提示允许 3–8 次编辑、底层却最多 2 次的契约冲突；现在统一为 1–2。
- 模拟授权与真实开发授权标记混淆。
- 旧规则宿主证据引用进入 updater 上下文的风险。
- 仅改变证据元数据被误记为新行为候选的问题。

新增五组测试覆盖初始化来源、字段隔离、编辑/范围约束、同反馈对照、三条件同协议、回放、unknown、No-Skill、目录误复用等。

| 检查 | 最终结果 |
| --- | --- |
| 本地 `tests/test_skill_validation_*.py` 全部相关回归 | 1,279 passed，包含本轮新增测试 |
| 本轮五组新增测试，Linux Python 3.11 | 137 passed |
| 本机与 Linux 离线 smoke / 重放 | 均完成，摘要哈希一致 |
| `git diff --check` | 通过 |

初次广泛回归出现 12 项旧 `validator_pilot_tasks` 隔离执行失败，原因是外层沙箱阻止 macOS `sandbox-exec`。获得批准后，在外层沙箱之外重跑该文件，项目自身隔离执行器仍保留，**60 项通过**；没有将首次失败记为通过或绕过项目隔离运行产物。

## 可回放 smoke

```bash
python -m pytest -q \
  tests/test_skill_validation_rule_skill.py \
  tests/test_skill_validation_skill_seed.py \
  tests/test_skill_validation_rule_learning.py \
  tests/test_skill_validation_rule_solver.py \
  tests/test_skill_validation_rule_learning_smoke.py

python -m skillopt.skill_validation.rule_learning_smoke \
  --output outputs/skill_validation/rule_learning_smoke_20260924_reviewed
```

本地输出：`outputs/skill_validation/rule_learning_smoke_20260924_reviewed/`。重复执行校验旧文件一致性，不覆盖冲突内容。保存 seed、反馈、模型视图、提案、候选、适用条件匹配与摘要共 10 个 JSON。

| 工程检查 | 结果 |
| --- | --- |
| 空 Skill → 脚本化候选 | 0 条 → 1 条条件规则 |
| 规则更新与全文更新的公开反馈 | 相同 |
| 明确要求原地修改的 Near-Miss | preservation 规则未注入 |
| 缺失产物 | 保留 unknown，不当作语义错误 |
| NO_UPDATE / 删除到空 | 正常记录，不产生授权 |
| 模型 / Research / 真实执行 / H 读取 | 均为 0 |

**这两个手写 fixture 只验证接线，不能估计准确率、负迁移率或泛化性能。** 两个冷条件本来没有 Skill 差异，脚本化产物差异也不能被解释为 Skill 效应。

摘要哈希（本机及 Linux 一致）：

```text
6a6adc7a02098a14fcfd5746f504c71b13947d591787e9e5919dc244a1527d31
```

已成功 SSH 到 PJLAB Linux 开发机，使用已有 Python 3.11 环境，在独立临时目录验证（公开说明省略机器别名及临时目录名）。只传输源码与测试，未复制 `.env`、未覆盖服务器原实验仓库；该目录是临时验证副本，不是正式实验部署。SSH 可用不等于模型 API 可用，本轮没有进行 API 可用性或吞吐测试。

## 下一步真实实验

优先在 Linux 上冻结同一开发证据、共同父版本、updater、Solver 与预算，对比“全文改写”和“条件化局部规则编辑”；分别报告 raw 强制注入与条件化注入的结果。先做一轮，暂不增加自动路由、多轮 autoresearch 或 Skill 数量。

warm source-trained 初始化作为独立学习历史，与冷启动及旧弱种子诊断分开；来源需要匹配任务，不能因为 SearchQA 中训练过就默认适合 Coding。先完成明确的规则化提案及一致性确认。

真实方法效果仍需未消费的确认任务与最终冻结评测，报告独立任务/任务族、重复测量、收益/回归、覆盖率、回退、unknown 及实际成本。Research 是否有效与这次表示改动是否有效要分开归因。本轮未启动新正式模型实验、没有产生新的 benchmark 分数，也没有给任何新 Skill 部署授权。
