# Skill–Verifier 最小准入闭环

日期：2026-09-20。新增入口 `skillopt.skill_validation.closed_loop`；保留历史实验与 9 月 18 日的探索入口，不覆盖原协议或结果。

## 为什么之前没闭合

之前的 `single_round` 可以改 Skill，但校准结论不控制 updater；最终只是强制使用候选并评分，没有 Skill Gate 或实际使用前的范围选择。另一个瓶颈是验证器只能检查既有输入：公开例恰好没有触发输入副作用时，“多加一条状态检查”也可能发现不了问题。

## 本次接通的流程

1. 固定父 Skill、开发／验证器校准／Skill 确认／最终四类任务，提前固定阈值、适用条件和探针预算。
2. No-Skill / Current 执行同一开发任务。Research 只读取公开证据及明确标记的开发审计缺口摘要，提出条件化 Rubric。
3. 为获准的方法实例化受限新输入。在独立校准任务上比较旧／新验证管线，保留独立审计 H 与可见检查 V 的边界。
4. **验证器未获授权就停止 updater。** 获准后，新检查在原开发产物上执行，真实回执进入结构化反馈，产生候选 Skill。
5. 冻结候选文本、版本、scope 和确认任务计划，在 `skill_confirmation` 做完整 No-Skill / Current / Candidate 配对。Skill Gate 输出 Local Commit／Restrict／Reject／Pending。
6. 依据已冻结决策和任务执行前可见的义务选择候选或干净 No-Skill；之后才做 final。强制候选成绩与条件部署成绩分开，final 不回流修改 Skill、Rubric 或 scope。

保存 `next_state.json` 供下一轮衔接，但本入口不自动长程迭代。下一轮需要新的分区和独立证据。

## 新检查不是新答案

`probe_recipes.py` 增加一个有界的 `reverse_list` 配方：

- 任务必须显式要求保持输入，且宿主注册的公开契约允许列表任意排序；缺失支持时不凭模型推断许可。
- 从一个合法公开输入产生最多一个逆序输入，保持类型、元素与长度；不预测新的返回值，不调用隐藏 oracle 补答案。
- 执行前后比较输入状态。仅“生成了输入”不计为发现错误，必须取得执行回执。
- 同任务三条件使用同一组检查。solver 仍只接收原始任务，不提前看到新增验证输入。
- 非输入保持任务不套用此检查；更换配方或实现源码会改变管线指纹，需要重新校准。

本次 Research 选择的是条件化 `input_state` 检查；`reverse_list` 是预先注册的宿主生成能力，**不是 Research 自行发明的任意测试算法**。

## 准入和范围控制

`admission.py` 将校准结果与完整验证管线绑定，并将授权检查放到 updater 和 Skill Gate 之前。Skill 的文本、版本、scope 或管线变化后不能继承旧证据。

目标区域要求相对 No-Skill 和 Current 有增量；保持区域检查退化；不适用区域检查禁用后的行为。当前 scope 只依赖公开义务，不读宿主机制标签、隐藏答案或执行后成败。没有已批准的 Current 时，回退为全新 No-Skill，不在候选改坏环境后继续执行并称作回退。

Restrict 只能使用确认前冻结的范围；不根据确认失败现场创造新条件，再宣称条件已经被同批数据验证。最终条件选择由 `select_skill()` 在求解之前完成。

## 工程 smoke 与真实授权必须分开

本次 CLI 只运行明确标记的工程样例：任务、产物、Research／updater 替身与 H 标签均是 fixture；Linux Docker 中的代码执行是真实的。

- 原 `VerifierDecision` 仍为 **Pending**，因为 fixture 不是自然模型证据。
- 只有显式 `engineering_simulation=True` 才能按相同阈值走 `engineering_accepted` 分支，验证后续代码路径。
- 工程决策的 `deployment_authorized` 永远为 false；默认真实路径拒绝工程授权。
- `run_round()` 提供真实 solver、Research、updater、独立 auditor 的宿主回调接口，但本次没有运行自然数据效果实验，也没有调用付费 API。
- 新例子采用了共同列表处理结构，操作与分区 ID 不重叠不代表它们是统计独立的研究样本。

### 运行命令

先同步当前源码到独立的 Linux 目录，不复制 `.env`。本次使用 `/root/skillval-closed-loop-20260920.1xuW7z`，固定 Docker 镜像延用原隔离执行器。

```bash
python -m skillopt.skill_validation.closed_loop \
  --output outputs/skill_validation/closed_loop_20260920_beneficial \
  --remote-repo /root/skillval-closed-loop-20260920.1xuW7z \
  --scenario beneficial
```

其他预声明场景使用新输出目录：`--scenario harmful`、`--scenario insufficient`；`--probe none` 检查没有新增有效证据时是否阻断更新。没有隔离环境时不退回宿主执行。

相同输出目录重复运行复用终态回执；未闭合 intent 不自动重试。改变源码、任务、阈值或配方必须使用新协议，不覆盖结果。

## 仍然没有宣称完成的能力

- 目前只有 Coding，不能发放 Cross-Domain Commit；目标领域需要独立适配、校准与确认。
- scope 依赖宿主核验的公开义务，引用存在不等于语义认证。
- 校准／确认的数据消费锁只覆盖当前输出目录。正式多轮实验需要共享消费记录，不能通过新建目录重复调参同一面板。
- 受限输入配方、脚本 Research 和工程通过率不能证明 DeepResearch 的独立收益或泛化改善。
- 真实实验仍需独立自然产物、多样正确解、合理难度与多次学习历史；unknown、成本和覆盖率不能隐藏。

新增文件：`admission.py`、`probe_recipes.py`、`closed_loop.py`、`closed_loop_fixtures.py`，及各自测试。

## 实际 smoke 结果

四组预先声明的工程场景已在远程固定 Docker 镜像中完成，共 **162 次真实隔离执行**，全部得到 observed 回执、确认完成清理。**0 次付费 API，0 次真实网页检索**；Research、updater 和产物生成均是明确标记的脚本替身。

| 工程场景 | 验证器工程准入 | Skill 结果 | updater 调用 | 实际检查的控制逻辑 |
| --- | --- | --- | ---: | --- |
| 有效新检查＋局部有效候选 | engineering_accepted | Restrict | 1 | 保留已冻结适用条件，范围外回退 |
| 相同检查＋有害候选 | engineering_accepted | Reject | 1 | 不因验证器通过而自动接受 Skill；最终全部回退 |
| 删除新增探针 | engineering_rejected | Pending，未生成候选 | 0 | 只有 Rubric 文本变化、没有新增检错证据时阻断 |
| 校准样本不足 | engineering_pending | Pending，未生成候选 | 0 | 不降低门槛，不让 updater 继续更新 |

上述所有场景的**正式自然数据 Verifier Gate 均为 Pending，真实部署授权均为 false**。工程模拟授权不能进入默认真实路径。

### 检查是否真的改善

在专门构造的校准控制中，旧检查对两个输入副作用缺陷检出 **0/2**，增加合法逆序输入与状态比较后检出 **2/2**；正确义务误拒 **0/10**，Near-Miss 条件误用 **0/4**。这些分母是产物／义务槽位，**不是独立任务数或模型效果估计**。

关键现象：原输入已经排好序，错误程序执行原地排序时状态看似不变；逆序输入才暴露副作用。去掉逆序探针后，虽然仍有状态检查，但没有新增检出，校准门会拒绝。这验证了“新执行证据”而非“多写一条检查描述”在控制路径中真正起作用。

### 范围限制是否真的生效

有效场景的三道最终工程题中，强制候选为 **2/3**；预先冻结的条件策略为 **3/3**，范围外 1/3 使用独立的 No-Skill 产物。有害场景中强制候选为 **0/3**，准入拒绝后策略回退为 Base 的 **2/3**，没有把全部回退写成学习收益。

这些结果由手写产物与人工审计标签构成；最终公开检查也实际执行并与标签一致。它们证明路由／拒绝实现正确，**不证明模型学到了更好的 Skill，不证明 Research 独有收益，也不是跨域泛化成绩**。

### 测试与回放

- 新增 **82 项测试**，相关测试合计 **672 passed**，Ruff 与 Git whitespace 检查通过。
- 正向、拒绝、unknown、样本不足、Near-Miss、final 泄漏、旧版本／管线冒用、工程授权误用、未闭合请求等分支均有覆盖。
- 对全部四组完整回放时禁止执行器、solver、updater、auditor、Research 与检索回调再次运行：**922 份 JSON 字节保持不变，新增执行／调用均为 0**。
- 不覆盖 9 月 18 日结果，不修改历史协议，不进行 Git 推送或密钥配置变更。

产物目录：

```text
outputs/skill_validation/closed_loop_20260920_beneficial/
outputs/skill_validation/closed_loop_20260920_harmful/
outputs/skill_validation/closed_loop_20260920_no_probe/
outputs/skill_validation/closed_loop_20260920_insufficient/
outputs/skill_validation/closed_loop_20260920_audit/cache_replay.json
```

结论：此前缺少的**新检查实例化、校准对更新的硬控制、独立 Skill 准入和执行前范围选择**已经在最小 Coding 工程闭环中接通。下一步应以真实模型和独立自然产物替换脚本替身，验证这些连接是否带来收益；不能用本页 smoke 成绩代替该研究实验。
