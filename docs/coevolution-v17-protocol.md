# V17：任务级跨域反馈与经验性范围准入

状态：首次 V17 模型调用前登记；不修改 V1–V16 源码、协议或结果。

## 研究目标与本轮边界

核心目标是 Skill 内容的跨域收益与稳定性，而非单个 benchmark 的最高分。V16 的额外输入测试未证明自然检错到泛化的因果链，且 No-Skill 最终满分。本版将新的目标领域任务执行证据真正接入 Skill 更新，并将 Skill 本身的效果与 gate 回退保护分开。

这是新编写合成任务上的探索性机制实验，不是公开 benchmark、原版 SkillOpt 对照或已经完成的持续协同进化。本轮不新增 Research 干预，也不再进化局部输入搜索策略：先隔离跨域反馈是否有效，避免同时改变过多模块。结构化臂是信息守恒的证据组织消融，不声称凭格式自动获得机制理解。

## 两个主对照

所有学习历史先在同一组来源 Coding 任务形成一份局部父 Skill。然后在新 Coding 与 Spreadsheet 开发任务上，以 No-Skill 和该父 Skill 配对执行。每份父 Skill 只分叉一次：

| 条件 | 反馈来源 | 组织方式 | 更新次数 |
|---|---|---|---:|
| local_feedback | 新 Coding 来源任务 | 普通记录 | 1 |
| cross_raw_feedback | Spreadsheet 跨域开发任务 | 普通记录 | 1 |
| cross_structured_feedback | 与上一组完全相同的 Spreadsheet 轨迹及事实 | 按领域／任务／角色结构化分组 | 1 |

三个候选共用更新器、父 Skill、输出预算与反馈任务数量。后两组反馈可以精确展平为相同 JSON 事实，不能增加隐藏诊断、额外模型反思或测试结果。上下文组织导致 token 数不同，不能宣称等 token 或等总成本。

主比较：cross_raw−local（换用跨域证据的联合效应）；cross_structured−cross_raw（同证据组织方式的效果）。最终另保留 No-Skill、原父 Skill，识别绝对收益以及父 Skill 是否退化。使用同一 glm-5.3，不更新模型权重。

## 数据与执行

pilot：3 条学习历史；source 6 Coding、source_extra 6 Coding、transfer 6 Spreadsheet；独立 confirmation 8 题（Code/Sheet 各 4）；最终 24 题（Code/Sheet/Rule 各 8，每域至少 4 个结构族，各 2 变体）。不同分区结构族互斥。相同结构变体及不同历史不视为独立新任务族。

Rule 不进入学习或准入，仅用于最终未见领域评测；Coding、Spreadsheet 的最终题是未见结构族，但后者已经进入跨域开发，不能把它称作未见领域。每域最终任务包含显式替代旧行为的 near-miss；该标签只在宿主统计和 gate 保护检查中使用，不向更新器泄漏，不用作最终逐题路由答案。

任务包含预定义 starter、公开规范、独立宿主 oracle 与隐藏检查。参考产物须通过全部检查，starter 至少失败一个检查，才能运行模型。该一致性自检不能证明任务自然度或统计代表性。模型生成 Python 仅由既有 OS 隔离执行器执行；表格和规则使用既有受限确定性执行器。

每次求解共用 V15 runtime：一次初稿、一次公开反馈修订。开发阶段完整可执行结果可进入 Skill 更新；校准／最终隐藏结果不进入模型。API/格式无效 Skill 更新保留父文本并记录失败，不重采样。合法但无效的 Skill 保留为 raw 候选，不以最终成绩选择。

smoke 使用独立专用结构，1 条历史、每开发分区 1 题、confirmation 必须包含两域×两 cell、最终每域 1 题。仅联调，不提供方法有效性结论。

## 有界开发筛查

正式 pilot 先对 history 0 的 source＋transfer 共 12 题运行 No-Skill。仅在可执行语义失败至少 2 个、来自至少 2 个结构族，且没有 oracle unknown 时继续分叉。该门槛是停止浪费的探索性准则，不是统计显著性。

若不通过：保存 complete=true、status=screen_stopped 的结果，不启动学习／准入／最终模型求解，不追加题目直到得到正结果。完整开发题集保留；不得按模型错误筛选最终题。smoke 为联调明确绕过此科学门槛。

开发筛查调用可在该历史中按完全相同干预复用；不同历史不共享模型抽样。通过筛查也不保证所有领域均有提升空间，需分别报告开发 headroom。

## 经验性范围门与最终评测

每个候选在独立 confirmation 中与 No-Skill、父 Skill 配对。按 Coding/Spreadsheet × same-mechanism/near-miss 四格检查，不允许某一格收益抵消另一格损失。

- Cross-domain commit：对两参照均无任何观测损失，并在 Spreadsheet 同机制格相对两个参照都出现至少一个成功增益。
- Local commit：Coding 全部格相对两个参照无损失、同机制格对两个参照均有成功增益，但未满足跨域条件。
- 其他情况 Restrict/Reject；unknown 不能成为批准证据，父 Skill 仅作为学习谱系保留，不自动视为安全回退。

这些是小样本经验规则，**不是统计非劣、安全保证或成熟的 scope-expansion 算法**。准入使用任务族新分区，但不同候选共用同一 confirmation，不据结果继续修改候选、阈值或规则。

部署诊断只按可信环境入口选用 Skill：cross commit 用于 Coding＋Spreadsheet；local commit 仅用于 Coding；其他范围回退 Base。Rule 未获范围批准，部署诊断一律 Base。不能使用 host near-miss 标签决定某道题是否用 Skill，也不称此为机制路由器。

所有历史、全部候选与 gate 决策先冻结，再统一最终评测。即使候选被 gate 拒绝，仍评测其 raw 内容在三个域的表现。部署成绩从同一批 raw/Base 轨迹按事先冻结的域映射重放，标明 shared-draw 离线诊断，不冒充独立在线验证或新的泛化收益。

## 分析与预期判据

报告逐域成功率、域等权平均、最差域变化、对 No-Skill 与父 Skill 的配对胜负、交付／语义／执行 unknown，以及准入覆盖率。比较时以结构族为聚类单位、保留全部变体和历史，使用预固定 seed 的 1000 次域内分层 bootstrap；区间仅条件于三条已观察学习历史，未作多重比较校正，不据小样本零损失宣称安全。

泛化内容证据来自：冻结 raw Skill 在未参与反馈的结构族／Rule 上有收益，且逐域损失可控；gate 把所有任务回退 Base 只说明没有部署候选，不能算 Skill 泛化成功。单个来源域提升、只修复 JSON、或仅提升后验部署平均数，分别如实报告，不混称跨域收益。

本轮 final 一旦用于结果反思，后续改算法必须另留新最终任务。不得把本轮错误反馈给 Skill 后重复跑同一 final 并继续称其独立。

## 预算、恢复与可审计性

沿用 PJLAB glm-5.3、4 workers、HTTP 尝试最小间隔 10 秒、既有有界传输重试；smoke 上限 128 逻辑调用，pilot 上限 1536，不自动上调。凭证只由原客户端读取，不写入新源码、快照或报告。

独立输出 `outputs/coevolution_v17/`。源码、任务、协议、Skill、请求与执行回执不可变。旧 intent 无回执时停止，不能猜测后重发；已有终止错误保留，不为提高分数删样。监督器每 30 秒心跳，检测明显挂起／时钟异常后请求 PAUSE，等待已发请求闭合，不自动删除样本或恢复。

已完成目录通过全量离线重建，禁止网络、模型调用与原生任务重执行，并要求目录字节哈希不变。明确记录实际调用、HTTP、token 与缺失 usage。脚本可以显式恢复，但不修改系统代理或休眠设置。
