# V14 跨域约束反馈与局部 Skill 更新实验

主比较为 Constrained − Independent；全部冻结末轮 Skill 直接进入最终评测，没有选择最优候选或历史。

## 方法与对照

模型 glm-5.3；3 条学习历史 × 2 轮 × 两个更新臂。两臂使用相同 Coding + Spreadsheet 开发任务及 solver/optimizer 调用机会；Constrained 额外使用预先编写的约束反例测试，并生成与证据关联的局部修改。这是组合干预：等模型调用机会，但不等 oracle/context 预算，不能分离反例与局部修改的贡献。
三个策略使用相同的生成＋公开反馈修订求解器：仅在修订回复 API/格式不可用时保留可交付初稿；不根据隐藏分数选择初稿或修订稿。Rule Reasoning 不进入开发反馈，全部 Skill 冻结后才评测。

## 冻结后的最终效果

24 个新合成任务，每个结构家族一个实例；coding: 8 家族 / spreadsheet: 8 家族 / rule_reasoning: 8 家族。216 个策略位置对应 216 条唯一轨迹、432 次唯一最终请求。
NoSkill 为 72 条实际轨迹、144 次请求；每条历史均重新调用，不跨历史复用。实际分开调用不证明提供方随机种子独立；同一历史内相同任务＋Skill 的别名仅计一次真实成本。
分数为全尝试成功率：交付失败或不可评保留在分母并计 0。先平均任务内历史，再平均家族内任务、域内家族，最后三域等权。

| 策略 | Coding | Spreadsheet | Rule Reasoning | macro | 最差域 | 对 Base 最大域退化 |
|---|---:|---:|---:|---:|---:|---:|
| NoSkill | 100.00% | 58.33% | 70.83% | 76.39% | 58.33% | 0.00 pp |
| Independent | 100.00% | 87.50% | 58.33% | 81.94% | 58.33% | 12.50 pp |
| Constrained | 100.00% | 87.50% | 62.50% | 83.33% | 62.50% | 8.33 pp |

### 交付与可评分层（策略位置计数）

| 策略 | 位置 | 交付失败 | 已交付但不可评 | 可评成功率（条件诊断） | 非空 Skill 覆盖 |
|---|---:|---:|---:|---:|---:|
| NoSkill | 72 | 13 | 0 | 93.22% | 0.00% |
| Independent | 72 | 13 | 0 | 100.00% | 100.00% |
| Constrained | 72 | 12 | 0 | 100.00% | 100.00% |

条件可评成功率不能替代全尝试主分数；非空文字不证明学到新机制或实际遵循 Skill。

### 各历史 macro

| 历史 | NoSkill | Independent | Constrained |
|---|---:|---:|---:|
| 0 | 79.17% | 70.83% | 83.33% |
| 1 | 75.00% | 83.33% | 87.50% |
| 2 | 75.00% | 91.67% | 79.17% |

历史间波动混合了 Skill 学习差异与求解采样差异，不能单独解释为模型随机性。

### 预设主比较：Constrained − Independent

| 终点 | 差值 | 家族 bootstrap 95% CI | 双侧 p | Holm p | sign-flip |
|---|---:|---|---:|---:|---|
| macro | +1.39 pp | [-2.78 pp, +5.56 pp] | 1.0000 | 1.0000 | 精确 |
| spreadsheet | +0.00 pp | [+0.00 pp, +0.00 pp] | 1.0000 | 1.0000 | 精确 |

两个主终点作 Holm 校正；CI 按域内家族分层重采样，条件于已冻结学习历史。3 条历史和家族内实例不能充当更多独立结构家族。每域 8 家族仍低功效；若 8 个非零家族差异同向，单域双侧精确 p 最小为 2/2⁸ = 0.0078125，少于 8 个非零差异时更粗。零宽 bootstrap 区间不证明精确、等效或安全；CI 与 sign-flip 并非同一检验的互逆结果。

### 探索性比较（不作为额外确认性发现）

| 比较 | 终点 | 差值 | 95% CI | 未校正 p |
|---|---|---:|---|---:|
| constrained_vs_independent | coding | +0.00 pp | [+0.00 pp, +0.00 pp] | 1.0000 |
| constrained_vs_independent | rule_reasoning | +4.17 pp | [-8.33 pp, +16.67 pp] | 1.0000 |
| independent_vs_no_skill | macro | +5.56 pp | [-6.94 pp, +18.06 pp] | 0.5859 |
| independent_vs_no_skill | coding | +0.00 pp | [+0.00 pp, +0.00 pp] | 1.0000 |
| independent_vs_no_skill | spreadsheet | +29.17 pp | [+0.00 pp, +58.33 pp] | 0.1875 |
| independent_vs_no_skill | rule_reasoning | -12.50 pp | [-33.33 pp, +8.44 pp] | 0.5312 |
| constrained_vs_no_skill | macro | +6.94 pp | [-6.94 pp, +19.44 pp] | 0.4863 |
| constrained_vs_no_skill | coding | +0.00 pp | [+0.00 pp, +0.00 pp] | 1.0000 |
| constrained_vs_no_skill | spreadsheet | +29.17 pp | [+0.00 pp, +58.33 pp] | 0.1875 |
| constrained_vs_no_skill | rule_reasoning | -8.33 pp | [-37.50 pp, +16.67 pp] | 0.7812 |

### 配对 gain/loss 与未知

| 比较 | win | loss | tie | 任一不可评 | 可评失败损失 | 交付失败损失 | 已交付不可评损失 |
|---|---:|---:|---:|---:|---:|---:|---:|
| constrained_vs_independent | 5 | 4 | 63 | 17 | 0 | 4 | 0 |
| independent_vs_no_skill | 11 | 7 | 54 | 20 | 0 | 7 | 0 |
| constrained_vs_no_skill | 11 | 6 | 55 | 19 | 0 | 6 | 0 |

上述为相关位置计数，不是独立试验数；unknown 可与 win/loss 重叠。可评失败可能包含运行异常，不能把全部 loss 称为纯推理错误或机制毒害。

## 全部更新与交付保护

| 历史 | 轮次 | 更新臂 | 有效 | 改变父 Skill | 局部操作数 | probe 引用数 |
|---|---|---|---:|---:|---:|---:|
| 0 | 0 | constrained | 1 | 1 | 2 | 8 |
| 0 | 0 | independent | 1 | 1 | 0 | 0 |
| 0 | 1 | constrained | 1 | 1 | 1 | 8 |
| 0 | 1 | independent | 1 | 1 | 0 | 0 |
| 1 | 0 | constrained | 1 | 1 | 2 | 8 |
| 1 | 0 | independent | 1 | 1 | 0 | 0 |
| 1 | 1 | constrained | 1 | 1 | 1 | 8 |
| 1 | 1 | independent | 1 | 1 | 0 | 0 |
| 2 | 0 | constrained | 0 | 0 | 0 | 8 |
| 2 | 0 | independent | 0 | 0 | 0 | 0 |
| 2 | 1 | constrained | 1 | 1 | 2 | 8 |
| 2 | 1 | independent | 1 | 1 | 0 | 0 |

全部 12 次更新均保留；有效 10 次，文本变化 10 次。约束 probe 共 32 次唯一额外原生评估；引用数可能因同一父链别名重复，不能直接作执行成本。没有 selection gate 或挑选最好候选。有效但未改变文本可为合法保留/弃权，不是解析失败，也不能算作学到新 Skill；最终空 Skill 与同历史 NoSkill 可精确共享轨迹，其无退化不能证明已学出泛化能力。

| 最终策略 | 非空 Skill / 位置 | 修订 API 不可用后保留初稿 | 修订格式不可用后保留初稿 |
|---|---:|---:|---:|
| NoSkill | 0/72 | 0 | 1 |
| Independent | 72/72 | 0 | 0 |
| Constrained | 72/72 | 0 | 0 |

以上是策略位置；去重后最终 216 条真实轨迹中，1 条触发交付保护。该数字不是隐藏语义修复收益；初稿仍可语义失败，不把保护后的可交付率解释为跨域泛化。

## 实际成本与离线核验

逻辑调用 524/640；HTTP 尝试 592；成功 514；终止错误 10。闭合账本包含 solver 请求 512、optimizer 请求 12。
记录输入 token 1328611、输出 token 92471、总 token 1421082；10 次缺少 usage。缺失 usage 不视作实际零消耗，不推算未核实价格。
已锁定回放并核对 5017 个证据文件；报告阶段模型调用 0、原生执行 0，整个实验目录逐文件字节不变。稳定摘要仅排除根级 supervisor.log 调度日志；回放前后字节检查仍包含该日志，所有科学回执均纳入摘要。
结果哈希：92e04d6bc9c553190250e16e47e35c2b0a586d8bc97bdf0f9b68b1686e21dacf；审计哈希：e277a7c43305856abdd97d24f0ccf9f7aca5c856a10c3823733a5d013ed8e550。

## 解释边界与下一步

这是新编合成结构上的探索性实验，不是公开 benchmark 复现；两个自写更新器均非原生 SkillOpt，未运行 DeepResearch，也未识别 Research/Rubric 独立贡献。当前比较同时改变约束证据、上下文与局部更新形式。与 V12 的任务面板和求解器均不同，不能把跨版本分数差直接归因于某一个改动。
下一步在新且更多独立家族、公开 benchmark 上冻结评测，并以等 oracle/context 预算拆分 probe 与局部更新消融；增加同族变体或只挑有利历史不能代替独立家族。没有显著退化不等于无害，本实验不提供安全、非劣效或普遍跨域泛化认证。
