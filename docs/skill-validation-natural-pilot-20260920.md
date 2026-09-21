# 自然 Coding 数据上的条件化 Skill pilot 协议

2026-09-20。本页记录运行协议、实现接口与能力边界，不因后续运行状态改写协议。初期 b 在 96 个开发位置暂停；截至 9/21 发布已恢复至 **169/256 个位置**，仍无方法效果结论。下文的 150／152 是公开参考检查的工程验收结果，不是模型成功率。最新断点见[发布汇总](research-progress-20260921.md)，初期诊断见[实验报告](skill-validation-natural-results-20260920.md)。原未闭合请求已登记为独立 local unknown，没有伪造 API 回执或重新抽样。

这轮研究的问题是：同一个历史父 Skill 经条件化清理后，公开执行反馈能否提供额外价值；在相同的任务级探针接口和预算上限下，外部资料 Research 是否比无 Research 的反思产生更多可校准的新证据。它延续[上一轮的诊断](skill-validation-single-round-results-20260918.md)，新增自然数据实验入口，不改写历史实验结果，也不把[工程门禁 smoke](skill-validation-gated-loop-20260920.md)当成自然任务效果。

## 1. 数据、模型与冻结单位

数据来自 HumanEval+ `v0.1.10` 的固定发布资产，压缩文件 SHA-256 为 `272720b90ac375502c8ed23cd791c2a93dfb22a911641a494da74a426c09f101`。本地桥接器校验下载内容、记录源行哈希，并在模型请求前冻结题目身份与历史暴露清单。

当前继承运行根目录为 `outputs/skill_validation/natural_20260920_b/`。其 `data_manifest.json` 保留 a 的全部题目身份与分区，声明以下自定义划分；a 的暂停、评分器修复和 b 的继承关系见第 6 节：

| 分区 | 任务数 | 用途 |
| --- | ---: | --- |
| development | 64 | 生成 No-Skill/Parent 自然产物；形成开发反馈与公开差异诊断 |
| verifier_calibration | 24 | 独立校准冻结的探针生成策略 |
| skill_confirmation | 24 | 候选冻结后的描述性确认，不选优、不调参、不更新候选 |
| final | 40 | 对全部冻结条件作最终独立描述性评测 |

合计 152 个任务身份。选择使用固定 seed `20260920`，按任务哈希排序，不按新模型成绩或 H 挑题。静态兼容性筛选排除不支持的输入／输出形态、特殊 oracle 和无法合法公开示例的任务；默认前三区为 64/24/24，剩余合格、未暴露的词面 family 代表进入 final，且 final 不少于 24。本次 manifest 的实际 final 数为 40。

完整公开参考验收发现其中两题仍存在公开契约或适配器不兼容，分别位于 confirmation 和 final；处理方式见第 6 节。固定分区与公共分母仍为 152，最多 150 题具备评分资格。两题在所有 arm／repeat 的位置保留为 unknown，不发送模型请求，不记为模型语义失败；H 超时等情况还可能进一步降低实际已知审计覆盖率。

词面 family 使用题面词序相似度的连通分量，每个 family 只取一个代表，分区之间无该分组的重叠。它不能认证语义上的 family 独立性；本轮也不具备项目级互斥。历史扫描覆盖仓库 `outputs` 中可定位的 HumanEval 身份和题面哈希，不保证模型预训练未见过公开题。

**这是原 HumanEval test 题目上的自定义四分区兼容实验，不是官方榜单、完整官方 pass@1 或标准训练／测试划分。** 基础与增强检查均由当前适配器执行，比较器、公开示例披露和筛选规则必须随结果一起说明。

| 项目 | 固定设置 |
| --- | --- |
| 模型 | PJLAB `glm-5.3`；temperature=0，reasoning_effort=low，streaming |
| 父 Skill | 历史 V16 第一条学习历史、第一轮 fixed 更新；校验原始模型回执与冻结链 |
| 父 Skill 来源边界 | 历史合成 Coding 场景的模型产出，不据此宣称自然任务训练历史或部署资格 |
| 求解重复 | 每个任务、每个文本条件 2 次 |
| updater 抽样 | 各更新臂 2 次，同一个父 Skill；不是两条独立学习历史 |
| updater 公共开发反馈 | 固定 8 道题；通过校准后的追加 probe 反馈限其中 task hash 最小的 4 道 |
| 模型并发／远程执行并发 | 6／4 |
| 单次模型输出上限 | 2,048 tokens |
| Research 模型可见资料 | 每页最多 6,000 字符，最多三页；获取快照及其完整哈希另行保存 |
| 整轮逻辑请求上限 | 2,400；实际唯一请求、HTTP 尝试与 token 另记 |
| 运行与选择 seed | `20260920` |

temperature=0 不保证两次求解完全相同。重复是同一道题的重复测量，updater 抽样是同一个父 Skill 的多个更新样本，不能把它们计为独立任务或独立学习历史。

## 2. 公开证据与宿主 H 的边界

求解器接收题面、公开的比较容差说明和可选 Skill。返回契约统一为一个 JSON 对象，且只有 `solution.py` 对应完整 Python 源码字符串；要求的函数签名、标准库和当前任务契约优先于 Skill。求解器提示不提供隐藏测试、参考实现、额外输入契约或 evaluator 内部信息。

公开固定检查首先提取原题面中可静态解析的字面量例子。b 的通用解析规则规定：题面存在独立 `Example:`／`Examples:` 节时，inline 等式只从该节提取；doctest 调用仍单独识别。缺少可支持例子时，统一向所有条件披露一条可支持的原始字面量 assertion，并记录来源。它们经 `public_runner.check` 聚合执行；开发反馈重放绑定的是相同的 `public_task` 与真实公开执行回执。

宿主 H 在隔离执行器中，分别对发布数据的全部 `base_input` 与 `plus_input` 做参考实现差分检查。报告的 `native_status` 是本协议基础输入检查的结果，`status` 是基础与增强检查的合并结果；它们不是未经修改的官方测试运行成绩。基础与增强任一明确失败则合并为 fail，两者明确通过才是 pass，其余为 unknown。参考程序检查不通过时，对应模型产物的审计身份保留为 unknown。此次评分器修复没有放宽 H 的 10 秒执行超时；超时仍保留为 unknown。

兼容比较先使用 Python 相等语义，浮点结果可使用 `rtol=1e-7` 与源任务绝对容差；源容差为零时，标量或同质浮点列表还使用 `atol=1e-6`。这些规则对公开固定检查与 H 明示。新增任务探针使用严格 JSON 类型和值比较，不自动继承浮点近似相等；其误拒风险必须由校准反映。

只有以下有限信息可以越过宿主边界：

- 两个自适应策略规划器共同看到同一份公开开发反馈，以及未链接到具体题目的开发 `V/H` 状态组合计数。该计数明确标为宿主开发审计摘要，不能称作 Research 自己发现的缺口；不提供隐藏输入、输出或参考源码。
- H 校准标签只用于宿主 `calibrate_policy` 判定策略能否提供有限的开发反馈，不进入任务级 probe 提示，也不用于补出 probe 的 expected 值。
- Skill updater 接收公共任务契约、公开产物和实际公开回执；通过校准的臂还可接收标为假设的新探针与其执行观察。updater 不接收校准 H 标签、确认结果或最终结果。

任务级 probe 提示只序列化公开题面、函数入口、冻结策略、引用及去重排序的匿名 `solution.py` 源码。它不传递 condition 标签、Skill 身份、宿主 H 或执行器身份；相同探针对该题全部配对产物执行。

## 3. 更新条件与主要 Research 对照

No-Skill 和原始 Parent 是共同基线。候选更新条件如下，每个条件登记 `u0`、`u1` 两个 updater 样本：

| 更新臂 | updater 可见信息 | 解释边界 |
| --- | --- | --- |
| contract_only | 父 Skill、共同 Python/JSON 输出契约及公开任务声明；无提交代码、执行观察或分数 | 测量格式和适用条件清理，不能称为从执行失败学习 |
| fixed | 同一公开契约，加原始公开检查的配对产物与回执 | 公开原始检查基线，不生成新探针 |
| adaptive_no_research | 与 Research 相同的策略／任务探针接口和预算上限；不取外部资料 | 经校准才可追加新探针反馈；未通过则回退 fixed 反馈 |
| adaptive_research | 相同开发信息、策略／任务探针接口和预算上限，另允许有限官方资料 | 经校准才可追加新探针反馈；未通过则回退 fixed 反馈 |

主要 Research 对照是两个 adaptive 臂。fixed 与 adaptive 还存在“是否具有新探针生成接口”的差异，所以不能把 fixed 到 Research 的差异全部归因于外部检索。预算上限相同也不等于实际成本相同，必须报告实际检索、请求、token 和执行开销。

每个 adaptive 臂最多一次规划、一次综合模型调用，每次最多 2,048 tokens。Research 最多请求三份唯一的 Python 3.11 官方文档，限定 `docs.python.org/3.11/library/` 下预注册的 `copy/stdtypes/functions/re/string/math/collections/itertools/functools` 页面。URL、重定向链和缓存回放均受白名单限制。b 在新增付费调用前，将单页模型可见摘录上限由 12,000 字符调整为 6,000 字符并写入冻结协议，以满足提示预算；获取源快照与原始摘录哈希仍保留，模型摘录另有自身哈希。引用只能来自实际提供给模型的精确片段，引用证明来源而不证明任务语义。

策略必须显式给出 mechanism、applicability、exceptions、evidence_required、check_generation 和 uncertainty，义务固定为已有的 `requested_behavior`。每题每策略最多生成两个 JSON 探针，形式为一个有假设 expected 值的调用，或两个假设应相等的调用。模型不能提交可执行探针脚本。公开引文匹配仅证明引文来自题面，不证明输入合法、关系成立或 expected 正确。

策略、探针和 Skill 响应均有终止式解析。`no_update`、`insufficient_evidence`、空探针和无新 Skill 是正常结果；格式错误不修补、不追加抽样追求成功。执行基础设施失败则停止后续付费阶段并保留回执，不把错误包装成语义失败。

四个更新臂共同使用第一轮求解中按 task hash 升序选出的 8 道开发题；通过校准的 adaptive 臂，只为这 8 道中 task hash 最小的 4 道追加 probe 反馈。两级选择均不查看 H 或 probe 结果。该 8／4 限额在主实验首次付费调用前，经提示尺寸验收固定，原因是模型请求的 system 与 user 合计具有 120,000 UTF-8 bytes 硬上限；数据划分、求解重复和 updater 抽样次数不因此改变。

条件化 updater 明确要求 Preserve / Repair / Restrict，允许删除无条件或冲突的旧规则，并要求在条件不成立时停止应用该规则。输出仍为 `Mechanism / When / Procedure / Avoid` 四节 Markdown，最多 6,000 UTF-8 bytes；解析器只检查形式，不自动验收其语义效果。

所有 updater 样本都从同一个 Parent 出发。若未获得新探针反馈，adaptive 可能与 fixed 形成完全相同的请求；相同提示、重复号及调用类型共享缓存。相同 Skill 文本也会共享相同求解请求。结果必须同时报告名义条件数、唯一 updater 请求数和唯一候选文本数，不能把别名当作独立方法收益。

## 4. 策略校准的有限授权

`natural_metrics.calibrate_policy` 比较同一批独立 verifier_calibration 自然产物上的 fixed 与 new 判断，使用相同的 H 标签和分母。计量单位是每个 `(task_id, repeat, condition)` 的一条 `requested_behavior` 产物任务义务；增加探针不会增加义务数。重复位置拒绝，unknown 不算已知错误或正确样本。

冻结阈值为：

| 条件 | 阈值 |
| --- | ---: |
| 声明的独立 family 数 | 至少 8 |
| H 已知错误义务 | 至少 4 |
| H 已知正确义务 | 至少 12 |
| 新策略判断覆盖率 | 至少 0.90 |
| 相对 fixed 的误拒率增幅 | 不大于 0 |
| 净新增错误检出 | 至少 1 |

净新增检出减去丢失的原有检出。误拒率在 H 已知正确义务上计算，覆盖率单独约束未知判断。缺少错误、正确样本或 family 时返回 `pending`，样本够但风险／增益条件不满足时为 `rejected`，全部满足才为 `accepted`。不能因为正确样本多、公开分数高就制造通过。

这里的 `accepted` **只允许冻结策略提供 Coding、requested_behavior、development 范围内的 qualified public feedback**。它不证明任一模型 expected 值为真，不授予 Skill 准入、部署、Near-Miss 或跨域权限。策略哈希同时绑定冻结策略、协议、probe 生成入口与执行器；改变这些身份不能沿用既有校准。

未获授权的 adaptive 假设不会回流 updater。对应更新条件仍可使用固定公开反馈形成探索候选，并显式记录 `fallback_feedback`，避免把回退后的同一证据当作 Research 的增量干预。

## 5. 冻结、确认、最终报告与 Skill Gate

所有候选文本、提示哈希和请求身份写入 `frozen_candidates.json` 后，才进入 24 题 confirmation 和 40 题 final。confirmation 不筛选候选、不改阈值、不决定“再试一次”；final 不反馈给任何模型、不更新 Skill、策略或分区。即使一个候选表现较好，本轮也没有 retention/Near-Miss 部署面板和适用范围授权。

因此 `skill_decision.json` 的 Skill Gate 保持 **Pending**，所有候选均是受控评测中的原始文本条件，`deployment_authorized=false`。没有跨域实验，也没有“已经获得可靠适用边界”的结论。

`natural_metrics.summarize(records, partition=..., protocolseed=20260920)` 对 development、skill_confirmation、final 分别生成带来源身份的描述性报告：

- 每个 arm 的全部预注册位置 pass/fail/unknown、完整分母成功率与审计覆盖率；unknown 保留分母，单列而不算作已执行语义失败。两道不兼容题虽不发送模型请求，仍保留对应位置；因此 `full_attempt_success` 的分母包含这些占位记录，实际 API 调用数由成本回执单独统计。
- 基础输入检查与更强 H 的差距，区分基础通过但增强失败与未知配对。公开例通过、基础通过、增强通过都是有限检查结果，不等于完全正确。
- 每个候选相对 No-Skill 和 Parent 的 win/loss/tie/unknown；任一未知则为未知配对，双方失败也是 tie，不能写成双方正确。
- 先在每个 task 内平均重复，再按声明的 family 整组重采样，固定 seed 做 2,000 次 bootstrap，给出描述性 95% 区间。点估计对 task 等权，重复不作为独立样本。该区间不认证 family 的语义独立性，也不建立 Skill 因果效应。

应同时检查 updater 是否真正删除／条件化了旧规则、是否仍存在输出协议冲突，以及任何观察收益来自交付修复还是新的行为证据。模板符合四节要求、策略格式有效、校准通过和候选最终得分，是四种不同的判断，不可互换。

## 6. a 暂停、评分器修复与 b 继承

`natural_20260920_a` 启动后完成了 36 次 `glm-5.3` 求解请求，API 状态均为 ok，累计记录 32,457 tokens。随后，对全部 64 道开发题开展的公开参考检查工程验收发现唯一一处示例解析错误：`HumanEval/130` 题面中的数学说明 `tri(2)=2`、`tri(4)=3` 被提取成函数返回值例子，而该函数实际要求返回列表。

a 已优雅暂停，36 次请求的完整终态回执均已保存，修改前源码归档为 `outputs/skill_validation/natural_20260920_a/source_before_adapter_fix.tar.gz`。问题来自公开参考实现验收，没有依据这批模型的得分筛题或选择保留哪些输出。这里报告的是 API 请求和成本记录，不是解题成绩。

修复采用第 2 节的通用 `Example(s)` 分节解析规则，保留原题与完整 64/24/24/40 分区。b 的 amendment 绑定 a 的 manifest/protocol 哈希，继承相同源数据和父 Skill，明确记录 `same_panel_not_new_independent_sample=true`、已有开发模型产物和未依据模型结果选题。**b 是同一批 152 题的评分器修复继承运行，不是新的独立样本或第二次独立实验。**

原 36 份完整 solver 回执仅在 system/user 提示、模型／service、repeat 等请求身份精确一致时复用，不为相同已完成请求重新抽样。复用对象是模型响应，修复后的公开检查与新协议身份另行绑定；实际复用数量和新请求成本须分别记录，避免把继承请求再次记为新增付费调用。

b 同时冻结了每页 6,000 字符的模型资料摘录预算；8 道公共反馈题、其中 4 道追加 probe 反馈、全部分区与重复次数均不变。H 的 10 秒超时也不变。

全部 152 道题的公开参考检查工程验收现已完成：**150 pass、2 fail**。该验收没有调用模型，也没有执行隐藏审计；终态 `summary.json` 的 `ready=false` 保留，不能称为 152 题全部通过。两项不兼容如下：

| 任务 | 固定分区 | 公开参考验收问题 | 正式记录方式 |
| --- | --- | --- | --- |
| HumanEval/47 | skill_confirmation | 原始公开示例给出 15，而对应数学中位数为 8，题面内部存在矛盾 | 每个条件／重复保留 unknown，不发模型请求 |
| HumanEval/148 | final | 要求返回 tuple，当前 JSON 适配器不支持；单元素 tuple 的公开写法又缺少逗号，静态字面量被解析成其他类型 | 每个条件／重复保留 unknown，不发模型请求 |

不修改这两题的答案、不替换题目、不从共同分母删去它们，也不将参考兼容性失败转记为模型语义失败。分区仍为 64/24/24/40，公开兼容的任务为 64/24/23/39，共 150 道；这只说明公开检查可评分，并不保证 H 必然有已知结果。`HumanEval/130` 的公开示例抽取已修正，但参考 H 在 10 秒预算内超时的情况仍为 unknown，未延长时限。

b 的 `--public-preflight` 指向 `outputs/skill_validation/natural_engineering_preflight_b_20260920/summary.json`。runner 验证该验收覆盖整个相同 manifest，且没有模型调用或隐藏审计，将完整记录存为 `public_compatibility.json`，并把其哈希及两题状态绑定到 `protocol.json`。如果不兼容项落在 development 或 verifier_calibration，入口会停止，不能带着无效开发反馈继续主实验；本次两项都位于确认／最终分区，因此按统一 unknown 规则继续。

b 已使用该冻结协议启动，正在开发阶段复用符合精确绑定的 a 回执并进行新增自然模型请求。这里只报告工程兼容性与运行状态，不报告尚未完成的自然模型效果；完整主线测试数量待最终验收后另行更新。

## 7. 执行命令与可回放产物

从仓库根目录登记 a 到 b 的同面板修订，保留原题目和父 Skill，不重新选择数据：

```bash
python -m skillopt.skill_validation.natural_study amend \
  --repo . \
  --output outputs/skill_validation/natural_20260920_b \
  --reuse-from outputs/skill_validation/natural_20260920_a
```

使用已准备的远程代码快照运行：

```bash
python -m skillopt.skill_validation.natural_study run \
  --repo . \
  --output outputs/skill_validation/natural_20260920_b \
  --remote-repo /root/skillval-natural-b-20260920.zpKBeX \
  --reuse-from outputs/skill_validation/natural_20260920_a \
  --public-preflight outputs/skill_validation/natural_engineering_preflight_b_20260920/summary.json \
  --workers 6 \
  --execution-workers 4 \
  --repeats 2 \
  --update-repeats 2
```

可增加 `--stop-after development` 在开发阶段后停下检查基础诊断。b 冻结后的常规恢复应继续使用同一数据、源代码、协议、运行目录、`--reuse-from` 来源及 `--public-preflight` 验收记录；不可通过覆盖回执或清除未完成 intent 重抽不满意的响应。a 到 b 的必要评分器修改通过独立 amendment 与旧源码归档披露，不能静默覆盖 a 的协议。

模型产物和参考代码仅在远程 Linux 隔离 Docker 中执行，不在本机执行。执行器复用已固定的镜像，启动前做预检，发生基础设施失败时保留中断状态。API 凭证留在本地配置，不进入模型提示、报告或远程源码快照。

主要产物按职责分开：

| 路径 | 内容 |
| --- | --- |
| `data_manifest.json`、`source_snapshot.json`、`exposure_inventory.json` | 固定题目、发布资产、历史暴露身份及 b 对 a 的 amendment |
| `parent_skill.json`、`protocol.json` | 父 Skill 回执链、运行参数／源代码哈希及继承 solver 回执来源 |
| `public_compatibility.json` | 全 152 题公开参考验收；150 pass／2 fail，两项不兼容在正式公共分母中保留为 unknown |
| `api/`、`model_budget/` | 实际模型回执、请求预算和未完成 intent |
| `public_feedback.json`、`public_reports/`、`public_execution/` | 公共反馈与源绑定执行回执 |
| `policies/`、`frozen_policies.json`、`probes/`、`probe_execution/` | 策略、资料缓存、模型探针假设与实际调用 |
| `verifier_authorities.json` | 策略校准状态与有限开发反馈权限 |
| `host_only/` | 隐藏审计回执、各分区行记录与校准／确认诊断 |
| `frozen_candidates.json`、`skill_decision.json` | 冻结候选与保持 Pending 的 Skill Gate |
| `results.json` | 完成后才形成的描述性汇总、唯一请求／文本数量及实际成本 |
| a 的 `source_before_adapter_fix.tar.gz` | 必要评分器修改前的源码归档，保留旧运行可审计性 |

当前能力是一次有界的 Coding 条件化内容研究：它能把公共契约假设落成隔离观察，并用独立校准限制新反馈的使用。它尚不能证明自然任务改善、Research 增益、稳定机制泛化或跨领域迁移；这些都需要真实完成记录和后续独立实验支持。
