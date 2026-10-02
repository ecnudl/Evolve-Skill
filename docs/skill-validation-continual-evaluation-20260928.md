# 五基准、六检查点：持续学习评测框架

版本：`continual-eval-v1`，2026-09-28。入口为 `python -m skillopt.continual_eval`。

本轮实现**评测流**，不是新的进化算法。支持把外部学习程序产生的冻结 Skill 注册为 S1–S5，再逐阶段评测五个 benchmark。尚未运行五域 No-Skill 或其他方法的正式成绩；不能把下面的工程 smoke 当泛化结果。历史实验、判分和授权不改写。

## 1. 协议与边界

默认顺序为 BigCodeBench → SpreadsheetBench → SearchQA → KOR-Bench → ALFWorld。顺序可以在启动前更改，冻结后不能换。S0 是共同空 Skill；Sk 声明已完成前 k 个来源阶段，但框架只核对父子版本及来源声明，**不独立认证训练真的发生或遵守了数据边界**。

| 输入阶段 | 本框架做什么 | 输出 |
| --- | --- | --- |
| 本地原始数据、资源及版本 | `prepare`：规范化公开契约/隐藏答案，保留来源与族身份 | 五种原生任务的 panel；不会生成替代小题 |
| panel、执行环境、模型、预算及曝光登记 | `check` 检查就绪；`freeze` 冻结任务、源码、资源和运行环境 | 不可变 plan；各方法/历史的共同空 S0 |
| 外部训练产生的冻结文本 | `checkpoint`：绑定方法、历史、阶段、父版本和文本哈希 | S1–S5；不产生 Skill 或授予范围权限 |
| 检查点＋某基准公开任务 | `generate`：仅把公开字段与 Skill 交给模型；记录请求、产物、成本 | 每个任务×重复的 prediction；不读取分数 |
| 冻结产物＋原生隐藏评分材料 | `score`：原生判分器在宿主侧评分 | pass / fail / unknown、原生指标及执行信息 |
| 已完成与未完成位置 | `report`：按冻结任务清单补足缺失分母 | 每方法/历史的 6×5 矩阵、迁移及配对比较 |

五个基准每阶段都评，但分数不得返回 Skill/Rubric/Research 更新器。当前用独立命令和白名单接口隔离，`host_only/` **不是操作系统权限隔离**；正式实验仍需执行者遵守盲评规则。持续学习调度器、跨阶段 Current/验证器状态继承、跨域准入及五种方法的训练程序不在本次新增范围内。

配置模板预留 `no_skill / skillopt / ours_fixed / ours_adaptive / ours_research`，只是冻结结果接入口，不表示已经实现或复现这些方法的五域训练。每份 Skill 最多 6,000 UTF-8 bytes，目前统一原样注入，**不是 Skill 检索、学习路由或条件回退评测**。要比较 SkillOpt 应另外训练合规来源检查点，不能把旧弱父命名为 SkillOpt。

## 2. 五个原生适配器

| Benchmark | 模型的输入／输出 | 评分依据 | 当前限制 |
| --- | --- | --- | --- |
| BigCodeBench | instruct/complete 提示 → 完整 Python | 官方 `untrusted_check` 与原测试，隔离执行 | 需要完整官方依赖镜像；受限资源协议不自动等同排行榜配置 |
| SpreadsheetBench | 操作要求、公开目标区域、首个输入工作簿预览 → Python 程序 | 同一程序分别处理各输入，复用原生目标单元格比较 | 不是 GUI agent；镜像无公式重算引擎，缺计算缓存时 unknown；非目标格式/保留区未作为新增主指标 |
| SearchQA | question/context → `<answer>` | 既有 EM 主指标，另存 F1/subEM | 无在线搜索工具；缺检索上下文不能补隐藏答案 |
| KOR-Bench | 规则＋问题 → 答案 | 官方五类单题 scorer | 需要固定官方源码三个文件的哈希；含表达式求值，必须在容器内运行 |
| ALFWorld | 当前观察、可用动作与近期轨迹 → 下一动作 | 原生环境终局成功 | 需要完整 TextWorld 数据与依赖；每位置新环境，固定种子/步数，专家轨迹不入模型 |

前四项当前是共同的 `initial-only` 一次生成配置，不是 9/27 DSL 学习入口的 `reliable_v1` 公开执行修订协议；ALFWorld 按固定动作预算交互。不同方法在同一基准上使用完全相同预算/工具。暂不把旧 DSL 修订逻辑强接到所有原生环境。后续若新增工具或一次公开修订，须单独冻结新配置并统一重建基线。

隔离执行采用 Linux Docker 固定镜像身份、无网络、只读、低权限和资源限制。不挂载仓库、密钥或 Docker socket；Spreadsheet 求解阶段不提供标准工作簿。环境缺失不退回本机裸跑。原生 worker 是非对抗性代码测量，不声称能防止恶意代码篡改容器内观察器。

部署步骤和依赖来源见[运行环境说明](../skillopt/continual_eval/runtime/README.md)。新入口没有 SSH 远程执行适配层，建议将**整个评测进程运行在 Linux**；已有本机→远端 DSL 调度器不会自动被新入口复用。

## 3. 数据准备与独立性

每题有 `task_id / family_id / project_id / partition / public / private`。支持 development、verifier_calibration、skill_confirmation、final；本入口只评 development 或 final，不执行两个 Gate。相同题/族不能跨分区，项目隔离需显式启用。重复运行、三种产物和同族变体不算新增独立题。

导入器的默认族划分是保守工程起点（例如 SearchQA 按标准化问题，KOR 按类别＋规则），**不是自动语义去重**。正式面板仍需人工审查近重复、已消费任务及来源许可。SearchQA 本地旧训练集已导入 400 条，只标 development；不能直接当新的 final。

正式 final 配置必须附曝光清单，格式如下：

```json
{"version":"continual-exposure-v1","records":[
  {"benchmark":"searchqa","task_id":"old-id","family_id":"old-family","purpose":"development"}
]}
```

框架拒绝登记过的题/族进入 final；**不能证明登记清单完整**，空清单也不证明未曝光。`protocol_complete` 只表示五域任务和必要声明齐备，不等于运行环境就绪、数据独立或方法有效。数据缺失、fixture、来源不完整均不得改名为真实完整评测。

导入命令（路径由操作者提供；不自动下载第三方资料）：

```bash
# 以下在仓库根目录运行；--revision 用真实冻结版本，不用 main/latest。
python -m skillopt.continual_eval prepare --benchmark searchqa \
  --source /ABS/searchqa/items.json --revision SEARCHQA_REV \
  --partition development --output /ABS/panels/searchqa.json
python -m skillopt.continual_eval prepare --benchmark bigcodebench \
  --source /ABS/bigcodebench.jsonl --variant instruct --revision BCB_REV \
  --partition final --output /ABS/panels/bigcodebench.json
python -m skillopt.continual_eval prepare --benchmark korbench \
  --source /ABS/logic.json --rules /ABS/logic_rules.json --category logic --revision KOR_REV \
  --partition final --output /ABS/panels/korbench.json
python -m skillopt.continual_eval prepare --benchmark spreadsheetbench \
  --source /ABS/dataset.json --data-root /ABS/spreadsheet-data --revision SHEET_REV \
  --partition final --output /ABS/panels/spreadsheetbench.json
python -m skillopt.continual_eval prepare --benchmark alfworld \
  --source /ABS/alfworld-manifest.json --data-root /ABS/alfworld-data --revision ALF_REV \
  --partition final --output /ABS/panels/alfworld.json
```

KOR 示例仅导入一个类别；完整面板应合并五类并统一去重/验证后冻结。若原始数据只有 ID 没有 question/context，SearchQA 导入会明确拒绝。Spreadsheet 缺配对工作簿或文件命名不受支持时拒绝，不猜测标准答案路径。

## 4. 可运行入口与恢复

```bash
# 零 API、零模型代码执行的五基准×六阶段编排 fixture
python -m skillopt.continual_eval smoke --output outputs/continual_eval/offline_demo
# 再次执行同一命令：new_positions=0，复用相同 report_hash。

# 修改配置副本，填入 panel 路径、原生环境和曝光清单，然后运行：
python -m skillopt.continual_eval check --config /ABS/study.json
python -m skillopt.continual_eval freeze --config /ABS/study.json --output /ABS/run

# 以下 generate 会使用本地 .env 中的 GLM-5.3 密钥；上面命令都不调用模型。
python -m skillopt.continual_eval generate --run /ABS/run \
  --method no_skill --history h0 --stage 0 --benchmark searchqa --workers 2
python -m skillopt.continual_eval score --run /ABS/run \
  --method no_skill --history h0 --stage 0 --benchmark searchqa
python -m skillopt.continual_eval report --run /ABS/run

# 学习程序在第一来源阶段结束后，独立注册已经冻结的 Skill：
python -m skillopt.continual_eval checkpoint --run /ABS/run \
  --method ours_research --history h0 --stage 1 --skill /ABS/skill-s1.txt \
  --provenance 'frozen training run ID and selection record'
# 对该检查点依次执行五个 benchmark 的 generate/score；之后再注册 S2。
```

配置模板：[five_benchmarks.json](../configs/continual_eval/five_benchmarks.json)。模板不是已完成的数据准备，三历史×两重复也不是统计充分性保证。先做 Linux 原生正/负控制、开发集难度诊断，再提前冻结正式规模和多顺序预算，不能看 final 分数后换题。

产物在 `predictions/`，评分与报告在 `host_only/`，检查点在 `checkpoints/`。相同终态直接回放；并发 1–10 受控、同目录单写者。网络断点只有 intent 没有终态时**不重新采样**，操作员核查后可用 `close-interrupted --position HASH` 明确结束为 unknown；已花调用保留，未闭合调用的 tokens 为未知，不能补成 0。源码、数据、镜像、Python/依赖或协议变化需新目录，不能改变旧成绩。

9/28实际启动后补充：Linux先运行`proxy_on`；HTTP客户端不读环境代理时，在新的`model`配置显式增加`proxy`，只允许原有本机loopback或已核实的PJLAB网关3128。首个真实请求必须先通过健康检查才展开并发，防止把未调用任务批量记成unknown。原始离线验收及A网络失败均保留，新行为使用B源码快照；当前真实运行与基线安排见[运行记录](skill-validation-baselines-20260928.md)。

## 5. 输出指标与解释

- 每个方法/历史提供 S0–S5 × 五域矩阵：原生主指标、pass/fail/unknown/missing、任务/族/重复分母；缺域的五域宏平均 Pending，不按已完成域冒充全域。
- unknown 单列，同时给全尝试下界/上界和可评样本均值；不会丢掉失败调用获得虚高 acc。下界将未知贡献记为 0，但不把未知重新标为语义 fail。
- 配对比较：当前阶段对自身 S0/上一阶段、显式 No-Skill S0，以及已注册的同历史同阶段 SkillOpt；报告胜、负、平、未知、均值差、最差域和负域数。
- 前向迁移：首次在某域学习前，相对 S0 的该域变化（首域不计）；后向迁移：S5 相对刚学完各旧域时的变化（最后域不计）。另保留逐阶段对 Base 的负迁移，不能让正负相抵后只报一个均值。
- 模型逻辑请求、HTTP 尝试、tokens、未知成本单列；未评分位置成本仍计入全运行账。容器回执另保留执行次数/耗时，不等于完整美元成本。

当前统计是描述性，不提供显著性或安全授权。重复不是独立家族，正式论文还需预登记族/项目层面的区间、多序列顺序、最小独立错误空间及非劣界。跨基准平均变化不等于机制泛化；最终还要分别分析同机制迁移、条件反转与无关任务。

## 6. 验收及下一步

离线测试覆盖导入、公开/私有隔离、任务/产物/回执身份、分区、不可变检查点、缺失成本、错误恢复、原生适配与跨方法统计。独立 code review 发现并修复了评分字段覆盖宿主身份、有效评分互换任务、嵌套模型回执错配及不配对请求漏计四项问题；Spreadsheet 公开目标范围也已补齐，仍不暴露目标值。

最终新模块 **130 passed**；相关旧模块＋新模块同进程回归 **2,556 passed、0 failed/skipped**，Ruff与编译检查通过。五域×六阶段离线smoke完成30位置，第二次新增0、报告哈希不变。最终源码的Linux原生控制3/3符合预期，5次容器执行共5.568秒；早一轮同组5次另外保留，不累计为独立样本。真实旧SearchQA 400条导入、就绪检查与冻结成功，0模型调用，仍只是development准备。

文档严格构建在“已跟踪文件＋本次改动”的独立副本通过。完整工作目录初次构建的26条警告来自本来就未跟踪的历史研究文档，未删除或修改这些文件，也未关闭strict；默认`skill`环境缺MkDocs，复用了已有专用文档环境。独立review之外，联调补充容器执行元数据兼容测试，防止安全白名单误拒合法原生回执。

验收数据与限制汇总到[机器可读记录](results/continual-evaluation-framework-20260928.json)，重要结论同步到[结果账本](results-and-lessons.md)。本次没有正式 No-Skill/SkillOpt/Our 模型成绩，不公布 fixture 的“100%”作为 benchmark 分数。

下一步是补齐并验收五域真实资源，先跑冻结开发诊断；随后锁定独立 final 与共同求解协议，采集 No-Skill S0，再接入真正训练得到的 SkillOpt 和 Our 检查点。先有可信基线，再开始五阶段协同进化比较；不把所有方法名称写进配置就称作已完成对照。
