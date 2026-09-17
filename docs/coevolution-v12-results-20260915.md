# V12 跨域 Skill 内容进化实验报告

主比较为未经过选择筛选的 Contrastive − Independent；selected 仅为部署诊断。

## 做了什么

模型 glm-5.3；3 条历史 × 3 轮 × 两种更新方法。两臂使用相同 Coding + Spreadsheet 开发任务、更新机会及调用上限；首轮后 Skill 和实际轨迹可以不同，因此不是完全相同的行为证据。每条求解轨迹均为生成后一次公开反馈修订。
Independent 使用独立记录的固定反馈；Contrastive 增加 NoSkill/current 配对反例及对照指令，直接修改 Skill 内容。Rule Reasoning 不进入开发和选择反馈。

## 冻结后的最终结果

36 个任务变体，结构簇分别为 coding: 4 / spreadsheet: 4 / rule_reasoning: 4；540 个策略位置，对应 360 条唯一最终轨迹、720 次唯一最终请求。

以下均为全尝试成功率：不可交付/不可评尝试计 0，不从分母删除。先在任务内平均历史，再平均簇内任务、域内结构簇，最后三个域等权。

| 策略 | Coding | Spreadsheet | Rule Reasoning | 域等权 macro | 非空 Skill 覆盖 | 可评位置 |
|---|---:|---:|---:|---:|---:|---:|
| NoSkill | 50.00% | 91.67% | 83.33% | 75.00% | 0.00% | 102/108 |
| Independent（raw） | 75.00% | 88.89% | 100.00% | 87.96% | 100.00% | 104/108 |
| Contrastive（raw） | 80.56% | 80.56% | 97.22% | 86.11% | 100.00% | 104/108 |
| Independent（selected 诊断） | 72.22% | 94.44% | 83.33% | 83.33% | 66.67% | 104/108 |
| Contrastive（selected 诊断） | 83.33% | 80.56% | 97.22% | 87.04% | 100.00% | 107/108 |

非空覆盖仅表示部署了文字，不证明学到了新机制。

### 各历史的域等权 macro

| 历史 | NoSkill | Independent（raw） | Contrastive（raw） | Independent（selected 诊断） | Contrastive（selected 诊断） |
|---|---:|---:|---:|---:|---:|
| 0 | 75.00% | 88.89% | 88.89% | 80.56% | 91.67% |
| 1 | 75.00% | 80.56% | 83.33% | 75.00% | 83.33% |
| 2 | 75.00% | 94.44% | 86.11% | 94.44% | 86.11% |

### 预设主比较：raw Contrastive − raw Independent

| 终点 | 差值 | 结构簇 bootstrap 95% CI | 双侧 p | Holm 校正 p |
|---|---:|---|---:|---:|
| macro | -1.85 pp | [-6.48 pp, +2.78 pp] | 0.7656 | 1.0000 |
| rule_reasoning | -2.78 pp | [-8.33 pp, +0.00 pp] | 1.0000 | 1.0000 |

CI 按域内结构簇分层重采样；两个预设终点用 Holm 校正。统计量条件于这些已冻结历史；变体、历史别名和缓存复用不增加独立样本数。未见域只有 4 个结构家族：双侧精确 sign-flip 的最小 p 为 2/2⁴ = 0.125，所以无论观测效应多大，本设计均不能在 0.05 水平确认 Rule 增益；这里只估计方向与幅度。macro 有 12 个结构家族，可取得更小的 p。区间跨零不等于没有效果，也不证明无害。

### 配对 gain/loss 与不可评

| 比较（前者−后者） | win | loss | tie | 任一不可评 | 可评失败损失 | 交付失败损失 | 已交付但不可评损失 |
|---|---:|---:|---:|---:|---:|---:|---:|
| contrastive_vs_independent | 8 | 10 | 90 | 8 | 6 | 4 | 0 |
| independent_vs_no_skill | 18 | 4 | 86 | 10 | 1 | 3 | 0 |
| contrastive_vs_no_skill | 20 | 8 | 80 | 10 | 4 | 4 | 0 |
| selected_independent_vs_no_skill | 13 | 4 | 91 | 8 | 2 | 2 | 0 |
| selected_contrastive_vs_no_skill | 21 | 8 | 79 | 7 | 7 | 1 | 0 |
| selected_contrastive_vs_selected_independent | 12 | 8 | 88 | 5 | 7 | 1 | 0 |
| selected_independent_vs_independent | 6 | 11 | 91 | 8 | 8 | 3 | 0 |
| selected_contrastive_vs_contrastive | 7 | 6 | 95 | 4 | 6 | 0 | 0 |

这些是相关的策略位置计数，不是独立试验数；不可评可与 win/loss 重叠。可评失败也可能包含运行异常，不能把全部 loss 解释为纯推理错误或 Skill 机制毒害。

## 全部候选与选择结果

| 更新臂 | 候选次数 | 有效文本 | 改变父 Skill | selection 接受 |
|---|---:|---:|---:|---:|
| independent | 9 | 9 | 9 | 3 |
| contrastive | 9 | 9 | 9 | 4 |

包含全部 18 次候选更新，不挑选有利历史。selection 仅在新的同开发域小切片上严格提升时替换诊断部署文本；不改变 raw 进化父链，也不是跨域安全认证。

## 实际消耗与审计

逻辑调用 1090/1536；HTTP 尝试 1117；成功调用 1084；终止错误 6。
账本记录输入 token 2387272，输出 token 325867，总 token 2713139；4 次缺少 usage。缺失 usage 不视作真实零消耗；不根据未核实价格估算费用。

完整回放核对 9667 个已有文件，实验目录内容不变；报告阶段模型调用 0、原生代码执行 0。只在 docs 新建不可变报告。
稳定证据摘要仅排除根级 supervisor.log（运行调度日志）；回放前后的逐文件字节一致性检查仍包含该日志，科学回执不作任何排除。
结果摘要：5db387d518f8a49b49165924561601e7a1aa358ddf216e9c9926a168f1d7fda5。审计摘要：6b26c10a9653aa28d628e2c0978ad0153fb431aa7da1a00b831ea474dab79d30。

## 能说明什么与下一步

这是原创合成任务上的探索性内容进化实验，不是公开 benchmark 复现；两个自写更新器均非原生 SkillOpt。当前对比不能分离配对证据与对照指令的贡献，也没有测量 DeepResearch 或 Rubric 协同进化的独立贡献。只有两个开发域及一个未见域，且没有独立预注册的 near-miss 任务组；不能宣称安全认证、非劣效或全面跨域泛化。
下一步应冻结本次结论与所有候选，在新任务/显著更多独立结构家族及公开 benchmark 上验证；单纯增加同家族变体或共享轨迹重复，不能弥补未见域检验的分辨率限制。若引入 Research/Rubric，应增加等预算的独立消融，而非用 selected 的最好结果替代 raw 主比较。
