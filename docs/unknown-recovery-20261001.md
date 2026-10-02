# 10/1 完整基线 unknown 的定向修复与重测

本轮对象是[新完整五域 No-Skill 基线](results/noskill-fivebench-long-20261001.json)，不是此前 4096/8192 的截断恢复链。模型原配置为 BigModel GLM-5.3、low、65536、流式 read300/wall1800；数据均为历史曝光 development。

**当前应用户要求暂停**：已持久化停止派发标志，在途请求写完回执后退出。KOR length暂停快照为1/10完成pass、1在途；不把快照当终态。[断点与恢复步骤](unknown-recovery-pause-20261001.md)。

## 处理边界

- 原任务、源码、调用、产物及评分全部保留；新诊断不能回填成统一预算基线。
- 固定程序的执行未知优先零 API 重放；完整语义失败不重复生成。
- KOR 的 10 个 closed length 位置独立允许一次 131072/wall3600 诊断；1 个 closed network_error 位置允许一次原预算诊断。每个逻辑生成沿用最多 3 次传输尝试，不做“直到成功”的补抽。
- SearchQA 的 6 个敏感过滤位置仅归档为不可用，不修改措辞绕过过滤、不重新提交。
- 原生容器使用共享锁、原镜像与隔离参数；未闭合意图不得自动重跑，清理未确认时停止后续提交。无 Docker 时不在宿主执行生成代码。

## 已完成：工作簿固定代码诊断

从完整 80 题×2 面板选择 7 个可交付代码但无工作簿的位置，来自 6 道题；另外 1 个模型截断不混入该零 API 实验。原代码、公开输入、依赖镜像均不变，只增加受限异常位置记录。

| 固定代码重放结果 | 位置数 | 能说明什么 |
| --- | ---: | --- |
| 运行异常复现 | 5 | TypeError 1、ValueError 1、AttributeError 2、FileNotFoundError 1；均定位到生成代码执行阶段，根因仍需结合契约与对应代码检查 |
| 正常返回但缺少 output.xlsx | 1 | 确认产物交付失败，不是成功完成 |
| 旧提取代码语法错误 | 1 | 静态 compile 即失败；随后发现旧围栏提取器取错文本，不能归咎于模型没有交付 Python |

本轮没有修复或改写模型答案，没有新增语义成功；旧 unknown 标签保持不变。6 个容器累计 32.936586 秒、0 API、0 清理未确认。[独立报告](results/unknown-sheet-native-replay-20261001.json)。异常类型和行号本身不足以断言所有责任均在模型。

**实际发现的适配 bug**：语法错误位置的原始完整回复含 Excel 围栏、解释文字和 Python 围栏。旧 `_code` 正则从前一个围栏的关闭行匹配到后一个开启行，错把解释文字提取为代码。应在新协议使用逐行围栏解析后重新提取原回复，不能通过模型重新作答来掩盖解析问题；该修复与重测仍在进行。原运行代码未经改写。

## 已完成：BCB 与 KOR 通信恢复

| 诊断 | 结果 | 新增成本 | 限制 |
| --- | --- | --- | --- |
| BCB 原唯一 native_timeout，固定原代码重放 | 官方 SDK 返回 fail | 0 API；1 容器，242.974812 秒；清理确认 | traceback 位于 multiprocessing.Pool 的 terminate/join 路径并触发 SDK TimeoutException，与已知 guard 兼容风险一致，不能直接认定纯模型推理错误 |
| KOR 唯一 closed network_error，原预算一次机会 | 完整交付，官方评分 fail | 1 调用/1 HTTP，1,403 tokens；1 容器，2.04958 秒；清理确认 | 消除了这次新诊断的交付未知，没有提升成功数；原请求 usage 缺失，不能声称新旧总成本完整 |

[BCB 回执](results/unknown-bcb-native-replay-20261001.json) · [KOR 回执](results/unknown-kor-network-recovery-20261001.json)。原基线全部保持不变；这两个 fail 不继续补抽。

## 正在验证 / 尚未完成

- KOR：实际响应已确认，10 个截断位置的独立恢复已在 Linux 单并发后台启动；不是 1000 位置统一重跑。
- Spreadsheet 兼容性：新增 v6 的极窄数值比较视图，拟处理已确认的内建格式 30 数值被解析成日期的问题。只在原数值与引擎导出 binary64 一致、没有格式观察行为时成立；不修改公式或缓存，不把空字符串与空白、错误常量与公式混同。工程测试已通过，新的真实引擎资格与完整 160 位置对照仍待完成，不能沿用 v5 授权。

**v6 首轮真实资格被拒绝**：[A 资格回执](results/unknown-sheet-v6-qualification-a-20261001.json)为 18/20，旧 17 项及格式观察拒绝控制通过，`format30_correct` 和 `format30_wrong` 均在比较视图校验被拒绝。18 容器/48.235216秒/0 API/0清理未确认；尚未启动完整 160 位置评分。保留该失败资格，若确认实现缺陷，必须另立源码版本及资格目录，不能修改控制预期来通过。

## 新入口及 review

- [交付恢复](../scripts/recover_full_delivery_unknowns.py)：`prepare/run/report`；必须使用原冻结包的 `PYTHONPATH` 和原解释器。
- [零 API 原生重放](../scripts/replay_native_unknowns.py)：`prepare/check/preflight/run`；Sheet 诊断调用[容器内适配器](../scripts/native_unknown_worker.py)，BCB 保留原评分器。
- [数值比较视图 v6](../skillopt/continual_eval/sheet_recalc_v6.py)：独立版本，不修改已冻结 v5。

独立 review 已修复：真实清理失败仅有 reason 字段时未阻止继续调用；只读 readiness 意外启动未计成本容器；最后一项清理失败仍报告完成；ZIP/XML 在进入 openpyxl 前缺少完整预检查。相关新旧离线测试 **317 passed**；这是工程检查，不是方法效果或跨域泛化证据。

暂停收尾时另一次广泛回归结束为 **3750 passed / 6 failed / 9 skipped**。6项失败均为资格源码身份变化拒绝，测试与编辑同时发生；尚待静止源码下复核，不称全量通过。详情及待办见暂停交接。

当前 Linux 后台运行，Mac 合盖不应终止已脱离本机会话的进程；恢复后仍需以实际回执确认完成，不能由进程消失推断成功。
