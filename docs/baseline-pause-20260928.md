# 2026-09-28 实验暂停与恢复交接

用户要求暂停，禁止自动启动后续实验。飞书配置仍暂缓；结果摘要见[本轮Markdown](noskill-baseline-summary-20260928.md)。

## 已保存进度

| 实验 | 暂停现场 |
| --- | --- |
| SearchQA No-Skill B | 完成800位置：552 pass、242 fail、6 API unknown；完整结果与私有备份已保存。 |
| KOR No-Skill A | 完成1000位置：639 pass、201 fail、160截断unknown；聚合JSON已保存。 |
| ALFWorld A | 78位置均完成，但任务目标丢失，整轮隔离；不作为有效基线，不合并B。 |
| ALFWorld B | 暂停核查时49 available、1 unknown、10开放意图、18未启动，共78位置；未评分。主进程已退出，不能按内存挂起直接恢复。 |
| BigCodeBench A | 800预测均完成；516评分闭合（248 pass、267 fail、1 unknown），另有1开放评分意图。未提交基础设施恢复，不报最终分数。 |
| Spreadsheet B | 80题×2、并发2已冻结，0模型调用，尚未启动。 |
| SkillOpt / GEPA 开发先导 | 64训练族/65题＋64选择族/64题、两次更新的协议已准备，0付费；独立环境仍需完成依赖检查。 |

## 恢复位置与约束

- ALF B：`/root/continual-noskill-alf-20260928-b/run`。plan `ac645d23baacef8f77d499e8e8f510a67969c3bd758b99ee6dfa264b1524296f`。先核查全部进程、未闭请求与回执。已完成50位置不覆盖；10个开放意图不能直接重采样，也不能宣称已完整保存可续接的内存状态。其余18位置可在处置明确后按冻结源码继续。
- BCB：`/root/continual-noskill-bcb-20260928-a/run`。唯一开放评分来自Docker清理超时。私有恢复工具及精确hash见 `outputs/continual_eval/result_tools_20260928/README.md`；仅dry-run通过，尚未写入。需要先核查已退出故障容器的清理，再将该位置记录unknown，继续未执行评分，不重新生成800份回答。
- Sheet B：`/root/continual-noskill-sheet-20260928-b/run`。plan `064ef740b596c2282a8e808e207064879360a8b1405e7195f68d59a0884e3ab4`。恢复后再启动；4GiB容器×2，不叠加多个8GiB评分池。
- 学习准备：`/root/continual-learning-bcb-20260928-a`。不得在独立venv依赖资格未通过前付费启动；开发集选择未读No-Skill分数，不能据结果重新筛题。
- 自动结果monitor v2尚未启动，旧接续队列已退出。不要认为离线期间会继续自动采集、评分或上传飞书。

## 本次代码验收

当前评测／SkillOpt／API相关回归共314 passed；官方GEPA及共享CLI独立合测47 passed；不同集合有重叠，不相加当独立测试数。新增ALF长轨迹目标保留、跨回合隔离及Docker执行/清理异常unknown测试经独立review。工程通过不代表真实学习或跨域泛化已有效。

所有冻结源码、意图、回执和历史失败保留；未推送Git、未公开原始任务或模型缓存、未修改Clash。恢复时先重新检查服务器和网络，不因本机合盖推断API失效。
