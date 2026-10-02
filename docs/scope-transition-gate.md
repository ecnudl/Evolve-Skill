# Transition-aware Scope Gate（独立离线原型）

[scope_gate.py](../skillopt/scope_evolution_v2/scope_gate.py) 区分“更新 Skill 内容”和“内容不变、扩大适用范围”。它不执行模型、不读写证据、不修改路由，也没有接入本轮已冻结的 A/C/D 实验。

## 为什么新增而不修改 v1

v1 `decide_scope` 要求来源 local 单元同时对 Base、Current 有正收益；`local_already_committed` 只在没有 local 行时才豁免。因此，已提交 Skill 保持来源执行不变、Candidate＝Current，却再次提交来源观测时，会因为不可能产生第二次 Current 正增益而 pending。

新模块保留 v1 作为冻结比较对象，复用其逐单元统计与检查结果，仅为明确的 scope_expansion 调整来源增益要求。这是工程语义修复，不是放宽当前实验门槛后重新宣布成功。

| 变更类型 | 来源对 Base | 来源对 Current | 跨域 positive | 保护单元 |
|---|---|---|---|---|
| `content_update` | 正收益及安全 | 正收益及安全 | 双参考正收益及安全 | 双参考安全、缺失检查 |
| `scope_expansion` | 每个 local 单元仍须新的正收益及安全证据 | 非劣与条件退化检查；有可信执行 identity 时可按结构同一处理 | 仍须双参考正收益及安全 | 仍须双参考安全、缺失检查 |

每个已提交来源域都必须有新的 local 行。首版不支持仅凭旧证书省掉来源行为验证；两个类型都禁止裸 `local_already_committed=True` 绕过检查。

## 最小 API 与可信边界

入口为：

```python
decide_transition(
    rows,
    transition="scope_expansion",  # 或 content_update
    current_content=current_skill_text,
    candidate_content=proposed_skill_text,
    current_version=committed_content_version,
    committed_source=trusted_contract,
    config=gate_config,
)
```

rows 沿用 v1 的 `id/domain/mechanism/group/baseline/current/candidate`；三个分数必须是有限二元观测，重复 ID 会被拒绝。config 沿用 v1 设置；scope_expansion 未显式指定 source_domains 时，从可信 contract 取得，显式提供时必须匹配。

scope_expansion 的两份真实内容文本必须非空且 UTF-8 SHA256 完全一致。`committed_source` 要求：

| 字段 | 含义 |
|---|---|
| `status` | 必须为 `committed` |
| `version` | 必须等于 `current_version` |
| `content_sha256` | 必须等于对实际内容计算的 SHA256 |
| `source_domains` | 已提交来源域，非空、无重复 |
| `source_policy_sha256` | 已提交来源范围内的执行/路由策略指纹 |
| `evidence_sha256` | 可信证据层中已提交证据的引用指纹 |

这个 contract 必须由可信执行、版本与证据管理层提供，**不是让 LLM 给自己签字**。本函数仅检查字段、内容和版本一致性；`evidence_sha256` 只是引用，不表示函数已加载、验证或认证其证据内容。外层仍须核验该引用真实存在、对应已提交版本及范围。content_update 不接受用 committed_source 覆盖来源更新检查。

## 对 Current 的结构 identity 不能从同分推断

同内容不自动代表来源路由未改变，同分也不代表同一策略。只有来源行显式声明 `candidate_is_current=True`，并且以下信息全部匹配，才允许当前比较使用结构化零退化界：

- `candidate_content_sha256`、`current_content_sha256` 都匹配实际 Skill hash。
- `candidate_version`、`current_version` 都匹配已提交内容版本。
- `candidate_source_policy_sha256`、`current_source_policy_sha256` 都匹配 contract 中的来源策略 hash。
- 实际 candidate/current 配对分数一致。
- 若提供 `candidate_applied` 或 `current_applied`，两者都必须存在、为显式布尔值且一致。

这些字段声明的是来源执行不变、同一已执行结果的共享重放，而不是独立生成碰巧同分。它们仍须由外层执行器真实生成。本版仅当单元内所有行具备有效 identity 时才给该单元豁免；部分行声明不会被扩大为整组 identity。该豁免只作用于对 Current 的安全检查，不豁免对 Base 的伤害，不豁免跨域收益或缺失保护单元。

没有 identity 元数据时按普通样本区间判断来源对 Current 的安全性：大样本同分可能通过非劣筛查，小样本同分仍可能 pending。任一 identity 字段、版本、hash、分数或 applied 状态矛盾都会抛出 ValueError，调用方必须将其视为不批准。

## 返回动作与已测行为

范围扩张可返回 `cross_domain_commit`、`restrict`、`reject`、`pending`，或 `keep_current_scope`。最后一个表示现有来源版本有新证据支持，但跨域扩张证据不足；不是再次提交同一内容。内容更新保留 v1 原有动作语义。结果保留逐单元双参考检查，并在 local 审计中显式标记只要求 Base 正增益，避免把 Current 的 gain=pending 隐藏掉。

[55 项新测试](../tests/test_scope_transition_gate.py) 覆盖：v1 tie 阻塞复现、来源 tie 不再要求第二次增益、内容更新仍须胜 Current、缺失/伪造 contract、改内容冒充 scope、版本/hash/分数/applied 矛盾、源域与跨域伤害、缺少来源/保护/预注册单元、同分不构成结构安全、部分 identity 不扩展、JSON 可序列化及输入不变。与旧 gate、来源、controls、session launcher 联合测试共 **128 passed**；新模块与新测试的 Ruff 检查通过。

模块继承 v1 固定样本 Wilson/配对检查的统计限制：没有跨单元、候选和多次查看的联合校正，也不证明未知域安全。它没有层次化 scope ladder、自动 Split 或 DeepResearch validator。本轮仅验证离线工程语义，不修改任何已冻结 run，不据此对 C/D 产生新的 Commit 或实验认证结论。
