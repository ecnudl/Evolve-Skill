# v1 Gate 固定样本量审计

结论：在**无结构性 identity、Base / Current / Candidate 全对且全平局**的保护 cell 中，当前主配置至少需要 **46 个独立任务**才能同时通过非劣性（NI）与条件伤害检查；严格敏感性配置需要 **96 个**。A 的 confirmation 每 cell 只有 32 题，所以这种 cell 即便观察到零错误，NI 仍然只能是 `pending`。

这是当前实现对“零 discordance、reference 全对”情形的数值下界，**不是统计功效保证，也不是任意有收益分布的全局最小 N**。A 的正例没有提升空间，构成另一项独立阻断；不能将最终全部 fallback 归因于样本量。

## 审计范围

只读检查 [gate.py](../skillopt/cross_domain/gate.py)、[experiment.py](../skillopt/cross_domain/experiment.py)，以及已经完成的 A [protocol](../outputs/cross_domain/scope_mvp_gpt55_20260907/protocol.json) 和 [frozen policies](../outputs/cross_domain/scope_mvp_gpt55_20260907/frozen_policies.json)，并用内存合成的二元结果运行原 `pair_stats` / `_cell_status`。

本次读取的 `gate.py` SHA256 与 A 冻结记录完全一致：

```text
55cb0b92224d7846576c80016a18b2dc1c58f7b403d11dc5906d2a6329a7c9b1
```

没有调用 API，没有读取 C/D 的新数据、结果或 holdout，没有修改任何阈值、代码或冻结产物。D 的样本规模仅引用其预注册设计，不作结果审计。

## 1. 实际公式与最小 N

Gate 按 `(group, domain, mechanism)` 分 cell，分别对 Base 和 Current 检查。令：

- `N`：该 cell 的独立任务数。
- `W`：reference 错而 Candidate 对的次数。
- `L`：reference 对而 Candidate 错的次数。
- `R`：reference 正确的次数；条件伤害的分母是 R，不是 N。

`confidence=0.95` 时，净收益区间由 W/N、L/N 两个 **97.5% Wilson 区间**相减构成；这是单个比较内部的 Bonferroni 分配。条件伤害 L/R 使用 **95% Wilson 区间**。

在 `W=L=0` 且 `R=N` 时，实际公式化简为：

```text
a = Φ⁻¹(0.9875)² = 5.0238861873
b = Φ⁻¹(0.9750)² = 3.8414588207

净收益区间下界 Δ_L = −a / (N + a)
条件伤害区间上界 H_U = b / (N + b)

NI 通过条件：Δ_L ≥ −ε
伤害通过条件：H_U ≤ η

N_NI = ceil[a × (1−ε) / ε]
R_harm = ceil[b × (1−η) / η]
```

还需满足 `min_group_n=16`。本审计中 Base 与 Current 完全相同，所以两组比较同时得到相同结论。

| 配置 | NI 容忍 ε | 伤害上界 η | NI 所需 N | 零伤害所需 reference-correct R | 全对全平局时最小 N |
|---|---:|---:|---:|---:|---:|
| A 主配置 | 0.10 | 0.15 | 46 | 22 | **46** |
| 严格敏感性 | 0.05 | 0.10 | 96 | 35 | **96** |

原函数逐 N 枚举的结果与公式一致。几个边界值如下；区间数值为比例，例如 `−0.135693` 即 `−13.5693` 个百分点。

| N | Δ_L | H_U | 主配置 safety | 严格配置 safety |
|---:|---:|---:|---|---|
| 16 | −0.238961 | 0.193608 | pending | pending |
| 24 | −0.173095 | 0.137976 | pending | pending |
| 32 | −0.135693 | 0.107179 | pending：NI 不足 | pending：NI 与伤害均不足 |
| 45 | −0.100430 | 0.078652 | pending：NI 不足 | pending |
| 46 | −0.098461 | 0.077074 | pass | pending：NI 不足 |
| 64 | −0.072785 | 0.056624 | pass | pending：NI 不足 |
| 95 | −0.050227 | 0.038865 | pass | pending：NI 不足 |
| 96 | −0.049730 | 0.038476 | pass | pass |

这里的 `pass` 仅指该 cell 的 safety 检查；不意味着 positive gain 通过，更不等于整个 scope 获准扩张。`pending` 是证据不足，不是已经证明模型造成伤害。

## 2. 为什么一次应用也会影响全 cell

当前 `structural_identity` 是 **all-rows 条件**：Candidate 必须在该比较的整个 cell 中都有事前明确的 Base identity 合同；对 Current 的 identity 还要求 Current 本身同样明确等于 Base。不能根据执行后的分数相等反推 identity。

离线构造 N=32、三臂全对时：

| 事前路由行为 | structural identity | 主配置 safety |
|---|---|---|
| 全 32 题明确使用同一 Base，Current 也明确为 Base | 是 | pass，区间结构性为零 |
| 31 题明确 fallback，1 题注入 Skill，但结果仍全对 | 否 | pending，Δ_L=−0.135693 |
| 32 题均注入 Skill，结果全对 | 否 | pending，同一区间 |

因此，对于全平局的保护 cell，非空应用足以失去整个 cell 的 identity 特例。实现并没有进一步利用“仅 1/32 题会应用”的结构来收紧 NI 区间。这是当前统计设计的保守性，不是那一道应用题产生错误的证据。

结构性 fallback 只说明这些输入使用同一策略；它不约束未观察输入上的 router 误触发概率。全部 fallback 也不能证明 Skill 收益、来源覆盖率或跨域泛化。

## 3. A：样本量限制与正例天花板必须分开

A 预注册 validation 每 cell 64 题，按 cell 交替划分为 fit 32 / confirmation 32；冻结记录共 320 个 fit ID 和 320 个 confirmation ID，各 gate audit 的 N 均为 32。fit 已用于形成允许范围，不能再并入 confirmation 冒充独立确认。后续 test 同题重复生成也不能按独立新任务叠加样本量，或回头替换已冻结的 confirmation 决策。

32 题不足以让上述非 identity 的全平局保护 cell 通过主 NI；这个设计在看到具体答案之前就可算出。

但 A 冻结记录还直接显示：两个 Skill track 的 coding / spreadsheet 正例在各方法下，Base、Current、Candidate 都为 100%，相应 gain 为 `fail`。对这些样本，Base 已全对意味着 `W=0`；候选最多打平，无法满足正净增益条件。仅增加同类满分样本，即使 safety 变为 pass，也不会产生 gain 证据。

实际六个 `track × method` 都退回 fallback。其中只有 EV / domain 的主 confirmation 理由包含 `protected_cell_safety_not_established`；其他方法的保护检查可以因结构性 fallback 成立。所有方法均包含来源收益未接受和跨域正收益未建立的原因。因此不能把“6/6 fallback”表述为样本量单独导致，也不能将 fallback 后没有退化当成 Skill 跨域成功。

## 4. 下界不等于功效或充分预算

46 / 96 的结论限定于 `W=L=0`、`R=N`，不是所有可能结果的最小 N。例如原 gate 在 **N=32、5 wins / 0 losses、R=27** 时，主配置得到：

```text
Δ_L = −0.074449
H_U =  0.124555
NI / harm / gain 均 pass
```

正收益可以抬高 NI 下界；所以不能笼统写成“任何非空策略 N<46 都绝对无法通过”。反过来，没有收益且出现损失时需要更多样本。以下也是离线确定性枚举，不是功效计算：

| 固定 losses，wins=0，reference 全对 | 主配置最小 N | 严格配置最小 N |
|---|---:|---:|
| 0 | 46 | 96 |
| 1 | 64 | 133 |
| 2 | 81 | 166 |
| 3 | 96 | 198 |

这张表固定的是“损失次数”，不是未知的真实损失概率；扩大样本时不能假定损失次数永远不变。也不能运行到首次 pass 就停止，否则已经改变 fixed-sample 协议。

若 reference 正确数较少，零损失时 harm 仍分别至少需要 **22 / 35 个正确 reference**。例如主配置 N=46 但 R=21，NI 可以通过而 harm 仍不能通过；R=0 时区间为 `[0,1]`。Base 与 Current 的正确数不同，必须分别检查。若同时存在 wins，NI 可能改善，因此“reference 更少”主要指条件伤害证据变弱，不是整体所需 N 必然单调增大的定理。

此外，现有 Wilson 是近似 fixed-sample screening；没有跨 cell、reference、候选数和反复查看的多重比较控制，没有对相关模板、服务漂移或未见领域提供保证。即使满足这些数值门槛，也不能称为正式安全认证。

## 5. D 的 16/group 只适合诊断

D 每个 split 预注册 positive / near-miss / unrelated 各 16 题，还分散到 3 或 4 个领域及多个机制边界。即使不分领域，N=16 的理想全对全平局区间也无法通过两种配置；按实际 `(group, domain, mechanism)` 再分 cell 后更稀疏，很多 cell 连 `min_group_n=16` 都不到。

这些控制题用于发现固定完整 Skill 的适配、边界行为与路由覆盖问题，不用于 Gate 认证。较大的来源样本、合并不同领域的总数、或 calibration 与 holdout 的简单相加，都不能替代每个保护 cell 的预先规划证据。本文不读取或推断 D 的实际结果。

## 6. 下一轮采样规划方向

1. **先确认可识别性。** 只用 train/dev 检查候选是否有真实触发前提、Base 是否存在合理提升空间、hard oracle 是否无歧义。来源收益、跨域正收益与保护任务分别规划，不能用保护组改善替代目标机制收益。
2. **按 cell 而不是总题数预算。** 明确未来要声明的 domain / mechanism / near-miss 边界以及两组 reference。46 / 96 仅作为全平局 NI 的起点；还应保证足够 reference-correct 观察，并留出损失、API 缺失及模板相关性的余量。
3. **在固定规则下做功效模拟。** 用独立 pilot 估计或给定一组保守的三臂联合二元结果分布，模拟完整 Gate 同时通过的概率；覆盖不同胜负差、损失率、reference 正确率和路由覆盖率。按预设目标功效选择固定 confirmation N，而不是承诺“收够 46 就一定通过”。
4. **将统计重设计独立版本化。** 如未来采用利用部分结构性 fallback 的区间、其他配对非劣检验、多重比较控制或允许连续采样的程序，应在新版本提前明确假设与停止规则；不更换当前区间后追认旧结果。
5. **留出独立冻结评测。** 形成候选和范围后冻结，再执行未参与设计的任务。不得因当前结果不显著就沿用原 fixed-sample 名义补样、放宽阈值或把相关重复当作新独立任务。

## 离线复核命令

以下仅执行纯统计文件，生成内存中的全对全平局结果，不导入模型后端、不读取任何实验任务、也不写文件：

```bash
python3 - <<'PY'
import runpy
gate = runpy.run_path('skillopt/cross_domain/gate.py')
for ni, harm in [(0.10, 0.15), (0.05, 0.10)]:
    cfg = gate['_config']({
        'confidence': 0.95,
        'noninferiority_margin': ni,
        'max_conditional_harm': harm,
    })
    for n in range(1, 301):
        rows = [dict(id=str(i), domain='audit', mechanism='audit',
                     group='nearmiss', baseline=1, current=1, candidate=1)
                for i in range(n)]
        stats = gate['pair_stats'](rows, confidence=0.95)
        safety, _ = gate['_cell_status'](stats, cfg)
        if safety == 'pass':
            print({'NI': ni, 'harm': harm, 'first_all_tied_safe_n': n})
            break
PY
```

预期输出：主配置 `46`，严格配置 `96`。
