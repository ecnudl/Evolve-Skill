# 五域持续评测：外部 baseline 接入准备

日期：2026-09-28。状态：**Coding 单阶段 GEPA adapter 已实现并通过官方引擎离线 fixture；未运行付费训练**。
当前流程和结果仍以 [完整流程](current-workflow.md) 与
[结果账本](results-and-lessons.md) 为准。本文件不改变已冻结的 No-Skill 协议。

## 选择与固定来源

除 Sequential SkillOpt，首个外部算法采用 **Sequential GEPA-6000**；
TextGrad 排在后续。简单经验累积可作为额外消融，不冒称原版 Reflexion。

已将 GEPA 官方源码下载到忽略目录
`outputs/continual_eval/baseline_preparation_20260928/gepa/`，固定 commit
`d771eb21b5dd3228bc3f567293d2ccfc423fc900`（提交时间 2026-09-22）。
GEPA 已安装到私有 `gepa-env` 独立 venv（继承只读系统包），未修改共享环境；
仅使用 authored fixture solver/反思响应运行真实官方算法，不调用外部模型。

固定源码入口：

- [优化 API](https://github.com/gepa-ai/gepa/blob/d771eb21b5dd3228bc3f567293d2ccfc423fc900/src/gepa/api.py)。
- [Adapter 与 EvaluationBatch](https://github.com/gepa-ai/gepa/blob/d771eb21b5dd3228bc3f567293d2ccfc423fc900/src/gepa/core/adapter.py)。
- [反思变异](https://github.com/gepa-ai/gepa/blob/d771eb21b5dd3228bc3f567293d2ccfc423fc900/src/gepa/proposer/reflective_mutation/reflective_mutation.py)。
- [引擎与恢复边界](https://github.com/gepa-ai/gepa/blob/d771eb21b5dd3228bc3f567293d2ccfc423fc900/src/gepa/core/engine.py)。
- [批采样器](https://github.com/gepa-ai/gepa/blob/d771eb21b5dd3228bc3f567293d2ccfc423fc900/src/gepa/strategies/batch_sampler.py)。

这是官方算法在本项目统一模型、solver、数据划分和长度预算下的适配，
**不是 GEPA 原论文数值复现**。阶段之间只携带选定 Skill；不将旧领域的
Pareto 分数直接继承到新领域。是否携带旧领域训练样本须单独预登记。

## 已有接口与最小新增边界

现有 `continual_eval` 是冻结评测器，`evolution_enabled=False`，
plan 与 prediction 均记录 `score_feedback_allowed=False`。
`checkpoint` 命令只登记外部 Skill，不训练或授予部署权限。
因此不能把 `host_only/scores` 直接交给 updater，声称已接通训练。

| 新接口 | 输入 | 输出与约束 |
| --- | --- | --- |
| 阶段学习协议 | 父 Skill、当前已见领域、开发 train/selection 家族清单、预算、官方源码 hash | 独立 learning manifest；不得重写评测 plan |
| 开发反馈投影 | 明确授权的开发任务产物与评分回执 | 白名单反馈；不读取 final、校准集或确认集 |
| `GEPAAdapter.evaluate` | `{"skill": text}`、任务与重复位置、是否采集轨迹 | 同一 `backends.solve/score` 的真实结果，完整才构造数值 `EvaluationBatch` |
| `make_reflective_dataset` | 开发输入、产物、允许的评分证据 | `Inputs / Generated Outputs / Feedback`，不序列化整个 private dict |
| 反思模型桥 | 官方原始反思 prompt、稳定逻辑调用身份 | `CachedAPI` 的 GLM-5.3 回执与文本，不增加未声明的 reviewer |
| 阶段导出 | 已完成搜索、开发 selection 结果、父版本 hash | 选定 Skill、学习证据 hash；再调用现有 checkpoint 登记 |

实际新增独立包 `skillopt/continual_learning/`：`contracts.py` 建立授权协议，
`ledger.py` 管理调用预算/回执，`gepa.py` 提供官方算法适配与共享开发执行接口。
没有将优化器塞入现有 generate/score，复用了本仓库回执、哈希和安全执行器。
manifest 同时绑定既有 `runtime_identity()`；真实 Linux manifest 必须在实际
运行环境生成，不能拿 Mac/另一 venv 的 manifest 直接替换环境继续。

`coevolution_v9/learning.py` 的原生 SkillOpt 链可以借鉴，但它绑定
SearchQA 原始 prompt、专用 analyst、评分器和 1–32 条训练记录。
不能把当前五域产物伪装成该接口要求的原生 SearchQA 回执。
五域 SkillOpt 需要薄轨迹适配，保留其 reflect/aggregate/clip/apply 算法。

## GEPA 必须保留什么

第一版使用官方核心 API，候选只有 `skill` 一个可变组件。保留
Pareto 候选选择、轨迹反思变异、父子同 minibatch 比较、完整开发 selection
评估及官方候选选择逻辑。使用默认单父单变异顺序流程，solver 内并发最多 10。
`use_merge` 必须显式冻结；首版可关闭并标明 GEPA 无 merge 适配，不能暗示覆盖
论文所有配置。不得用一次普通反思调用替代整个搜索算法。

solver、基础提示词、输出解析、scorer、执行环境、工具预算均保持与其他方法一致。
仅 Skill 可变，所有方法的 S0 都为空；后续阶段继承上一阶段选定的 Skill，
最终长度不超过 6,000 UTF-8 bytes。
约束须进入提案说明并由宿主复核：超长或字段非法提案应记为无效提案，
不得静默截断、变更 solver 或花额外未登记调用修复。

CachedAPI 当前仅接收 system/user 文本。官方默认 GEPA 反思可用单字符串
调用薄桥接；若后续版本产生多轮/tool 消息，须拒绝不支持的形状，不能随意
拼接改变语义。保留官方提案解析，仅加公开声明的长度约束。

## 开发反馈可以暴露到哪里

训练本身需要开发评分；这不等于允许读取评测真值。新 learning manifest
必须明确记录哪些 development task/family、产物和回执可用于学习。
已有 development No-Skill 产物若被复用，要新建授权投影、列出来源 hash，
保留原始记录的禁止回流标记；不能回填旧协议或称其为新独立运行。

第一版建议给所有 baseline 相同的开发公开输入、实际输出、原生标量评分
与允许的执行诊断；不默认提供答案、完整隐藏测试或 gold workbook。
若选择更强的训练监督，必须明确列字段，并同时给所有方法同等权限。
Research/Rubric 独有新增证据另行归因，不能把开发审计诊断记作自主发现。

GEPA `valset` 是可反复用于选候选的 **development selection**，不是
`verifier_calibration`、一次性 `skill_confirmation`，也不是 `final`。
显式传入非重叠 train/selection，按项目或任务族划分，不能按重复产物随机分。
原生 API 在缺省 valset 时可复用训练数据，不能依赖该默认行为。
S0–S5 最终五域面板只评估冻结 checkpoint，分数不得驱动本轮候选选择。

## 预算：不能只看 metric calls

官方 `max_metric_calls` 是任务评估量，不是 API 次数、token 或总成本。
ALFWorld 一个 episode 可能对应多次请求。首版需在 manifest 预登记：
训练/selection 任务数、重复数、metric calls、反思调用数、每次输出上限、
阶段总 token 预算、环境执行预算及并发。

solver、反思、候选比较和 selection 全部记账；最终五域评测另列。
实际 prompt/completion tokens、逻辑调用、HTTP attempts、缓存命中、执行耗时
分别报告。共享父轨迹的复用须说明，不把重复缓存命中当新增独立样本。
预算耗尽正常保持最后完整的合法候选，不临时提高上限直到出现正收益。

GLM token 统计以实际回执为准。缺失 usage 与重试前消耗不可默认为零；
报告已知小计和未知数量。若声明硬 token 上限，应为在途调用做预留，采用
明确的保守计费上界；无法建立上界时停止/待确认，而不是宣称预算精确相同。
不能把 GEPA callable 的估算成本自动当成 BigModel 实际账单。

已实现第一版使用 `max_reported_tokens` **已报告 token 停止阈值**，不是严格账单
上限：一次调用可能越过阈值，后续不再发送；输出长度与调用总数另外硬限制。
solver 目前串行、每题一次；最小接口不宣称并发 10 或重试随机性已被消除。

## unknown、断点和恢复

GEPA 的 `scores` 是浮点数，本仓库的 `unknown` 不是语义 0。
第一版采取保守策略：遇到不完整父子比较或 selection（API/运行环境未知），
落盘已完成证据，停止该阶段并标记 Pending，不选出伪优胜者。
有确证的程序错误可记 fail；基础设施失败、缺失结果、截断等仍按冻结协议处理。
不能删除不利位置、换题、重复抽样，或仅把成功请求凑成完整 batch。

完整优化器恢复仍待实现；当前只读回放已完成/已终止结果，中断阶段保持 Pending。
没有调用官方 `run_dir` 的自动恢复，更没有读取其 pickle 重新训练。
两层恢复设计如下：

1. **付费请求层**：沿用先 intent 后 receipt。终态回执原样复用；孤立 intent
   不自动再次调用。稳定身份包含学习协议、父/候选 hash、任务/重复、阶段、
   角色和逻辑调用序号，不使用 GEPA 随机 iteration UUID 作唯一 cache key。
2. **优化器层**：固定 commit 保存 `GEPAState` 和可选 adapter_state，但默认
   sampler 的 shuffled IDs、epoch 等以及 selector 的 RNG 是独立运行对象。
   不能仅用相同 seed 重启便声称恢复同一搜索。需通过适配层保存/恢复原生
   sampler 状态及共享 RNG，并核对父选择、任务批次和调用序列。保存点位于
   迭代边界；中断迭代只允许从原始 intent/receipt 重放，不重新选批次。

已终态 unknown 的位置不会因网络恢复自动变为可评；它仍可能阻止该比较。
需要新采样、改 runtime 或评分逻辑时，先形成新版本协议，旧运行保留 Pending。
GEPA 的 pickle 状态仅从本机可信生成、绑定 hash 的私有目录读取，不能加载
第三方或公开下载的任意 checkpoint。

## 付费训练前验收与非目标

先完成现有 No-Skill。当前独立 venv 下 `tests/test_continual_learning_gepa.py`
有 **23 passed，0 skipped**：包括真实官方 GEPA 候选搜索、完成回放、超长拒绝、
开发家族/项目隔离、禁止篡改任务或角色、unknown 保留、调用与 token 阈值、
API 回执错配、无 usage、中断后不重新抽样。未安装可选官方 GEPA 的普通环境
会明确跳过官方引擎测试，不能将跳过计作通过。

离线 smoke 使用四个 authored Coding task metadata：两个开发训练任务、两个
独立开发 selection 任务。官方算法产生两个候选（空父 Skill 与一个新 Skill）；
fixture selection 得分为 0/2 → 2/2，只有一次固定反思响应、**零付费调用**。
这是脚本规定的工程路径，不是模型学习或方法收益。
完整私有产物：`outputs/continual_eval/baseline_preparation_20260928/gepa_smoke_v1/`。
结果 hash：`8d1934e9c838ba025f61b2b6db094480629c24e754ea44175a97908e6ede9cf9`。

可运行命令（依赖上述固定源码与独立 venv 已准备）：

```bash
outputs/continual_eval/baseline_preparation_20260928/gepa-env/bin/python -m pytest -q tests/test_continual_learning_gepa.py
```

`scripts/run_continual_learning.py` 现提供两种方法的共同单阶段入口，默认仅校验：

```bash
python -m scripts.run_continual_learning --manifest MANIFEST.json --panel PANEL.json
python -m scripts.run_continual_learning --manifest MANIFEST.json --panel PANEL.json --execute --output NEW_RUN --repo CREDENTIAL_REPO --gepa-source PINNED_GEPA_REPO
```

第二条仅 GEPA 需要 `--gepa-source`；方法由已封存 manifest 的 `method` 决定。
fixture 必须另外加 `--fixture`，它不能覆盖 natural 协议；Pending 返回退出码 3。
CLI 不会自动建立 manifest、变更数据分区、调用 Research 或登记部署权限。
CLI 的两条实际算法 fixture 路径均已执行；与 GEPA 和 native SkillOpt 测试一起
合测为 **47 passed，0 skipped**（独立 GEPA 环境，1.07 秒）。

Linux 准备环境为 `/root/continual-learning-env-20260928/`，其 `gepa-source/`
固定同一官方 commit，独立 venv 继承运行依赖但不修改共享 conda 环境。
环境准备没有模型调用，也没有冻结真实训练 manifest；真实运行需另建源码快照。

测试还发现官方 proposer 可以吞掉反思异常并跳过该次更新；适配层现以 Pending
锁存失败，阻止进一步付费并在官方返回后再次核查，不能把 API 失败误报完成。
官方结果的整数键/tuple 已在落盘前标准化，保证完成后回放一致。

仍待真实开发链路验收、完整五域训练与优化器精确恢复。超长候选当前会使该
阶段 Pending、保留父 Skill，而非自动修复。数据不足、预算边界或基础设施失败
也可能保持 Pending。正式任务数与预算在付费开跑前冻结。

TextGrad 仍未接入。它需要保留原生 Variable/backward/TGD；普通反思不等于
TextGrad。Reflexion 的原始同任务重试/memory 机制与冻结 Skill 跨任务测评不同；
全局压缩经验只能命名为 Reflexion-inspired，不能作为原论文复现。

所有方法若需要历史域 replay，应匹配可访问数据与计算预算并单独报告；
只给 Ours 旧域验证面板会混淆方法收益与额外监督。当前研究目标仍是已见/相似
机制任务的收益与其他任务的回归控制，不预设每经过一个阶段分数必然单调提高。
