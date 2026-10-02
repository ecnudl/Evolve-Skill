# E：固定章节消融的来源收益归因

E 检查完整 SearchQA Skill 的收益对两个预先指定章节组的依赖程度。它在 C 的**同一批 256 道 holdout** 上复用 C 已有的 Base/full 输出，仅新增两个删除版 Skill 的执行，不进行 E calibration，也不根据 holdout 修改消融内容。

这是章节级消融，不是干净的机制因果拆解，也不是第二次独立来源复现。

## 固定的四个 arm

| Arm | 内容 | 目标轨迹来源 | 字符数 |
|---|---|---|---:|
| `base` | 原历史 `initial.md`，不是新造的空系统提示 | 复用 C | 104 |
| `full` | 原历史 `best_skill.md` 完整文本 | 复用 C | 7,904 |
| `without_evidence_section` | 仅删除 `## Extractive / Trivia Evidence Selection` 到下一标题之前的完整章节 | E 新执行 | 5,680 |
| `without_answer_form_sections` | 删除 `## Concise clue-answering rules` 完整章节，以及包含起止标记的整个 SLOW_UPDATE 块 | E 新执行 | 2,749 |

两个删除版都保留 `## Jeopardy-Style Wordplay` 和 `## Final Answer Formatting`，后者的 `<answer>...</answer>` 输出规则不删除。第二个删除版还保留完整 Evidence Selection 章节。删除仅拼接原文剩余片段，不改写规则、不增补提示、不清理保留下来的空白。

历史 full SHA256 必须精确等于：

```text
6aad066e67088cb4d814f8452908f092ca5a9f45ab44fcb7f65deb752fc5d17c
```

标题及 SLOW_UPDATE 起止标记必须唯一；快照哈希、章节定义、代码、五组比较、bootstrap 参数和来源 manifest 已写入 [冻结协议](../outputs/scope_evolution_v2/source_attribution_gpt55_20260908/attribution_protocol.json)，协议另有独立 seal。E 在查看 C calibration 后、打开 source / D holdout 前注册；不能将它描述为在所有来源数据之前提出的完全盲消融。

## 环境与目录

在仓库根目录使用 `skill` conda 环境。保留已有 `.env` 中的 Freerouter 配置和现有 session ID，不打印或提交凭证。

```bash
SKILLOPT_SOURCE_RUN=outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix
SKILLOPT_ROUTING_RUN=outputs/scope_evolution_v2/retention_routing_gpt55_20260908_paced
SKILLOPT_ATTRIBUTION_RUN=outputs/scope_evolution_v2/source_attribution_gpt55_20260908
```

本轮模型是 `gpt-5.5`，六个 worker，单进程 logical backend 请求开始间隔至少 2 秒。使用原 SearchQA system/user builder、6,000 字符的上下文截断和原 evaluator。请求的 completion 上限为 16,384，兼容后端实际 cap 为 8,000；温度沿用服务默认值。

E CLI 自身先加载**现有** session 环境，再导入后端并装配 `paced_backend(backend, 2.0)`。真实运行应使用下面的 CLI，不要在已导入模型的临时进程中直接调用 `run_phase`，也不需要再套一层 pacing。内部 retry/backoff 没有逐次节流，因此 2 秒逻辑间隔不保证真实 HTTP 请求速率或绝不出现 429。

完整复现依赖 C 的 source protocol / manifest / freeze / Skill 快照 / calibration 和 holdout 产物，以及一致的本地 Hugging Face Arrow 缓存。E 的 report 也会重新验证来源与本地缓存；仅复制 E 的 summary 文件不足以重新核验。

## 严格阶段顺序

以下均以前台方式串行运行，等待上一阶段成功返回。C/D 完整流程见 [固定路由实验说明](retention-routing-mvp.md)。E 不负责启动 C/D，也不自动推进所有阶段。

### 1. 先完成 C calibration，再冻结 E

C 必须已经 prepare、完成其全部预注册 calibration arm，并生成 `frozen_source_protocol.json`。D 的 calibration 路由应在 C calibration 目标执行之前完成；这一先后关系由 C/D 流程控制。

在 source / D holdout 尚未打开时执行：

```bash
conda run --no-capture-output -n skill python scripts/source_attribution_mvp.py \
  --phase prepare --out "$SKILLOPT_ATTRIBUTION_RUN" \
  --source-dir "$SKILLOPT_SOURCE_RUN" --routing-dir "$SKILLOPT_ROUTING_RUN"
```

本轮已经成功完成此阶段。prepare 只读取来源协议、manifest、freeze、历史 Skill 和缓存请求的 split 元信息，校验既有 calibration 产物哈希；不物化或查看 holdout 正文/答案，不调用 API。它冻结四份 Skill 快照、`attribution_protocol.json` 与 `attribution_seal.json`。

新的注册会检查 source / D 已物化数据、holdout 路由、目标结果/标记及 source 单题请求 metadata；若 holdout 已打开则拒绝。该检查不是跨进程事务锁，所以不能与 D route-test 同时启动。

### 2. D 先封存 holdout 路由，再由 C 执行原 holdout

在 D 已完成其 calibration freeze 且 E prepare 已成功之后：

```bash
conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry routing --min-interval 2 --phase route-test \
  --out "$SKILLOPT_ROUTING_RUN" --source-dir "$SKILLOPT_SOURCE_RUN"

conda run --no-capture-output -n skill python scripts/paced_scope_mvp.py \
  --entry source --min-interval 2 --phase test --out "$SKILLOPT_SOURCE_RUN"
```

D route-test 首先封存 masks，之后才允许 C 的对应目标输出。C test 必须完成原有全部 arm（本轮 base/full/extractive），生成完整 `holdout_summary.json` 和逐臂 JSONL。E 不会替 C 补跑缺失 arm，也不会重新生成 Base/full。

如果本轮还要执行 D control-test，按既定 C/D 流程串行完成即可；它不是 E 的数据依赖。不要并行启动 E、C 或 D 的真实 API 批次来叠加请求速率。

### 3. 显式执行 E 的两种删除版

```bash
conda run --no-capture-output -n skill python scripts/source_attribution_mvp.py \
  --phase test --out "$SKILLOPT_ATTRIBUTION_RUN" \
  --source-dir "$SKILLOPT_SOURCE_RUN" --routing-dir "$SKILLOPT_ROUTING_RUN"
```

E 先验证自己的冻结依赖、C 的完整 holdout 和真实/测试替身模式；再从同一 manifest/cache 核对 C 的 holdout payload。原 C JSONL 会逐题复核 ID、问题、gold、Skill hash、API 状态与原 evaluator 得分。E 将 C 被借用产物的完整文件哈希写入 `borrowed_source_holdout_artifacts.json`，但不重新调用这两臂。

随后依固定顺序执行两个 lesion，各 256 题，最多新增 **512 个 logical target 请求**；服务内部重试不计作新的独立任务。模型只收到原问题/上下文及对应 Skill，gold 只用于执行后的评分。

### 4. 查看或重新核验报告

test 完成时自动写报告。需要重新核验已有结果时：

```bash
conda run --no-capture-output -n skill python scripts/source_attribution_mvp.py \
  --phase report --out "$SKILLOPT_ATTRIBUTION_RUN" \
  --source-dir "$SKILLOPT_SOURCE_RUN" --routing-dir "$SKILLOPT_ROUTING_RUN"
```

report 不调用模型，不会补跑缺失数据；它要求两条 lesion JSONL 已完整存在，并重新校验冻结依赖和保存的得分。输出包括：

- `holdout_report.md`：四臂 EM/F1、API 错误数、主要配对差异。
- `holdout_summary.json`：EM/F1 差异与置信区间、每组 wins/losses 及对应题目 ID、共同成功 ID、排除 ID、Skill 与借用文件哈希。
- `searchqa_rollouts/holdout/<lesion>/results.jsonl`：两个新增 arm 的原始答案、评分和请求 provenance。
- `calls/`：E 的成功与失败单题 API 缓存；C 原始调用仍保留在 C 目录。

## 如何读 `vs_base` 和 `vs_full`

所有主指标与五组比较都使用 **Base、full、两个 lesion 四臂共同 API 成功的同一组 ID**。API 错误不是答错，不计为 0；同时报告单臂错误和排除 ID。排除可能有偏，不能只报告自己的成功分母。

| 比较字段 | 含义 | 差值方向 |
|---|---|---|
| `vs_base.full` | 完整 Skill 相对 Base 的来源表现 | full − Base |
| `vs_base.<lesion>` | 删除版相对 Base 是否仍有收益 | lesion − Base |
| `vs_full.<lesion>` | 删除这组章节相对完整 Skill 的表现变化 | lesion − full |

例如 `vs_full` 为负，表示删除版比完整 Skill 弱；如果差异区间支持负值，说明在本轮设定中保留该章节组与更好的表现相联系。为正则表示删除版更好，不能继续预设被删规则都是有益的。

wins 是“reference 错、candidate 对”，losses 是“reference 对、candidate 错”。所以 `vs_full` 的 losses 就是完整 Skill 原本答对、删除后答错的题。需要结合逐题答案检查差异属于实体选择、答案粒度、字面形式、记忆实例还是其他行为。

区间使用固定种子 `20260908`、5,000 次原始任务级配对 bootstrap，EM 与 F1 都计算；五组比较固定报告，不根据结果择优。实现为计算 `vs_full` 使用临时 reference lookup 别名，不改写实际 row 的 arm 或 Skill hash。

如果删除版仍优于 Base，但弱于 full，可以说被删章节组可能贡献了完整 Skill 的部分收益；不能据此宣称它是唯一机制。删除后无显著变化也不等于章节毫无作用：可能有规则冗余、相互作用、样本不足或调用波动。

C 原报告默认采用三臂共同成功分母，E 采用四臂共同成功分母，因此即便复用同一条 Base/full 输出，headline 小数仍可能因排除 ID 不同而变化。不能把这类分母变化解释成模型重新执行后的性能漂移。

## 解释边界

- “答案形式章节组”同时删除 SLOW_UPDATE 中的 **Fragonard / Showboat / Bagpipes 等实例记忆**，不只是抽象的输出格式规则。
- Evidence、Concise、Wordplay 等章节存在 requested answer type、clue relation 和重复证据等语义交叉；删除一个章节不等于清除一种唯一机制。
- 两个 lesion 长度明显不同，没有等长度 placebo、完全正交的规则分解或全析因交互对照；提示长度、冗余、注意力分配与内容变化无法干净分离。
- Base/full 复用的是 C 同一批轨迹；E 的来源结果不能算额外独立复现。新 lesion 只有单次生成，不覆盖模型种子、时间或服务漂移。
- 没有跨五组比较的多重检验校正，也没有对更广领域作推断。区间不构成 Gate 安全认证或跨域 scope 扩张证据。
- 保留所有无效、负向和混合结果。不能因为某一 lesion 不符合预期，就重新删几条规则、换题或扩大本轮样本后仍称为原注册实验。

## 失败与恢复边界

本次 E test 的第一条请求必须成功，才释放其余 worker。之后连续三次完成请求失败会触发停止；断路状态不会被已经在途的成功请求清除。已在途调用仍可能结束并留下缓存。两个 lesion 共用本次执行的健康检查/断路器，不是第二个 arm 必然另做一条独立预检。

失败缓存保留，不会自动删除或重试其终止失败请求。相同冻结目录再次执行 test 会复用成功/失败缓存与已有完整 JSONL；如果同一失败缓存再次触发断路器，重复命令不解决服务问题。未完成的 arm 不会被报告为完整的零分结果；report 会拒绝缺失的完整产物。

停机后先区分连接/session/额度/限流问题与模型答案错误；不要改 Skill、阈值、模型或已冻结 JSON 来恢复原实验。普通进程中断后，尚未发起且未缓存的请求可以在原协议下继续；这不等于重新调用已有失败请求。

**holdout 打开后，不能简单新建目录重新运行 prepare。** 新注册会被拒绝，不能把已经接触的样本重新称为未见 holdout。若确需运输层恢复分支，应由操作者另行明确批准并记录恢复方案，保留原失败证据并证明沿用原注册内容；当前 CLI 不自动提供这种分支流程。否则应报告实验未完成，而不是悄悄覆写缓存或补注册。

静态接口的实用边界是：prepare 的 exposure 检查依赖已知 source / D 路径且没有跨进程锁；节流/session 初始化由指定 CLI 提供，直接调用 Python 函数不保证同样的执行环境。严格串行和原入口是协议的一部分。
