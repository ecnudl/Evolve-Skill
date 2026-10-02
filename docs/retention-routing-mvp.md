# 固定完整 Skill 的来源收益保留与路由诊断

本实验检查：对同一份已经训练完成的 SearchQA Skill，只改变是否注入它，能否保留来源任务收益，同时减少不适用任务上的干扰。它是 **fixed-policy / shared-draw 诊断**，不是新的 Skill 自动进化算法，也不授予经过认证的 Validation Gate Commit。

## 两个相互配合的实验目录

| 实验 | 工作 | 本轮推荐目录 |
|---|---|---|
| C：来源收益复核 | 在新选取的 SearchQA 样本上执行 Base、完整 Skill，以及默认启用的 extractive 消融 | `outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix` |
| D：固定 Skill 路由 | 在 C 的同一批来源输入和独立合成控制题上封存路由；执行控制题的 Base/full 两臂；组合结果并分析 | `outputs/scope_evolution_v2/retention_routing_gpt55_20260908_paced` |

D 的所有启用策略使用 **同一份完整 Skill 文本**，不能把 extractive 消融当成完整 Skill 的替代品。未启用时使用历史 `initial.md`，不是重新定义的空系统提示。

固定完整 Skill 来自 `outputs/repro_searchqa/full_gpt55_seed42/best_skill.md`，SHA256 为：

```text
6aad066e67088cb4d814f8452908f092ca5a9f45ab44fcb7f65deb752fc5d17c
```

## 数据与边界

- C 默认预留 calibration 128 题、holdout 256 题。ID 和问题指纹由同一份 manifest 预先确定；prepare 不物化 holdout 正文及答案。
- D 每个 split 有 48 道控制题：跨域同关系证据机制正例 16 题、near-miss 16 题、无关任务 16 题。
- 正例分布在 coding、spreadsheet、rule reasoning 的文档问答中。Near-miss 有 8 道 SearchQA/trivia 来源外观题和 8 道跨域题，检查完整姓名、指定原文、直接证据与同源镜像等边界。无关题包含来源和目标领域外观。
- 这些是合成的领域文档 QA，不是实际修改代码、操作表格或执行规则系统的工具任务。单个 domain / near-miss 子类样本很少。
- 完整 Skill 本身已经包含“需要时保留完整名称”等限定，因此控制题不预设它一定产生退化。
- 路由只接收真实 question/context，使用与目标完全相同的 SearchQA `_build_user` 和 6,000 字符、`[DOC]` 边界截断。不会收到 gold、domain/group/mechanism 元标签或目标模型结果。
- 控制题要求唯一 `<answer>...</answer>`；仅允许 Unicode NFC 与空白规范化，不删除姓名词、冠词或标点，也不忽略大小写。

## 预先固定的策略与指标

| 项目 | 固定值或定义 |
|---|---|
| Base | 从不注入完整 Skill |
| Unconditional | 所有输入都注入完整 Skill |
| Domain-only | 输入式 GPT 路由的 `domain_score >= 0.70` |
| Mechanism | 输入式 GPT 路由的 `mechanism_score >= 0.60` |
| 来源覆盖率目标 | 至少 80% |
| 来源净增益保留目标 | 至少 80% |

RCE scope 是根据冻结完整 Skill 的原文，由人预先指定的机制描述；不是从控制题标签、校准得分或 holdout 结果自动学出的规则。它不排除“模型已有先验、能够直接回答”的来源问题，也不把完整姓名请求一概列为不适用。

来源净增益保留率定义为：

```text
(路由策略正确题数 − Base 正确题数)
÷ (完整 Skill 正确题数 − Base 正确题数)
```

分母不为正时记为 `null / N/A`，不能假定来源收益成立。比例不截断：负值与大于 100% 的值都保留。报告同时列出完整 Skill 的错→对和对→错题数，以及路由保留的改善题、仍使用的退化题、阻止的退化题。全部 fallback 的覆盖率为零，不能借此满足目标。

附表另有四个预设 **mechanism score 阈值**：`0.25, 0.50, 0.75, 0.90`。对于每个阈值，先在尚无目标结果的完整输入集合上计算其启用数 K，再分别取 mechanism、domain 和确定性 ID-hash 随机排序的前 K 项。

这些数值 **不是 25%/50%/75%/90% 固定覆盖率，也不是另一个实验的 10%/25%/50%/75% 覆盖率计划**。K 只在完整预注册集合上相等；来源/near-miss 等子群内部，或者排除 API 失败以后，不保证相同覆盖率。四组结果全部报告，不根据结果挑一个阈值来替换主部署策略。

## 环境与依赖

从仓库根目录运行，使用已有 `skill` conda 环境。需要：

- 仓库 `.env` 中现有 Freerouter URL、API key，以及共享或角色专用的 session ID；不要将这些值打印或提交。
- 历史完整 Skill 和 `skillopt/envs/searchqa/skills/initial.md` 的原始快照及正确哈希。
- 本地 Hugging Face SearchQA Arrow 缓存；默认路径由 [source_data.py](../skillopt/scope_evolution_v2/source_data.py) 的 `DEFAULT_CACHE` 指定。C prepare 会将缓存位置及内容哈希写入 manifest。
- source manifest/protocol、Skill 快照、控制题、路由、分析计划及其哈希。仅复制两个结果 CSV 或单个 Skill 文件不足以完整复现。

推荐通过 `scripts/paced_scope_mvp.py` 启动真实 API 阶段：`--entry source` 转交 `scripts/source_retention_session_mvp.py`，`--entry routing` 转交 `scripts/retention_routing_mvp.py`。这两个内层入口会在任何 SkillOpt/model 导入之前加载现有 session ID。不要绕过 C 的 session launcher 直接启动旧 CLI。它们不创建新 session ID，也不更改 Clash 路由。

`--min-interval 2` 在单个进程内将 logical backend 调用的开始间隔限制为至少 2 秒；并发上限仍由内层 `--workers` 控制，默认 6。原请求参数、内部 retry/backoff 保持不变，**不是每个 wire retry 的限速，也不保证真实 HTTP 请求不超过每分钟 30 次或绝不出现 429**。不要通过启动多个并行进程抵消节流。

节流 launcher 只是临时 transport 包装，不自动 prepare、不写 transport amendment、不修改实验产物。启用它时，操作者需要在首次目标执行前另行记录并冻结 transport amendment（入口、间隔、脚本哈希和变更原因），保留核心协议、manifest 与 Skill 哈希不变。

## 精确阶段顺序

以下命令均以前台方式运行，等待上一条结束再执行下一条。尤其 **不能并行运行 C 的目标执行和 D 对同一 split 的路由**。路由程序会拒绝在该 split 已存在单题目标缓存、完整结果或控制目标启动标记后新建 masks；这不是允许与尚未落缓存的进行中请求并发的承诺。

先选定独立目录。下面显式使用新的 paced D 目录；它不是旧内层 CLI 的默认目录：

```bash
SKILLOPT_SOURCE_RUN=outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix
SKILLOPT_ROUTING_RUN=outputs/scope_evolution_v2/retention_routing_gpt55_20260908_paced
```

### 1. C prepare：来源 manifest、calibration 和 Skill 快照

```bash
conda run --no-capture-output -n skill python scripts/source_retention_session_mvp.py \
  --phase prepare --out "$SKILLOPT_SOURCE_RUN"
```

默认 C 包含 base/full/extractive 三臂。若确实需要仅 base/full，必须在最初 prepare 就使用 `--without-extractive`，之后每次 C 调用保持相同设置；不要在运行中改变 arm 列表。

### 2. D prepare，并冻结独立分析计划

```bash
conda run --no-capture-output -n skill python scripts/retention_routing_mvp.py \
  --phase prepare --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/analyze_retention_routing.py \
  --run-dir "$SKILLOPT_ROUTING_RUN" --freeze-plan
```

`--freeze-plan` 必须在 D prepare 之后、任何 holdout 物化/路由之前运行。推荐像本轮一样，在所有目标执行之前就完成它。它固定分析脚本哈希、比较对象、群组、5,000 次任务级配对 bootstrap 及随机种子；最终分析不能随意改脚本或选择更有利的比较。

### 3. 先封存 calibration 路由，再执行两组目标

```bash
conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry routing --min-interval 2 \
  --phase route-calibration --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry source --min-interval 2 \
  --phase pilot --out "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry routing --min-interval 2 \
  --phase control-calibration --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"
```

`route-calibration` 默认路由 128 道来源题和 48 道控制题，先写路由分数、正常部署 masks、四组等 K 诊断 masks 及独立 seal，然后才允许目标执行。C pilot 结束并完成其所有预注册 arm 后会产生 `frozen_source_protocol.json`。

### 4. 冻结 D；决定是否值得继续，而不是悄悄改阈值

```bash
conda run --no-capture-output -n skill python scripts/retention_routing_mvp.py \
  --phase freeze --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"
```

该阶段要求完整 C freeze、正确 real/mock 模式以及完整 calibration 结果，重新校验协议、输入、Skill、路由及结果哈希。它不根据 calibration 调整 scope 或阈值，不授予 Commit。若没有来源收益、跨域正例满分或样本不可识别，可以在此如实停止；不要为追求正结果扩大 holdout 或改本轮定义。

可选：在打开 holdout 前查看已完成的 calibration 报告：

```bash
conda run --no-capture-output -n skill python scripts/retention_routing_mvp.py \
  --phase report --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/analyze_retention_routing.py \
  --run-dir "$SKILLOPT_ROUTING_RUN" --split calibration --write
```

### 5. 先封存 holdout 路由，再执行 holdout 目标

```bash
conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry routing --min-interval 2 \
  --phase route-test --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry source --min-interval 2 \
  --phase test --out "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry routing --min-interval 2 \
  --phase control-test --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"
```

`route-test` 才物化预留的 256 道来源 holdout 和 48 道控制 holdout，并在任何对应目标结果之前封存 masks。之后 C test 物化的是同一份来源 manifest 的同一组样本，不是第二份独立评测。

### 6. 固定报告与配对分析

```bash
conda run --no-capture-output -n skill python scripts/retention_routing_mvp.py \
  --phase report --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/analyze_retention_routing.py \
  --run-dir "$SKILLOPT_ROUTING_RUN" --split holdout --write
```

完整 Skill 和 Base 对每道题各执行一次，各路由策略通过预先冻结的 masks 选择这两次实际输出之一。它是共享抽样结果的配对诊断，不是每个策略又进行了独立目标运行。

## 失败、恢复与重跑

- 本轮旧 D 目录 `retention_routing_gpt55_20260908` 的首个 calibration 路由批次因 HTTP 429 自动中止，尚未 seal、未执行目标；旧成功和失败缓存全部保留。新分支 `retention_routing_gpt55_20260908_paced` 重新执行完整 176 个 calibration 路由，不拼接旧分支的部分路由。C 的 `_sessionfix` 目录尚无目标调用，继续使用已 prepare 的原 manifest / source protocol / Skill 快照，仅追加首次目标执行前的 transport amendment；无需重新抽样。
- D 的每个新路由/控制批次先确认首条请求成功，再展开最多 6 并发。连续三条完成请求的 API/路由失败会中止；已在途请求仍可能完成并留下缓存。
- API 失败和模型答错分开保存，失败的目标调用 `hard=None`。配对分析使用 Base/full 共同成功的同一组 ID，报告单臂失败数与排除 ID；排除不保证无偏。
- 路由格式错误会 abstain；首条失败或连续失败会触发 fail-fast。不能把不可用的网关误报成方法退化。
- 终止失败缓存不会自动删除或重新调用。批次失败后先检查连通、session、权限、服务状态；需要重新调用时由操作者明确建立新运行分支/目录，并记录原因，不覆写失败证据。
- 在相同目录恢复会复用已缓存请求和冻结 masks，不会重新挑 scope。缓存成功也不能证明服务此刻仍健康。
- 代码、配置、Skill 或数据哈希变化会拒绝继续原运行。修订实验请建立新目录，不绕过校验、不手工修改已冻结 JSON。
- 新 C manifest 会排除已知运行及此前 manifest 预留的来源 ID/问题指纹。因此即便 seed 相同，新目录也不一定得到相同样本。复现原抽样需要保留原 manifest 和完全一致的 Arrow 缓存；复用原 API 缓存不算新的独立模型重复实验。

## 结果应该如何表述

分别报告来源、跨域正例、来源外观 near-miss、跨域 near-miss、unrelated；不要把公开来源 QA 与合成控制题的 pooled 均分当作主要成功证据。

D 的来源结果与 C 完全共享原始 observations，不能把它们当两次独立复现。C 默认采用三臂共同成功分母，D 采用 Base/full 两臂共同成功分母；如果 extractive 有独有 API 错误，两者小数可能不同，应核对分母后解释。

统计区间描述固定 Skill、当前模型服务和当前样本上的配对差异；没有多比较、模型种子或服务漂移校正。相同 masks 导致的零差异/零区间，不证明未知任务无副作用。稀疏 domain / near-miss 子类、有限控制任务、不确定来源收益都需要原样披露。

即使覆盖率和收益保留目标都达到，也只能称为这一固定路由诊断的观察结果；不能自动宣称完成 Skill 自进化、成功扩大跨域 scope，或得到经过认证的安全 Gate。
