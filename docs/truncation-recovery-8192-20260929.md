# 4096 → 8192 截断恢复诊断

日期：2026-09-29。状态：**18:11:44应用户要求停止**。18:09:51启动后完成5个KOR恢复位置（2 pass、3 fail），保留10个在途开放意图、149个未提交位置；没有完整恢复结果。没有存活求解进程或运行容器，不能直接CONT恢复；见[暂停交接与限制](truncation-recovery-pause-20260929.md)。

**后续：19:10:59已在独立B目录接续149个未提交位置**，不重抽A的10个中断调用，见[v2续跑与安全暂停](truncation-recovery-resume-20260929.md)。本页A的原结果与协议保持不变。

## 目的与边界

用户授权仅对输出截断增加一次8192-token重试。保留所有4096原始记录、分数、失败与成本，在独立输出目录冻结恢复清单；不修改历史协议，不重新启动SkillOpt/GEPA优化器。

本次是**已消费开发面板的事后交付恢复诊断**，不是独立方法效果、全量8192基线或新Skill的准入结果。同样的提示词再次调用也存在随机性，若没有4096等预算重试对照，不能把恢复全部因果归于预算增加。采用一次4096、截断后一次8192的流程，其累计生成预算最多12288，不是一次8192。

## 冻结范围

| 来源 | 旧面板位置 | 确证截断重试位置 | 新结果能说明什么 |
| --- | ---: | ---: | --- |
| KOR No-Skill | 1000 | 160 | 原提示词一次重试后的交付及原生判分 |
| Spreadsheet No-Skill B | 160 | 1 | 原脚本生成提示词一次重试；同一隔离执行与评分 |
| SkillOpt 第二候选选择 | 已评60/计划64 | 1 | 同一冻结候选、同一任务的一次独立恢复；不能补全原训练成绩 |
| ALF No-Skill B | 78 | 2 | 只重试截断动作调用，不能由此推断完整episode成功 |
| **合计** | 不合并为准确率分母 | **164** | 162个可重新评任务的位置＋2个动作调用诊断 |

HTTP400、公式缓存缺失、执行异常、操作中断等其他unknown不纳入。已正确和已判错的原位置均不重采样；不会依据新结果选择更好答案。若8192仍截断，保留unknown，不继续提升或抽样。

## 执行协议

- 模型、服务、temperature、low reasoning、原system/user及评分标准不变；仅单次生成上限4096→8192，使用新调用身份与缓存。
- 源任务、repeat、checkpoint/candidate、旧调用及旧产物均需通过绑定检查。公开提示词没有隐藏答案；重新评分仅在宿主侧执行。
- 新入口独立于原`generate`/`run_stage`，不覆盖旧终态，不批准Skill，也不把反馈送回更新器。
- 新调用先持久化intent，终态重放不产生新模型调用；开放intent不能静默重新抽样。网络有限重试继承已冻结客户端，并单独报告HTTP次数和完整计费未知。
- PJLAB Linux后台运行，在同一shell执行`proxy_on`，显式使用既有无凭据网关。第一条真实响应确认服务正常后才释放并发，最多10。
- ALF原环境已关闭，原动作提示词可以精确重试，但不伪造`won`或episode分数。完整episode恢复另需独立协议，本次不做。

配置：[恢复源清单](../configs/continual_eval/truncation_recovery_20260929.json)。入口：[恢复程序](../skillopt/continual_eval/truncation_recovery.py)、[有限Linux启动脚本](../scripts/run_truncation_recovery_linux.sh)。

Linux独立快照目录为`/root/continual-truncation-recovery-20260929-a`，凭据只读取既有本地配置，不进入新协议。命令在该目录执行：

```bash
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery prepare \
  --spec configs/truncation_recovery_20260929.json --output run

# 在Linux交互Bash内运行；脚本在同一shell调用proxy_on。
bash -ic 'source scripts/run_truncation_recovery_linux.sh /root/continual-truncation-recovery-20260929-a'

/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery report \
  --output run
```

## 启动前检查

- Linux只读导入已核验164条确证截断、2714个绑定源文件，所有原调用均4096上限及`finish_reason=length`，没有发起模型调用。
- KOR、Spreadsheet、BigCodeBench三个Docker依赖探测均ready、清理确认；0模型调用，不是方法效果。
- 本地既有相关回归：211 passed、7 skipped。7项因本机未安装可选固定GEPA，不能记作通过，也不属于此次截断恢复的调用依赖。
- 新恢复入口15项专门fixture测试在本机和Linux分别全部通过、0跳过；相关本地合测226 passed、7 skipped（可选GEPA未安装，不把跳过算通过）。Ruff及启动脚本语法检查通过。
- 独立review确认原结果只读、原prompt/候选/服务绑定、单次重试、ALF无episode评分、开放intent不重抽。补齐镜像旧请求去重、No-Skill入口范围及候选原生提案来源绑定。

## 当前运行与回放

- 冻结恢复协议：`eac632a9c022cf53ec32cdcb2a42361e8ba512faa4ed753f1b38de31d54dbd77`。
- Linux原tmux：`continual-truncation-8192-20260929-a`（已退出）；日志：上述独立快照目录的`launch.log`；新证据：`run/positions/`与`run/api/`。
- 共164条不同原请求；KOR160位置来自93道不同任务、18个规则族，重复位置不算新增独立题。ALF两条来自两道任务，其余两域各一道。
- 首条KOR完整交付但原生判错，说明“解除截断”与“任务正确”必须分别报告。此单例不是总体结论。
- 进度查询使用上面的`report`命令，只读统计；开放调用不将其当成终态模型失败。本轮提前由用户暂停，恢复必须先处理已明确保留的中断，不能直接重启绕过检查；不启动其他学习或扩大预算。

## 必须保留的原结论

SkillOpt第一候选28/64、空父39/64，两者均0 unknown；此项负结果不因本次重试改变。第二候选尚有4个未提交任务，恢复1次截断不等于完成训练。Spreadsheet的主要52个公式缓存unknown也不在本次修复范围内。

[原始结果总表](experiment-results-20260929.md) · [流程](current-workflow.md) · [结果账本](results-and-lessons.md)
