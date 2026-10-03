# SkillOpt五域补跑与No-Skill对比（2026-10-02）

## 当前状态

**10/3终态（只读核验）：新D五个来源阶段全部结束，完整学习0/5，最终Skill仍为空；25个评测格全部复用旧No-Skill，0新评测调用。** `final.json`于10/3 01:03写出，状态`attempts_finished_with_pending`。学习端共506逻辑调用/508 HTTP、已知1,113,763 tokens、3条usage缺失、0未闭合。这不是SkillOpt无效的证据：五个Pending都来自交付、记账或接口规则，没有一个候选进入完整选择比较。[脱敏终态JSON](results/skillopt-generalization-final-20261003.json)

| 来源阶段 | 终态原因 | 逐例核查（零新API） |
|---|---|---|
| Coding | `native_optimizer_incomplete` | 父选择40/65、训练24/64；10次反思中1次HTTP200但流未结束（`incomplete_stream`、无usage），v4不重试，优化器无候选。 |
| Spreadsheet | `evaluation_unknown` | 首个选择位置：模型生成程序在自身数据检查处`raise SystemExit`，未保存output.xlsx；无工作簿即unknown，一个unknown使整阶段Pending。不是评分器或执行适配缺陷。 |
| SearchQA | `evaluation_unknown` | 父选择51/64；训练至第51题时1次服务内容过滤（`sensitive`、无usage）。按设计不重试、不绕过。 |
| KOR | `native_candidate_exceeds_skill_budget` | 父选择66/100、训练59/100、17次反思全部完成；最终合并为单条6,172字节追加，超过冻结的6,000字节Skill接口，v4记Pending而非评测。 |
| ALF | `evaluation_unknown` | 34调用/36 HTTP：1次调用经2次失败尝试后恢复，失败尝试usage未知；v4账本把它视为阻断，下一次模型调用在第2个选择回合内抛出`LearningPending`。这是v4网络重试与v4缺usage阻断规则互相矛盾，不是环境或模型失败。 |

后续修复已在本地实现为显式**learning v5**（不改v4、不改D记录）：`incomplete_stream`纳入同一有限重试；失败尝试的未知usage如实报告但不阻断，每阶段最多64次；超出6,000字节的完整原生候选判为不可接受并保留父Skill、继续下一轮，不截断、不评测。unknown分数与内容过滤仍Pending、绝不记0。v5还记录上游合并/排序的静默回退来源，并在账本/预算拦截时保留真实停止原因；仅限SkillOpt。新增15项专测与671项相关回归通过，本地全仓库12,293项通过、22项跳过、0失败（工程验证，不是方法效果）；经用户批准，v5另加入预先冻结的unknown成对排除与每次更新重新执行训练集，接入序列v3；新E于10/3 09:22启动，运行中，见[新E报告](skillopt-generalization-e-20261003.md)。

旧C的SkillOpt与GEPA两条序列也均已终止：两者各完成0/5学习；SkillOpt 420调用/已知710,435 tokens/1缺usage（此前只见于本文，现有终态记录支撑），GEPA 300调用/已知473,290 tokens/2缺usage。[旧C终态JSON](results/fivebench-sequence-c-final-20261003.json)

**以下22:22及更早内容为运行中历史快照，保留原样。**

**22:22发布快照：完整学习0/5，全域评测矩阵闭合3/5，但前15格全部复用旧No-Skill。** 本轮前三来源已因不同问题Pending携空父，KOR继续运行；不是五阶段学习完成，也没有新的非空Skill泛化成绩。[逐阶段对比表](skillopt-generalization-progress-20261002.md) · [脱敏完整快照JSON](results/skillopt-generalization-progress-20261002.json)。以下21:32/21:42记录保留为较早进度，不代表此刻状态。

| 来源阶段 | 新D实际结果 | 解释 |
|---|---|---|
| Coding | 139调用；`native_optimizer_incomplete` | 129求解＋10反思；一条反思HTTP200但`incomplete_stream`，缺usage。不能把不完整反思当作合法候选，也不是完整候选被gate拒绝。 |
| Spreadsheet | 1调用；`evaluation_unknown` | 新v7执行路径返回`native_exception:SystemExit`，无工作簿重算回执，原因仍需定位。23项资格通过不等于所有自然任务可判定。 |
| SearchQA | 115调用；`evaluation_unknown` | 一条服务`sensitive`/内容过滤，缺usage；不绕过过滤、不计为语义错误。 |
| KOR | 已开始，尚无阶段终态 | 不以前缀成绩作候选结论。 |
| ALFWorld | 尚未开始 | 等前序阶段闭合。 |

前三阶段共255逻辑调用/HTTP，已知257,534 tokens、2条usage缺失、调用账本无未闭合意图；HTTP响应流不完整与账本已有失败回执是不同概念。该成本不含仍在运行的KOR。原No-Skill及旧C状态均不改写。本轮说明修复了已知阻塞仍不保证整条自然学习链闭合；后续需分别处理交付、执行异常和内容过滤，不能通过静默补抽或把unknown计0制造完成。

21:32在PJLAB Linux启动新的完整规模SkillOpt队列，先通过新源码的工作簿23项资格控制，再冻结协议并开始Coding来源学习。初始真实调用已确认HTTP200、`glm-5.3`和完整响应；这是运行进度，不是候选最终成绩。不会覆盖旧C的Pending记录，也不会把前三域小样本smoke当正式效果。

21:42核验：本轮Coding空父选择 **40/65**（25 fail、0unknown），正在采集训练反馈，尚无新候选完整选择结果。与全域No-Skill的400/800不是同一个分母，不能直接比较。旧C五阶段尝试现已全部终止，但完整学习 **0/5**；420调用、已知710,435 tokens、1条usage缺失，25格均为携空父后引用旧No-Skill，不能称为已学成的SkillOpt泛化成绩。

协议哈希：`97ca8db2c92820cd5b796939f0afbe06685716f74671caf6ddac076e165a7754`。

[脱敏启动、资格与No-Skill参照数据](results/skillopt-generalization-launch-20261002.json)仅存白名单计数及哈希，不发布私有调用缓存。

## 流程与比较规则

依次在Coding、Spreadsheet、SearchQA、KOR、ALFWorld学习。每次完成原生SkillOpt最多两次更新后冻结选中Skill，在全部五域评测，再将同一Skill传给下个来源阶段。来源选择门不读取其他域评测分数，不加Research、不改为我们自己的安全gate。

| 来源域 | 训练题 / 任务族 | 选择题 / 任务族 | 每个阶段后的该域评测 |
|---|---:|---:|---:|
| BigCodeBench | 64 / 64 | 65 / 64 | 400题×2 |
| SpreadsheetBench | 40 / 40 | 40 / 40 | 80题×2 |
| SearchQA | 64 / 64 | 64 / 64 | 400题×2 |
| KOR-Bench | 100 / 10 | 100 / 10 | 500题×2 |
| ALFWorld | 19 / 19 | 20 / 20 | 39题×2 |

- 初始Skill为空；候选经来源域原生选择后才成为下一阶段父Skill。未知不能充当0分反馈。
- 安全闭合但Pending的阶段携原父继续尝试下一域，明确不计作完整学习；在途调用或原生执行清理不完整则停止队列。
- 评测保持原No-Skill模型服务、提示词模板、预算、源码、执行环境、评分器、任务与重复。只有Skill文本不同；不采用“只修好SkillOpt评分器”的不对称比较。
- 相同文本/评测身份复用已有结果，新增调用为0。空Skill与No-Skill相等不是独立观测，更不代表学到了泛化能力。
- 全矩阵和“排除全部计划train/selection任务族”的子集分开报告。Sheet/ALF在本面板没有剩余留出；所有任务均属此前暴露开发数据，不是独立final。历史No-Skill也无法完全控制服务随时间变化。
- 报P/F/U/待评分全分母、覆盖率、逐位置配对胜负和任务族统计；不把重复当新增独立任务。尚未完整评分时不计算候选最终差值。

## 已完成的No-Skill参照

| Benchmark | 正确 | 错误 | Unknown | 全分母确认正确率 |
|---|---:|---:|---:|---:|
| BigCodeBench | 400 | 399 | 1 | 400/800 = 50.00% |
| SpreadsheetBench | 63 | 44 | 53 | 63/160 = 39.38% |
| SearchQA（EM） | 560 | 234 | 6 | 560/800 = 70.00% |
| KOR-Bench | 746 | 243 | 11 | 746/1000 = 74.60% |
| ALFWorld | 65 | 13 | 0 | 65/78 = 83.33% |

Unknown没有被宣称为语义错误；上列比例是确认正确数除以全部位置。Sheet覆盖仍不足，不以域平均掩盖这一问题。原成本4,115调用/HTTP，已知6,788,261 tokens、7条缺usage，不是完整账单。[原聚合数据](results/noskill-fivebench-long-20261001.json)

排除本轮所有计划学习任务族后的参照如下；它们尚未用于本轮训练/选择，但曾在历史开发评测曝光：

| Benchmark | 剩余任务 / 任务族 | No-Skill正确 / 错误 / 未知 | 全部位置 |
|---|---:|---:|---:|
| BigCodeBench | 271 / 271 | 274 / 267 / 1 | 542 |
| SearchQA | 272 / 272 | 379 / 161 / 4 | 544 |
| KOR-Bench | 300 / 30 | 488 / 103 / 9 | 600 |
| Spreadsheet、ALFWorld | 0 / 0 | 不适用 | 0 |

## 本次改动与工程验证

- 显式新序列v2接入学习v4的严格JSON桥、ALF数据目录绑定、工作簿v7数值读取与有限交付恢复；旧协议不改。
- 学习端长响应服务与评测端原服务分别冻结，启动时、锁等待后及每阶段前检查；防止静默环境漂移。
- 预设上限：两更新、512 metric、64 reflection、12,000逻辑API、报告token停止阈值600万；初始solver65536/reflection4096，符合条件的闭合length最多一次131072恢复。不是绝对计费上限，不宣称与旧预算等算力。
- 学习串行，全域新策略评测最多10并发，隔离执行共用原生锁。只有新策略才触发新的评测采集。
- 本地队列/报告/恢复/启动及自动报告最终97项测试通过；Linux冻结源码对应65项通过。含服务身份负控、完整五阶段fixture、回放零新增调用、锁等待文件漂移、unknown、错配与报告脱敏。工程fixture不是方法有效性证据。
- 扩展本地学习/五域/监控回归 **374 passed、15 skipped**；跳过为可选依赖/对应运行条件，不计通过。独立代码review未发现启动阻断项；报告额外标明未评测位置，不能将其显示为模型零准确率。
- 只读报告器导出五域逐阶段表、配对差异、学习外子集和分离成本，不导出Skill、提示词、原始代码或私有API缓存。
- 报告及自动导出专测26项通过，含假时钟的有限等待、终态出现、旧快照保留、目录隔离及零模型调用；与前述测试有重叠，不累加为独立效果样本。文档构建测试因本机缺可选依赖跳过1项（exit5），不计通过；已单独检查本次三个文档的相对链接与代码Ruff。

## 运行与接手

Linux源码：`/root/continual-skillopt-generalization-20261002-d-source`；研究输出：`/root/continual-skillopt-generalization-20261002-d-study`；tmux：`skillopt-generalization-20261002-d`。只读观察器`skillopt-observer-20261002-d`每60秒采样、最长12小时，不自动重抽或修改实验。

另已启动`skillopt-generalization-report-d`：新终态触发报告，长任务每15分钟快照，60秒检查、12小时截止；在截止前发现合法`final.json`即导出最终比较并退出。输出`/root/continual-skillopt-generalization-20261002-d-reports/`，`latest.json`指向最新`snapshot-NNNN/report.md`及JSON。若到时实验尚未结束，保存`watch_deadline_reached`而不是伪称最终报告；实验队列本身不因观察器结束而停止。

入口：[队列](../scripts/run_skillopt_generalization_linux.sh) · [协议配置](../configs/continual_learning/fivebench_sequence_v2.pjlab.json) · [报告器](../scripts/report_fivebench_generalization.py)。

不要再次执行启动shell覆盖现有目录。断网/本机休眠不会终止Linux后台队列；重新连接后先核对tmux、闭合回执和终态。是否完成以学习`result.json`、阶段`stage.json`及最终`final.json`为准，不以进程退出或矩阵文件数量替代。

报告导出到**新的、研究目录外**的路径，例如在冻结源码下运行：

```bash
PYTHONPATH=. /root/continual-alf-prep-20260928/env/bin/python \
  /root/continual-skillopt-generalization-20261002-d-report-ops/report_fivebench_generalization.py \
  --study /root/continual-skillopt-generalization-20261002-d-study \
  --output /root/continual-skillopt-generalization-20261002-d-report-NEXT
```

当前尚无本轮五阶段完成结果。后续结论以完整配对结果为准，不能预设成绩会逐阶段单调提高。

## 本次GitHub发布核验

本地完整研究CI命令：4,441 passed、15 skipped；从暂存文件导出的干净源码树：97项队列/恢复/报告检查通过。另在独立临时文档环境完成17项发布边界测试及严格MkDocs构建，源码树构建也通过；这补充了此前主环境缺MkDocs的跳过记录，不改变历史实验结论。发布范围经过密钥及数据边界审查，仅包含源码、测试、配置、报告和脱敏摘要，不含`.env`、原始API缓存、工作簿或benchmark标准答案。
