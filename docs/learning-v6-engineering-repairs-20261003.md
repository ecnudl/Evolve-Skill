# Learning v6：异常处理修复与发布边界（2026-10-03）

这是工程修复，不是新方法效果实验。所有新增复现使用离线假API、固定产物或模拟进程边界，0真实模型调用；未修改Linux E源码、环境、进程、协议或历史结果。E仍为序列v3／learning v5。

## 再次确认的问题与修复

| 问题 | 旧行为的离线复现 | 显式v6行为 |
| --- | --- | --- |
| 容器清理未确认仍继续 | v5出现`run → rm失败 → run → rm`；整阶段末handoff才阻止向后交接 | 保存证据后立即Pending，禁止下一题、反思和评分；Spreadsheet同题剩余case也不再执行，记为未执行；缓存回放同样阻断 |
| 过滤响应误重试 | v2客户端收到`sensitive/content_filter`后EOF、ReadError或超时，仍提交第二次请求 | v3客户端保留已观察到的安全终止元数据，过滤后绝不重试，清空过滤正文；正常网络失败仍按原次数上限重试 |
| 首题过滤阻断正常题 | 完整HTTP200／模型匹配的过滤回复使health失败，下一道题不提交 | 当前题仍unknown且不重试；只放行后续不同任务的连接健康检查；不完整或错模型回复仍保守阻断 |
| 未知成本上限越界 | v5合法重试让未知尝试63→65，终态仍可completed | 每逻辑调用前按冻结`max_retries+1`预留；余额不足不写intent、不发请求；越界回执完整保留并阻断终态 |
| 新版本整合回放 | v6初稿在`Ledger(..., None)`读取API属性，终态回放失败 | 从已有sealed `model_service.json`只读恢复并将其纳入结果绑定；零调用Pending也可回放，不重新请求API |

预留未知成本是保守保护：生产最多3次HTTP尝试时，已累计62个未知尝试即停止新调用，因为不能保证下一调用最多只新增2个。它不是把未知token记为0，也不意味着已精确知道总token成本。

## 输入、输出和代码入口

输入仍是冻结的开发面板、train/selection任务族、父Skill、预算和运行环境；仅显式选择`continual-learning-v6`与`POLICY_V6`才启用修复。v6仍仅支持该SkillOpt适配器，不把GEPA标记为已验证支持。

- [recovery.py](../skillopt/continual_learning/recovery.py)：`HARDENED_VERSION`／`POLICY_V6`绑定`closed_delivery_error_v3`。
- [api.py](../skillopt/validator_pilot/api.py)：流事件、过滤和健康检查分离；service参与缓存身份。
- [gepa.py](../skillopt/continual_learning/gepa.py)：SkillOpt复用的执行Adapter，在未知排除／反馈投影前检查清理证据；[backends.py](../skillopt/continual_eval/backends.py)只在v6内部标记下提前停止工作簿case。
- [ledger.py](../skillopt/continual_learning/ledger.py)：服务绑定、调用前额度预留、终态阻断、只读回放。
- [run_continual_learning.py](../scripts/run_continual_learning.py)：现有单阶段入口支持显式v6及离线fixture；输出仍为候选／父Skill、completed或Pending、费用与绑定回执，不新增部署授权。

新manifest必须由当前源码生成并使用新输出目录。现有E启动脚本和序列v3配置继续指向旧v5，**没有自动升级、更没有启动一轮v6正式实验**。后续五阶段队列如启用v6，须另立序列配置并重新冻结，不修改E。

## 验证命令

```bash
python -m pytest -q tests/test_validator_delivery_v3.py \
  tests/test_continual_learning_budget_v6.py \
  tests/test_continual_learning_cleanup_v6.py
```

其中`test_v6_offline_cli_smoke`实际调用单阶段CLI并重复回放；其他控制包括旧v5缺陷的保留对照、过滤后真实async deadline、清理失败的零后续执行、未知成本边界、普通unknown可继续，以及零调用Pending回放。旧v1–v5测试一起回归，不能用新源码强行恢复旧哈希绑定实验。

本次验证结果：三个新边界文件 **68 passed**；研究离线大回归 **4,532 passed / 15 skipped**；上游回归 **1,519 passed / 6 skipped**；文档发布边界 **17 passed**，MkDocs严格构建通过。测试集合有重叠，不把这些数字相加；研究套件15个跳过均因当前环境未安装可选pinned GEPA，另以`-rs`复核，不计为通过。默认skill环境未安装MkDocs，文档测试先显示skip，随后在独立文档环境实际运行通过。新增API边界测试已加入CI；这些结果均不代表v6已完成真实模型实验。

提交前另从Git暂存区导出干净源码树，关键回归 **364 passed**、文档边界 **17 passed**，确认不依赖未跟踪文件；修改的Python文件Ruff检查通过。没有将私有缓存、密钥或原始benchmark载荷加入发布。

## E已有结果是否受影响？

E随后自然终止，[18:13终态](results/skillopt-generalization-e-final-20261003.json)完整学习4/5、全域矩阵闭合5/5，只有S1更新、后续均携同一Skill。这个运行结果与本地v6修复相互独立；详细成绩和费用见[E报告](skillopt-generalization-e-20261003.md)。

提交前再查全部五阶段：学习1,928逻辑调用＝1,928 HTTP，1,926次普通终止、2次过滤单次终止，未知成本尝试合计2；1,535份学习执行／评分记录中未见清理未确认，69个冻结源码哈希无变化。这里的记录数不是独立任务数。未见本次修复的边界缺陷在E实际触发，不覆盖或重算E成绩。

[17:53只读快照](results/skillopt-generalization-e-progress-20261003.json)记录完整学习3/5、矩阵闭合4/5：只有S1更新，S2/S3候选超长而无更新，S4优化器未完整完成而Pending，S5无终态。S1–S4没有学习端HTTP重试，S3两次过滤均单次终止；未知成本最多2次。所查清理回执未发现未确认，69个冻结源码文件哈希一致。这里没有证据说明上述边界bug已经污染E的已完成成绩，不将这些成绩作废；也不能把未触发当作旧实现没有bug。

## 本次不改变的研究规则

净unknown偏移＋共同已知位置的选择策略仍原样保留，包括其局限。100位置的人工反例中，父`25 pass / 50 fail / 25 unknown`，候选`1 pass / 74 fail / 25 unknown`，双方已知位置交集50、净unknown变化0，门控仍可因交集内`0→1`而接受。它是协议方法学风险，不是本次修复的工程bug，更不是E上已观察到的效果。

S1实际选择的65位置全部已知，不受这个反例影响；不能据此声称后续任意unknown分布都安全。改变选择分母、unknown风险约束、Skill长度或更新策略都应另开研究协议。本次也不修剪超长候选、不调整6000字节上限、不改oracle或追改历史评分。
