# 小规模单轮 Skill 更新：协议与运行说明

日期：2026-09-18。定位：真实模型探索实验，不是正式准入或跨域效果证明。

## 本轮回答的问题

能否把新主线中可见的、绑定执行证据的 Rubric 反馈，真正用于修改父 Skill，并在未用于更新的任务上比较原始效果？同时检查 Research 是否带来了不同于固定验证器的有效反馈。

固定父 Skill → 开发任务上的 No-Skill / Parent 产物 → 三种验证反馈 → 一次 Skill 文本更新 → 冻结候选 → 独立最终任务上的原始配对执行。

固定验证器、无 Research 自适应验证器、Research 自适应验证器共用相同开发产物。有效反馈完全相同时，共享同一个 updater 请求；相同 Skill 文本在同题同重复下也共享求解请求。这是消除不可识别对照，不是三次独立学习历史。

## 预先固定的设置

| 项目 | 设置 |
| --- | --- |
| 数据 | 仓库已固定版本的 MBPP-sanitized，静态兼容子集 |
| 开发 / 验证器校准 / 最终 | 8 / 4 / 16 个原始任务 ID |
| 重复 | 最终每个条件 2 次；仍只有 16 个任务 ID |
| 排除 | 历史已使用、预留任务及保守词面近重复族；选择不查看本轮结果 |
| 父 Skill | V16 第一条学习历史的第一轮 fixed Coding 更新，不按新结果挑选 |
| 模型 | 仓库 PJLAB 配置，glm-5.3，temperature=0，reasoning_effort=low |
| 调用限制 | 并发 4；最多 191 个逻辑请求；每次最多 2048 输出 token |
| 检查 | 原生 Python assertion；首条例子公开，其余仅宿主独立审计可见 |
| 最终条件 | No-Skill、Parent、三个反馈分支的候选；重复内容去重并披露 |
| 执行 | SSH 到独立代码快照，固定镜像的 Linux Docker；无网络、资源受限 |
| 更新格式 | Mechanism / When / Procedure / Avoid，或 NO_UPDATE |

原始断言仍使用 Python 的类型与比较语义，不把返回值转换成 JSON 后比较。所有任务、失败和 unknown 保留分母；参考实现未通过时，该题标为审计不可用，不换题。API、解析、执行基础设施问题与已确认的任务错误区分。

## 证据和预算边界

- Research 只读取公开契约、匿名产物、公开执行以及显式标记的开发审计缺口类别；不读取隐藏测试、参考代码或最终结果。
- Skill updater 只读取重新绑定实际公开执行回执的开发反馈；不读取开发隐藏答案、校准结果或最终结果。
- 两个自适应验证器提案在校准前冻结；校准不足正常 Pending。此次验证器可用于明确标记的探索候选，不拥有部署或范围扩大授权。
- 当前只有 `public_examples`、`input_state`、`public_invariant` 三种受限检查配方。MBPP 契约只有 requested_behavior 和一个公开例子，没有输入保持义务及公开关系，因此现有接口实际上不能产生新的有效检查。此次不检验 Research 有效或无效，只检验共享父 Skill 的更新链；反馈相同时标记 `collapsed_intervention`，只算一个候选。不能给 MBPP 强加未声明的不变性来制造对比。
- 只有一个学习历史。词面去重不等于语义任务族完全独立；数据也不是项目级划分。本轮不是标准完整 MBPP 成绩，更不是未见领域迁移。
- 调用有不可变 intent/receipt；已完成请求缓存复用。中断且无完整回执时停止，不能自动重采样。基础设施异常停止后续付费阶段。
- API 自身最多三次 HTTP 尝试；报告实际尝试数和可获得的 token。如果失败重试的 token 不可得，不把终态 token 称为完整成本。
- Docker 观测用于非对抗性测量，不宣称能抵抗主动篡改 Python 测试器的恶意产物。

## 新代码与命令

新增 `single_round_data.py`（数据/父 Skill 固定）、`single_round_feedback.py`（公开反馈与 updater）、`single_round.py`（单轮编排）、`remote_executor.py`（复用 Docker 的 SSH 传输）。历史实验不修改。

```bash
python -m skillopt.skill_validation.single_round prepare \
  --repo "$PWD" --output "$PWD/outputs/skill_validation/single_round_20260918_a"
python -u -m skillopt.skill_validation.single_round run \
  --repo "$PWD" --output "$PWD/outputs/skill_validation/single_round_20260918_a" \
  --remote-repo /root/skillval-round-20260918.N7kgRn --workers 4
```

运行前先将源代码快照同步到上述新目录，不传输 `.env`。API 留在本机，产物执行在开发机隔离容器中。不要修改已固定的源码后直接复用同一运行目录。

结果分别保存为数据清单、协议、模型回执、Research 提案、公开执行证据、反馈、冻结候选、宿主审计和 `results.json`。最终报告另写，不能用工程 fixture 的结果替代真实运行。
