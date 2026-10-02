# 当前完整流程：Skill 与验证器如何协同进化

**10/2 22:22状态核验：新D前三来源Pending，KOR在运行。** Coding反思出现HTTP200但流交付不完整，Sheet新v7路径返回`native_exception:SystemExit`，QA触发服务内容过滤；三者携空父继续，完整学习仍0/5，已闭合的15个矩阵格仅引用旧No-Skill。不会将97项工程测试、23项评分资格或空策略相等解释为泛化收益。详见[最新原因与成本](skillopt-generalization-20261002.md)及[完整脱敏快照](results/skillopt-generalization-progress-20261002.json)。下述21:32启动信息保留，实际完成状态以绑定终态为准。

**10/2 21:32：修复后的正式规模 SkillOpt 五域补跑已启动。** 新队列版本 `fivebench-sequential-attempts-v2` 通过 [v2配置](../configs/continual_learning/fivebench_sequence_v2.pjlab.json) 显式创建 `continual-learning-v4`，不覆盖下方旧C尝试。输入为原五域已暴露开发面板、按任务族哈希冻结的 train/selection、空初始Skill及预算；顺序 Coding→Spreadsheet→SearchQA→KOR→ALF。每阶段走原生反思/合并/排序/编辑/来源选择门，输出选中Skill或原父、收费及执行回执，再用**原No-Skill的模型服务、源码、运行环境、评分器和全部2,838个位置**评测五域，之后才进入下一来源。全域成绩不反馈给学习器；同策略同评测身份链接既有观测。

学习端单独绑定3600秒长响应服务和有限恢复，Spreadsheet使用新源码下23/23控制通过的v7数值视图；评测端仍保持原配置，不只给SkillOpt换裁判。反思/API上限在结果前分别设为64/12,000，覆盖两轮KOR反思及ALF动作；metric512、两更新、solver65536/reflection4096、报告token停止阈值600万。学习串行，若选中新策略，全域生成最多10并发；锁等待后和每阶段前重验冻结文件。不是SkillOpt论文默认完整复现，也不是Research方法分支。

[只读报告器](../scripts/report_fivebench_generalization.py)把每阶段学习终态、五域P/F/U/待评分、相对No-Skill配对胜负及成本分开，并排除所有计划学习任务族另报子集。Spreadsheet/ALF的本面板全部进入计划学习，**不存在这两域的学习外留出题**；其余留出也属历史曝光development，不能称独立最终泛化测试。Linux队列和60秒只读观察器已启动；报告器另以`--watch`最多12小时在研究目录外保存不可覆盖快照，阶段/最终结果出现时导出，长任务每15分钟记录进度；只更新`latest.json`指针、不调用模型或自动恢复任务。启动/校准与工程测试通过不代表阶段完成或方法有效。[本轮协议、进度与对比](skillopt-generalization-20261002.md)。

**10/2晚：学习阻塞修复进入显式v4。** 输入仍是冻结的开发train/selection、父Skill和预算；新增[recovery.py](../skillopt/continual_learning/recovery.py)规定评分前最多一次length增预算恢复及有限provider-network重试，输出保留每次原始回执、逐HTTP成本和恢复父身份。过滤、缺usage、未闭合流与最终unknown仍不能生成失败反馈。原生反思/合并/排序/编辑/gate不变；[严格JSON桥](../skillopt/continual_learning/reflection_json.py)只修非法转义的字面表示，原响应不动，审计进入阶段哈希；不再依赖可选宽松解析库。v1–v3不自动启用这些行为。

工作簿新显式`qualified_lo_recalc_v7_v1`在评分前校验新源码的23项独立资格，输出保持公式/数值的读取视图和可回放评分；已在原SkillOpt未知产物上恢复明确fail，非提分。ALF通过[launch.py](../skillopt/continual_learning/launch.py)在串行启动边界绑定/恢复冻结数据目录，Linux真实reset+一步+清理已通过。新[小闭环入口](../scripts/smoke_skillopt_recovery.py)已在独立目录完成Coding/QA/KOR各一轮，每域2训练＋2选择；24调用、36,102 tokens、0unknown，三个候选均被gate拒绝，完整缓存回放不新增调用。这只是工程smoke，不是正式方法效果。正式五阶段队列的v1配置仍产生v3，不能把新增代码当成已部署到旧运行。[修复报告与启用边界](skillopt-blocker-repairs-20261002.md)。

**10/2傍晚新增：五域 baseline 学习接续。** [接手指南](agent-start-here.md)给无上下文代理提供入口；[本次实录](baseline-continuation-20261002.md)区分已完成、启动中和待运行。新增显式 `continual-learning-v3`：输入冻结的域内 train/selection 面板、父 Skill、共同模型/预算，输出原生 SkillOpt 或官方 GEPA 选择结果、公开反馈轨迹与收费回执。SearchQA/KOR使用公开文本，Sheet只向反思器提供任务要求与生成代码，ALF只提供有标记裁剪的公开交互；私有测试、参考工作簿和专家行动不进入提示词。旧v1/v2仍只支持Coding，协议和结果不变。

[continue_fivebench_baselines.py](../scripts/continue_fivebench_baselines.py)将五个来源阶段串联：冻结所有任务族角色/顺序/预算 → 学习 → 选中或保留父文本 → 每域原冻结环境评测 → 下一阶段。completed/no_update可继续；已闭合、安全交接的Pending也可携父尝试下一域，但最终明确计作未完成学习。开放调用、缺执行回执或清理未确认必须停队列。父阶段哈希与文本分别绑定；相同策略在同一冻结评测身份下只链接既有结果，不产生新重复或学习收益。真实服务身份与返回模型、阶段及评测证据在续跑时重验。

本轮任务仍取已暴露开发面板，训练/选择与全域矩阵存在明示交集，不是独立final。矩阵不回流给learner，两个原算法baseline不等于Research协同进化方法已完成。新循环离线测试已通过，Linux相应65项通过；10/2 17:51已实际启动SkillOpt五阶段后台队列，GEPA随后执行，首批真实调用/原生评分已落盘。完成状态和成本以本次实录及实际回执为准，不称为五阶段已完成。

旧C先前三域均Pending携空父；10/2晚复核终态为五域全部尝试、完整学习0/5，25个矩阵格都引用旧No-Skill，不是新泛化观测。Coding第二轮的非法JSON转义曾暴露活动环境缺可选`json_repair`，未静默安装或改写旧状态；后续v4改为源码绑定的严格词法桥，已在独立smoke完成真实更新链路。本页开头的新D是新协议完整规模补跑，不能解除旧C的Pending。[旧原因及边界](baseline-continuation-20261002.md) · [新运行](skillopt-generalization-20261002.md)

未知修复新增两个独立入口：[被动链接回放](../scripts/replay_sheet_passive_links.py)先验证原字节资格，再候选原字节离线重算；独立读取视图只恢复原有但导出丢失的hover tooltip，不改公式、缓存、地址或原文件。A资格39/41拒绝保留；B经41＋18＋2资格后完成160份旧产物重评，仍79/55/26，134个旧已知全保持、没有额外覆盖收益，不替换学习v5评分器。[围栏产物接冻结H](../scripts/replay_fenced_with_frozen_h.py)则只输入唯一已保存56786/r1修复产物与原C参考清单，输出新单位置回执及内容fail；不再调用模型，也不把组合诊断并入原基线。

随后v9c增加有明确前提的独立display比较视图：只恢复“原属性等于href、导出属性等于前后未变显式文字”的变换，保留真实地址/文字/公式/缓存及所有旧保护。CLI v3必须复用B原41样例，另增2个实际触发恢复的正负控制，重新通过43＋18＋4资格后才能重评。实现、独审与Linux159项离线测试通过；真实资格及160回放在独立后台队列等待两baseline安全终态，**当前没有新增恢复分数**。[排队边界](results/passive-links-c-queued-20261002.json)

更新：2026-10-02。同配置GLM-5.3 low/65536五域新基线全部完成：BigCodeBench 400 pass/399 fail/1 unknown，SearchQA 560/234/6，各400题×2、均0截断；KOR全500×2为746/243/11，ALF39×2为65/13/0，Sheet80×2为63/44/53。共1,419题×2，[聚合数据](results/noskill-fivebench-long-20261001.json)保留分母与不完整成本。Sheet只有107/160可判定、Coding新环境资格仍Pending，不能把运行完成当环境完全修好。GEPA候选28/64、SkillOpt有限重提31/64、条件化归纳shadow32/64均未超过共同空父33/64，无新S1；普通归纳34 pass/29 fail/1 unknown，原Pending不改。重复波动下的小分差不是方法效应。下一步优先接入可信具体反例反馈；公式预览与ALF日志另有已测试、未部署的新版本。旧工作簿v5重评61/46/53与新模型基线分开，均非Skill泛化收益。[夜间监控与修复](overnight-baselines-20261001.md)

**10/2午后最新终态**：aTrust恢复后零API续跑，Sheet冻结参考标签H v3经34项引擎＋18项评分资格，完整80题×2为**79 pass/55 fail/26 unknown**，相对v8b70/48/42恢复16位置（9 pass＋7 fail），原118个已知全保持。H只读保存缓存、不宣称新鲜或绝对真值，候选仍独立重算。交付分轴另有回顾性79/61/20，仅5程序缺陷＋1闭合预算耗尽计交付失败，内容分不改；16候选兼容、2参考争议、2契约/提取问题仍未知。负对照B为51/41/68并保留；不替换原基线或学习评分器。[午后完整数据与限制](unknown-recovery-results-20261002.md#午后恢复冻结h参考标签与交付分轴)。

**10/2早间修复终态**：KOR截断子集10/10闭合，7 pass/2 fail/1 unknown；残留一次completion耗满131072，说明扩大上限不保证交付。Sheet原63/44/53经v7重评63/46/51，再经34项资格通过的v8b全160重评为**70/48/42**；累计11 unknown恢复（6道任务），原107个已知结果全部保持，0新API。当时剩余34个兼容位置＋8个冻结原未交付，不把新答案偷偷混入。围栏修复另成功交付但参考仍unknown；唯一截断一次恢复判fail。原5个运行unknown已归因为程序缺陷，1个缺文件涉及VBA/工作簿契约歧义；旧基线和拒绝资格不改写，v8b也不自动成为生产/学习评分器。[完整结果](unknown-recovery-results-20261002.md)；[续跑快照](unknown-recovery-resume-20261002.md)及[10/1暂停快照](unknown-recovery-pause-20261001.md)保留。

9/30 17:54暂停后，Linux任务独立完成；10/1已恢复SSH并核验终态，没有关闭或重启Clash。此前暂停快照保留在[交接记录](evaluation-environment-recovery-20260930.md)，当前状态见[10/1环境报告](evaluation-environment-recovery-20261001.md)。

本文是**当前流程的主文档**：实现或数据流改变时同步更新。实验数字集中维护在[结果与经验账本](results-and-lessons.md)，历史协议和日期报告原样保留。[研究索引](research-overview.md)用于查找历史材料。

**环境恢复入口**：[truncation_recovery.py](../skillopt/continual_eval/truncation_recovery.py)的`prepare-environment`输入完整冻结v3父记录，输出v4长流式协议。E/F终态分别6 pass/7 fail/3 length、0 pass/3 fail/4 length。新`prepare-ceiling`只接纳完整v4父运行中确证HTTP200/length且流正常结束的位置，另冻v5：131072/read300/每HTTP wall3600；G纳入E的3份，H纳入F的4份，不重抽完整错误或开放调用，不回写旧分数，也不支持v5再升级。G为1 pass/2 fail，H为2 pass/2 fail，均完整；实际生成全部低于65536，没有等预算重采样对照，不能归因于增加上限。结果分层而非合成统一预算成绩。原目录`pause/run/report`支持恢复器协作暂停与回放，但不代表学习优化器也可恢复。[本轮协议与结果](long-response-baselines-20261001.md) · [已完成E/F](evaluation-environment-recovery-20261001.md)。以下带历史日期的节点保留当时状态。

## 1. 目标与当前完成程度

**10/1完整基线 unknown 的独立恢复**：[新诊断入口与状态](unknown-recovery-20261001.md)把交付问题、固定程序运行问题、工作簿兼容限制分开。`recover_full_delivery_unknowns.py` 输入完整冻结 No-Skill 面板与已闭合失败回执，只为 KOR length/network 两层各提供一次指定预算机会，输出独立调用与原生评分；SearchQA 内容过滤只归档。`replay_native_unknowns.py` 输入绑定原代码/输入/镜像的产物，零 API 输出有限异常证据，不能把交付诊断当作语义 pass。执行共享原生锁、先写意图、拒绝开放意图重抽，清理未确认立即停止；原始分母及旧分数不变。Sheet v6 另有窄范围数值比较视图及预解析 ZIP/XML 检查，须新资格和全 160 位置重评后才能讨论覆盖收益，目前尚未授权取代 v5。

新求解配置还可显式指定 `runtime.<coding_benchmark>.code_extraction_version="explicit-python-fences-v1"`，接入 [code_delivery.py](../skillopt/continual_eval/code_delivery.py) 的逐行围栏解析：一个明确 Python/py 块优先于 Excel 等说明块，多个 Python 块或未闭合围栏返回 unknown，不按能否编译或评分选代码。原文字符片段、哈希和提取结果随产物保存；提示词和预算不变，不修补模型程序。默认仍为历史提取行为，新选项及源码进入新 plan 身份。该问题来自真实工作簿日志；新 profile 的 95 项联合 fixture 已通过，现有冻结基线尚未重跑或替换。

10/2 [replay_fenced_delivery.py](../scripts/replay_fenced_delivery.py)已真实走完完整160回复审计→选择唯一实质提取变化的旧unknown→同回复代码在原隔离容器执行→原资格评分器重评。取得共享锁后再校验源码/资产，实际输入字节绑定冻结哈希，不能在等待期间悄悄换输入。该题工作簿交付恢复，但参考兼容问题使语义仍unknown；0模型调用，不合并为基线提分。旧日志、原提取和新提取均可追踪，缓存回放不重复执行。[结果](results/unknown-sheet-fenced-replay-20261002.json)

[recover_sheet_length.py](../scripts/recover_sheet_length.py)补齐完整Sheet面板唯一closed length的位置：原提示词先用旧截断回执重建核对，外部API只调用一次；生成与原v5评分在共享native锁内执行，分别核验镜像/清理并计成本，缺失回执不补抽。131072只是新独立诊断预算，不改旧基线。该入口真实结束为完整交付后fail。新只读监控v4分别识别`full_delivery_recovery`和`single_delivery_recovery`的账本布局，保留在途和缺usage，不能自行恢复或产生部署授权。

新[sheet_recalc_v7.py](../skillopt/continual_eval/sheet_recalc_v7.py)仅修复Calc把原General公式读成日期的问题：输入原工作簿及独立重算产物，输出单独的数值读取视图和适配回执。仅在原公式逐字一致、数值缓存有限、无格式观察行为等条件下调整样式属性，不改公式、数值缓存或原文件；原本的日期仍按日期比较。`replay_sheet_v6.py --engine-version v7`先严格复用旧20控制的输入字节/expected，再增加3个日期及错误数值控制，单独冻结23项资格；通过后才允许原80题×2全量零API回放（含旧pass/fail），未交付仍unknown。v5的参考漂移/不支持内容保护继续有效；这不是Excel全语义等价证明，也不直接启用生产评分或学习反馈。

**10/2受限函数适配（v8a被拒，v8b已完成资格与回放）**：[sheet_recalc_functions.py](../skillopt/continual_eval/sheet_recalc_functions.py)的首次实现将两个真正函数token的`_xlfn`别名转成标准函数名，用独立执行视图计算；真实资格27/34拒绝，发现命名空间丢失会让Calc算出错误函数缓存。该执行转换不获授权，也不能只放宽大小写比较。v8b保留原工作簿/公式字节执行；临时去前缀副本只供完整安全预筛，随后销毁，不能挂载执行。薄隔离driver复用v5固定镜像、worker、限额与清理，继续绑定原输入的数值证明、回执、原内容保持和参考缓存漂移。命名表达式、观察公式/格式的程序、动态数组、宏和外链继续保守拒绝。新增48项模块测试、独立安全审查通过，旧源码及[失败资格](results/unknown-sheet-v8a-qualification-20261002.json)保留，不被修订覆盖。

`replay_sheet_v6.py --engine-version v8 --prior-profile-qualification <q23>`严格复用原23控制的输入/预期并全部重新执行，新增11项函数、数组、错误传播和不适用控制；只有新34项全部通过，才允许新目录完整重评160位置。**v8b真实34/34通过**（28容器65.267648秒），随后全160回放70/48/42，200回执/190容器1030.222882秒，均0API/开放/清理未确认。6题12位置通过函数初筛，其中9位置恢复、3位置仍被后续重算内容/公式保持检查拦截（包括错误字面量变成公式及数组错误），不能仅放宽拼写比较；原命名表达式限制不放宽。修订后完整离线3914通过/9跳过，独立170项相关回归通过。入口输出新协议/资格/位置结果/终态，不覆盖旧结果、不自动供学习反馈；未交付仍保留在分母。[资格](results/unknown-sheet-v8b-qualification-20261002.json) · [全量结果](results/unknown-sheet-v8b-replay-final-20261002.json)

目标不是每个 benchmark 都最高分，而是学到有增量收益、较少负迁移的 Skill：验证其底层机制、成立条件和例外，再根据行为证据决定是否接受、限制或扩大适用范围。

**10/2后续评分协议（不替换v8b）**：[sheet_frozen_gold.py](../skillopt/continual_eval/sheet_frozen_gold.py)将原数据集参考缓存作为宿主私有H：输入原参考字节哈希、目标区域、数据来源及已知争议，输出可序列化的缓存完整性清单。普通空白、公式空字符串、缺缓存、共享公式与固定数组的从属结果分别检查。v3仅支持严格关系/MIME/命名空间/计数链、单记录XLDAPR、cm1单格array与显式保存缓存；带元数据时目标缺cell或缺值不能推断为空白。多格动态spill、未知元数据、无效共享公式和已有参考冲突仍不合格。这里仅证明冻结标签存在，不声称缓存新鲜或答案绝对正确。随后只把原模型工作簿交给独立资格化的v8b执行器，保留全部候选内容/公式/数值检查，H不进入容器或模型。该前处理不同于旧双重重算，必须另开目录和协议。

[replay_sheet_frozen_gold.py](../scripts/replay_sheet_frozen_gold.py)提供`qualify-score → prepare → run/report`：先核验新源码位置的34项引擎控制，再执行新评分控制（包括伪造正确旧缓存必须重算为失败、H缺缓存不得因别格错误判fail），之后才允许同80题×2全部冻结产物重评。首次13项为12/13拒绝：候选False字面量被Calc改为公式，旧引擎不支持；原源码与失败资格保留。v2用支持的公式候选检验H中0/False完整性，另增加候选布尔字面量必须unknown的控制，合计14项，不放宽引擎。输入原v8b完整160位置、回执和库存；输出原分数/v8b分数/新评分转移、H清单、隔离成本。没有新模型调用、不挑可评分子集、不自动供学习反馈；旧未交付在语义轴仍unknown。**14:05用户恢复aTrust后，确认无遗留评分启动，再补执行14项评分并全部通过；完整160已在Linux后台开始。** H中23/80参考因全局元数据限制被拒、1份有既有争议，该覆盖问题单独复核，当前运行不改协议。[断点与命令](unknown-recovery-resume-20261002.md)

[delivery_outcomes.py](../skillopt/continual_eval/delivery_outcomes.py)另提供交付—内容—归因分轴：输入绑定原任务/重复/预测/调用/代码/诊断身份的闭合观察和审阅归因，输出交付状态及未改写的内容分。异常名本身不能证明模型责任；已核实的程序错误、完整流预算耗尽、服务/环境故障、契约歧义和解析错误分开。此接口不运行或修正答案，实际历史数据侧车核验及新端到端统计另行保存，不覆盖旧评分。

**午后B→C验证终态**：B的v2全160为51/41/68，元数据全局拒绝造成44个交付位置未知，33旧已知退回unknown；负结果保持。v3经91项本地相关测试和独审、C引擎34/34、评分18/18真实通过，全160为79/55/26，原v8b118个已知保持；H 79份可用/1份争议，候选仍有16兼容限制。[report_sheet_delivery_outcomes.py](../scripts/report_sheet_delivery_outcomes.py)已分别对B、C完整160位置执行原调用/代码/诊断/评分身份核验，输出交付152/未交付8及独立回顾性端到端口径，内容分不动；5程序缺陷＋1闭合length算交付失败，契约歧义和提取bug仍未知，C端到端为79/61/20。侧车78项自测、10项独审通过，完整离线回归4093通过/9可选依赖跳过；两轮均0新API/开放/清理未确认。[本轮数据与限制](unknown-recovery-results-20261002.md#午后恢复冻结h参考标签与交付分轴)

**目前有可组合的实现、真实的局部实验和工程闭环，但还没有完成“新生成任务上的规则学习＋获授权 Research 验证＋跨域推广”的真实端到端验证。**

| 部分 | 当前已有 | 尚未完成或证明 |
| --- | --- | --- |
| Skill 内容学习 | 明确空初始化/来源导入；条件规则更新；真实修复轨迹已产生候选并完成后续执行 | 新任务上稳定的语义增益；来源训练父版本接入课程；跨域提升 |
| 验证器进化 | 条件 Rubric、资料研究、检查实例化、执行前审阅、独立校准接口 | Research 相对无资料对照的可靠信息增量 |
| 协同进化 | 历史 V16 实际发生多轮 Skill/验证策略更新；新双门闭环通过工程控制实验 | 真实自然数据上“新增有效检查→更好 Skill→更好准入”的完整证据链 |
| 历史驱动课程 | 全量开发摘要→能力目标已真实调用；6 个模型生成任务家族通过隔离资格检查 | 公平的 Generic/Targeted 学习对照尚未完成，A–D 均在准备阶段 Pending |
| 同课程机制归纳 | 44族资格与3历史完整确认已完成；local出现少量交付/产物可用性改善，mechanism全no_update | 未证明机制策略优势；只覆盖Coding，且无有效条件禁用 |
| 范围控制 | 当前 Coding 的 Local Commit / Restrict / Reject / Pending 接口 | Cross-Domain Commit、自动 Split、自然跨域部署授权 |
| 共同求解协议 | 9/27可靠配置统一初稿/修订预算、格式、一次修订和公开回归保护；真实工程验收完成 | 新配置下的独立方法比较；不能用工程smoke推断总体通过率提高 |
| 五域持续评测 | 导入→冻结检查点→公开求解→独立原生评分→6×5矩阵；No-Skill全1419题×2齐备；10/2新增原生baseline五阶段调度并已实启 | Sheet原基线覆盖107/160，新H诊断134/160不回写；Coding新环境资格Pending；尚无五阶段真实学习终态、非空被选S1全域结果或独立final，旧Pending不因诊断解除 |

以下把**应该如何连接**与**哪些入口实际连接了**分开说明，不能把不同实验拼成一次已经成功的运行。

**10/1交互反馈的日志补齐（仅工程验证）**：ALF全78轨迹复盘发现每episode最后一步的动作后观察未保存。新[backends.py](../skillopt/continual_eval/backends.py)显式选项`runtime.alfworld.alfworld_trace_version="alfworld-public-transitions-v1"`将实际返回的公开观察写入宿主trace，区分complete/truncated/missing、保留原长，最多12,000字符；step或cleanup异常不补造观察。模型仍只见原observation/action的最近5步，完整system/user字节、动作、预算及评分不变；不添加reward、won、专家信息。默认legacy不启用，选项绑定新plan身份，25项新fixture及95项联合回归、双review通过。**未部署到本轮Linux冻结源、未重跑78或生成Skill，不能修复旧日志缺失。** [真实诊断](results/alfworld-public-trajectory-audit-20261001.json)亦说明成功轨迹会有无效行动，不能直接把中间事件升级为语义错误。

### 9/23–9/27：本阶段实际新增了什么

- **初始化与演化边界**：区分可追溯但弱的历史父、空规则包与来源训练导入；规则更新绑定父版本、公开证据、适用条件和例外，不因文本写得通用就获得更大授权。
- **可用于学习的反馈**：由最终布尔结果扩展到全量配对摘要、逐例观察、初稿→修订轨迹；被修复或被回退的错误经验不再随最终成功而消失。F→T已真实走完“修复证据→规则提案→冻结→后续任务执行”，但没有Research参与，也未证明正迁移。
- **验证反馈的质量控制**：先审查测试依据和适用性，再执行；具体外部事实缺口有有界Research接口。盲审有真实过滤错误检查的信号，按缺口Research的独有增量仍待新数据验证。
- **公平、可归因的共同执行**：将交付失败、语义失败、执行未知分开，并把预算及修订保护统一给Base和候选。它减少实验混淆，不应记作某个Skill独享的方法改进。

对应证据与局限见[结果账本](results-and-lessons.md)；完整归档见[9/23审阅](skill-validation-admissibility-20260923.md)、[9/25学习与归因](skill-validation-mechanism-study-20260925.md)、[9/27可靠性验收](skill-validation-solver-reliability-20260927.md)。

## 2. 先区分六个对象

| 对象 | 是什么 | 不是什么 |
| --- | --- | --- |
| 任务契约 | 原任务要求、公开例子、输入输出约定、必须满足的义务 | 可以由 Research 为提高分数随意改写的标准 |
| Skill | 给 Solver 的可复用解题指导；新表示是带条件、例外和证据引用的规则包 | 模型参数训练，也不是题目标准答案 |
| 可复用 Rubric / 验证策略 | 检查什么义务、何时适用、需要什么证据、如何生成及汇总检查 | 某一道题的几个测试输入 |
| 任务级检查 / probe | 把冻结策略应用到具体任务后得到的调用、预期结果或关系 | 新 benchmark 任务，也不自带正确性保证 |
| Research | 针对验证知识缺口查阅限定资料，提出或支持检查 | 最终评分 oracle；目前也不是开放式长程 DeepResearch Agent |
| 能力任务家族 | 为某项待检验能力生成的新任务及契约变体，用来学习或确认 | 给原题多加几个输入；与 probe 生成是两个模块 |

## 3. Skill 从哪里来、数量多少、如何调用

### 初始化

[skill_seed.py](../skillopt/skill_validation/skill_seed.py)提供三种来源接口：

| 来源 | 输入 → 输出 | 当前用途 |
| --- | --- | --- |
| `cold` | 学习历史 ID → 空 Skill / 空规则包 | 9/25固定面板对照已实际使用共同空 `RuleSkill`；9/24历史目标课程A–D仍未进入真实学习 |
| `source_trained` | SkillOpt 源域 best/checkpoint、宿主审阅的来源与选择声明、文件哈希 → 冻结 seed | 导入与测试已实现，尚未接入当前课程 driver；不按 final 选父 Skill，不自动认证训练效果或转换成结构化规则 |
| `legacy_diagnostic` | 历史文本与来源指纹 → 诊断 seed | 保留弱父版本，不能冒充成熟、独立验证过的源域 Skill |

9/22–23 自然实验的 Current 来自 **V16 第一条历史、第一轮、fixed 分支**：模型从空文本、两道合成 Coding 题的轨迹中生成。它可追溯，但不是 SkillOpt 充分训练后选出的 best Skill。[来源核对](skill-validation-feedback-repair-20260923.md)

历史目标课程`curriculum_study`仅把该旧父及其历史当作**发现假设的背景**。driver 设计为让 Generic 与 Targeted 都另从相同空规则包开始，重新收集各自证据；该入口真实试跑尚未到达学习阶段，旧父的产物不能作为新父的行为证据。另一个固定面板入口`mechanism_study`已完成真实空父更新，两者不能混称同一次课程实验。

### 优化对象与调用

- 一条学习历史维护一个 Current 规则包，再生成 Candidate；不是大量独立 Skill 等待向量检索。
- [RuleSkill](../skillopt/skill_validation/rule_skill.py)最多 8 条规则、渲染不超过 6,000 UTF-8 bytes；每次最多 2 项新增、替换或删除。规则包含机制、操作、适用条件、例外、scope 和证据引用。
- 固定 JSON 交付要求、工具权限和一次公开修订机会属于执行协议，不作为“学出的 Skill”。
- [rule_solver.py](../skillopt/skill_validation/rule_solver.py)将规则渲染为文本交给 Solver。`raw` 使用全部规则；`conditional` 仅按执行前公开义务类型筛选，不是学习型语义路由，也不等于获得部署授权。
- **历史目标课程配置为用 `raw` 强制使用候选**，以观察内容本身的收益/损害；该入口尚未产生真实确认成绩。固定面板A/C另有已完成的raw/conditional比较，T为raw；不按隐藏成绩选择是否启用Skill。
- 冷启动 Current 与 No-Skill 文本完全相同；相同请求可共享缓存，不能称为两次独立学习证据。不同版本/实际注入文本均绑定各自哈希。

## 4. 数据与证据边界

| 数据用途 | 输入与允许用途 | 禁止用途 |
| --- | --- | --- |
| `development` | 发现缺口、产生 Rubric/Skill/适用条件候选 | 把开发效果当独立泛化成绩 |
| `verifier_calibration` | 冻结验证管线后决定是否授予限定反馈权限 | 按结果反复改同一提案直到过门 |
| `verifier_audit` | 冻结后独立评价验证器判断质量 | 回流修改待评验证器 |
| `skill_confirmation` | 冻结 Candidate 与范围后进行配对准入 | 用确认结果改范围，再用同批数据宣称已确认 |
| `final` | 评价冻结 Skill、验证器和部署决策 | 决定当次路由、修改 Skill 或门槛 |

这是用途划分，不代表每个历史实验都有五套数据。9/22 自然先导为 **64/24/24/40** 四分区（开发/验证器校准/Skill 确认/final），没有额外独立 verifier_audit。最新课程只有开发与共同确认的 shadow 对照，未接入正式两道门。

可见证据 **V** 包括公开契约、允许查看的代码和公开执行回执；独立审计 **H** 包括隐藏检查、参考实现结果或人工核验。验证与更新使用白名单视图，不把整个宿主记录放进 prompt。开发 H 的漏检/误判摘要只有专门接口可以使用，必须标成“宿主开发诊断”，不能归功于 Research 自主发现。最新历史课程规划只读公开 V。

原任务/近重复族强制隔离；项目隔离仅在 `project_disjoint=True` 时启用。重复执行、同题三种 Skill 条件、家族内条件变体不是独立新任务。消费锁作用于当前 ledger/output，跨实验目录仍需统一曝光记录；新建目录不使旧数据重新成为独立数据。来源区分真实模型、fixture、人工 mutant、生成规格；旧记录来源不完整不能用来正式验收。[可见视图](../skillopt/skill_validation/views.py) · [分区实现](../skillopt/skill_validation/partitions.py)

## 5. 主线 A：从历史表现到更有针对性的 Skill 学习

当前入口：[curriculum_study.py](../skillopt/skill_validation/curriculum_study.py)。下面是该入口已经写好的顺序，**不是本次真实运行已经走完的顺序**。

| 步骤 | 输入 | 处理 | 输出 / 当前状态 |
| --- | --- | --- | --- |
| A1 回放历史 | 旧父版本、development 任务/产物/公开回执 | 校验绑定，汇总所有配对，分层展开案例 | 64 题×2 次的 128 对摘要＋10 对详情，已有真实记录 |
| A2 定义能力目标 | 同一公开历史、固定执行协议 | 模型列失败假设、竞争解释、证据与所需任务角色，可 no_update | 1–3 个能力目标；真实调用已完成，不把单次失败判成 Skill 过拟合 |
| A3 提议开发课程 | Generic 不看目标；Targeted 看预登记的首个历史目标 | 模型选择受限操作规格，宿主编译任务 | 每臂默认 6 个结构家族；真实生成存在格式/预算失败 |
| A4 资格、隔离与冻结 | 两组开发规格、随后生成的共同确认规格 | 参考实现交叉核对、控制产物、结构/有限行为去重 | 冻结任务池；两组开发可重叠但须报告，开发与确认不得重复；完整步骤目前仅 fixture 贯通 |
| A5 开发求解 | 同一空父、各臂开发任务、相同执行预算 | No-Skill/Current 求解，公开执行，再给一次修订机会 | 最终产物、初稿/修订稿、公开证据、调用成本 |
| A6 汇总反馈 | 与当前父版本匹配的全部开发配对 | 全量摘要＋预算内详情，区分改善/回归/共同失败/unknown | 更新器可见反馈及证据目录，不含 H 答案 |
| A7 更新规则 | 父规则包、公开反馈、相同 updater | 最多两项编辑；核对父哈希、引用与 scope | 新候选 / no_update / invalid；元数据变化不计行为学习 |
| A8 共同确认 | 冻结 Generic/Targeted 候选、共同确认任务 | No-Skill 与两候选强制使用，各自干净执行，之后宿主 H 评分 | 配对胜负、逐族结果、unknown 与成本；真实试跑尚未到达 |

历史摘要由 [development_feedback.py](../skillopt/skill_validation/development_feedback.py)形成，能力目标由 [capability_goals.py](../skillopt/skill_validation/capability_goals.py)提出，规则由 [rule_learning.py](../skillopt/skill_validation/rule_learning.py)更新。还有 `whole_text` 更新对照接口，但最新课程比较的是 **Generic vs Targeted 课程**，不是规则式 vs 全文式 Skill 的真实效果实验。

目标规划另存一个删除历史结果/代码的 `outcome_blind` 消融；它仍使用同一批历史案例契约，不是完全随机选题的无历史基线，也不是额外完整学习臂。

### 任务究竟怎样生成

[curriculum_tasks.py](../skillopt/skill_validation/curriculum_tasks.py)目前只支持有界整数列表 DSL：过滤、变换、排序/去重、聚合；模型选 2–3 个操作，不提交任意判分代码或标准答案。每个结构家族编译成三个完整契约任务：

1. 必须保留输入。
2. 必须原地修改为指定变换结果。
3. 不限制输入是否被修改。

输入范围是长度0–8、元素为−9到9的整数列表（不含bool）。每题4个公开示例、175个宿主审计输入，其中3个与公开输入重合。任务资格检查每规格使用176个输入×3个契约角色，共528次参考/角色比较，并检查错误返回、错误状态与正确替代解；这**不是528个独立任务，更不是Verifier Gate**。

默认开发每臂6家族×3契约×2次=36个配对，No-Skill/Current两条件共72个逻辑产物位置，冷启动同prompt可共享缓存。共同确认12家族×3契约×2次，在No-Skill/Generic/Targeted三条件下共216个评分位置。它们只是预定预算，不是统计充分性保证，也不是当前已完成数量。

目前覆盖同机制与状态条件反转；“不限制输入”不等于真正无关机制任务。尚无完整表面迁移、数学近似条件反转或跨域适配。生成目标超出 DSL 能力时必须报告缺口，不能拿代理任务高分代替目标达成。

### 反馈怎样改变 Skill

新规则必须引用当前开发证据，可新增、删除或条件化已有规则。替换同一规则 ID 时只允许保持或收窄语法 scope；扩大范围是待验证请求，不自动生效。证据引用正确只是来源保证，**不证明模型归纳正确**。

举例（说明机制，不是新增实验结果）：若任务明确要求保留输入，而代码原地排序，反馈应指向实际状态差异；更新可提出“显式要求保留时使用不变换原对象的实现，并检查前后状态”，同时保留“要求原地修改时不适用”的例外。不能从这次失败推出“任何任务都不能修改输入”。

当前课程仅使用注册公开检查，所有候选为 **shadow**：可以研究其原始效果，但未经授权不能宣称可以部署。Research 反馈臂仍为 Pending、未运行。

检查器新增独立状态观察版本：普通异常使返回义务失败，但仍根据调用后的真实输入判断状态义务；不能把“抛异常”自动归因为“修改输入”。MemoryError/TimeoutError等资源异常仍为unknown。5个真实Docker工程控制已通过；冻结历史检查器及原分数不改写。

公开修订适配器另有默认关闭的`allow_clean_timeout_revision=True`：只有来源绑定、隔离条件匹配且清理确认的公开执行超时，才可得到同样一次修订机会。反馈只说明“隔离调用未在预算内完成，语义结果未知”，不把超时判成算法错误，不放行SSH/容器一般故障或资源异常，不补答案、不重抽。真实单案例工程smoke已完成unknown→公开pass，回放不新增调用；它没有更新Skill、执行H或改变既有实验，不能算泛化效果。

另有默认关闭的`public_selection_policy="public_nonregression_v1"`。输入为同一任务初稿/单次修订的公开检查：若初稿pass而修订fail/unknown，则输出`retained`及原稿；完整保留被拒的修订、执行证据和已消费修订机会。没有H参与，不增加请求或检查，不能把公开pass当全面正确。新政策的反馈额外保留attempt代码与attempt transition，避免回退遮蔽错误经验；超时→pass仍为unknown转移而非语义修复。默认历史行为不变；真实C原响应的2次Linux公开重执行已验证保护，0新模型/0H，未改C分数。未来方法对照必须为所有Solver条件统一冻结该政策，不能仅对候选启用。

### 9/27 三项可靠性修复：统一求解配置，不改变评测标准

[solver_profile.py](../skillopt/skill_validation/solver_profile.py)定义显式的`reliable_v1`。输入为预先声明的配置、公开任务及当前规则；[rule_solver.py](../skillopt/skill_validation/rule_solver.py)冻结实际注入文本和配置后，输出初稿、公开执行证据、至多一次修订、选择结果及完整被拒尝试。

| 环节 | 新配置的行为 | 边界 |
| --- | --- | --- |
| 输出预算与交付 | 初稿/修订默认各4096 tokens；`compact_json_v1`提示完整、紧凑、严格JSON | 不抽取半截代码、不放松解析；不因失败自动加预算重抽；其他角色不扩额 |
| 一次公开修订 | 既有公开检查反馈；另允许隔离与清理均已确认的执行超时获得一次机会 | 超时仍为unknown，不放行SSH断连、普通容器故障；不读H |
| 公开回归保护 | 初稿pass、修订fail/unknown时保留初稿，记录`retained` | 完整保留被拒修订、成本和失败证据；公开pass不保证隐藏正确 |

两学习入口`mechanism_study`与`curriculum_study`均支持`--solver-profile reliable_v1`，在开发/确认、No-Skill/Current/各Candidate上统一生效。`--solver-max-tokens`只允许在运行前固定共同上限；Updater仍2048，课程规格生成仍6144。初稿的完整HTTP截断是终态交付unknown，不再被误当整个API服务不可用；真正网络失败仍停下核实。

历史调用默认仍为`legacy`，新行为必须用**新输出目录＋显式配置**，不会默默改变旧实验。协议、规则暴露、初稿及修订回执均绑定预算/格式；调用前检查实际API健康策略与两阶段预算，错配在付费前拒绝。同目录更换配置不能重新采样。下游`public_repair_feedback`按新元数据重建请求并保留attempt，旧F反馈重建仍逐字段一致。

[真实smoke入口](../scripts/smoke_solver_reliability.py)只检查工程链路：一个手工选定DSL家族的保留/原地/无状态约束三变体，各跑三条件，至多18次请求；Current/Candidate故意共用同一手写测试规则，不是学习实验。9/27 Linux Docker运行的9/9位置公开通过，12次唯一模型请求、0交付失败；完整结果与保护分支控制见[验收报告](skill-validation-solver-reliability-20260927.md)。这不证明通过率的统计提升或Skill泛化。

```bash
# 需已有.env及Linux上的源码快照/隔离镜像；不会修改评测集
python -m scripts.smoke_solver_reliability \
  --output outputs/skill_validation/reliability_new_run \
  --remote-repo /absolute/linux/source/snapshot

# 原学习命令在新的输出目录显式追加：
# --solver-profile reliable_v1
```

### 9/25 新对照：先固定课程，再比较如何学习

[mechanism_study.py](../skillopt/skill_validation/mechanism_study.py)是同一主线下的受控入口，不覆盖上述课程实验。输入为固定seed和任务预算；[任务目录](../skillopt/skill_validation/mechanism_tasks.py)编译开发30题、确认78题。相关家族分别8/24个，每个包含保留、原地修改、无状态要求三种契约；另各6个不同算法控制任务，仍全部为Coding。

数据流是：**完整面板冻结→Linux参考/控制资格检查→共同空父开发执行→同一公开反馈包→两种归纳策略各更新一次→全部候选冻结→共同确认→分区域配对统计**。默认3条请求独立历史×2次重复，共享任务面板，不把历史数当新增任务数。

A原始更新器读取的是**最终产物与最终公开检查**；初稿和修订记录虽已保存，该入口没有提供完整修复轨迹。包装检查主要返回布尔值。此限制已在下述F独立提案对照中接通，不能回写成A当时已经使用修复轨迹。

[local与mechanism更新](../skillopt/skill_validation/mechanism_learning.py)共用规则schema、证据、最多两项编辑及预算；仅后者显式要求对比失败、正确替代解、条件反转与保留行为。因此这是归纳策略对照，不是完整SkillOpt基线或规则表示消融。真实API格式smoke发现遗漏嵌套字段后，新共享提示增加完整骨架，不放松解析器或自动补答案。

确认同时保存`raw`强制使用与`conditional`公开义务筛选。前者评价内容，后者本拟评价禁用/覆盖；此次唯一规则的scope覆盖所有任务，两暴露完全相同，因此没有检验出条件控制作用，不能把回退收益写成Skill自身学会泛化。[统计接口](../skillopt/skill_validation/mechanism_metrics.py)保留Base/Current、未知和缺失分母、族聚类区间与成本；非劣诊断不签发授权。A已全部完成，主要差异来自输出截断和一例不终止代码，不是已建立的语义泛化；详见[9/25报告](skill-validation-mechanism-study-20260925.md)。

本轮没有使用Research新增反馈，也不评价历史目标选题；目的是避免再次把课程生成可靠性、学习策略和路由同时改变。

### 9/25 开发诊断后的薄修正（不写回冻结的 A）

- `mechanism_learning` v3将已有证据ID直接放进对应案例，并核对未标注内容的哈希；减少跨列表抄错，但**不认证引用能支持结论**。A中已发生一次语义错引，保留原样。
- `mechanism_tasks` v2按照保留／原地修改／无状态要求各自真正可观察的行为去重。固定有限输入上的469项仍不是语义独立证明；A沿用原747项目录，不中途换题。
- [public_case_feedback.py](../skillopt/skill_validation/public_case_feedback.py)对已注册公开例子逐一执行，输出期望、实际返回、异常和前后输入状态，再回放回执形成模型视图。它没有生成新题或Research信息；明确保持义务才能把状态改变判失败，缺少结构化原地修改后置条件则保留unknown。资源不足与语义错误分开。
- B反馈粒度对照使用同一批最终开发产物和同样的详情选择：原布尔反馈保留，实验臂仅增加绑定同产物的逐例观察；两臂同updater、同内联ID。B仍不包含初稿→修复轨迹。这里只能先检验提案质量，不能靠“更多candidate”证明泛化提高。
- [逐例候选确认入口](../skillopt/skill_validation/mechanism_case_confirmation.py)只回放预登记的第0次提案，全部冻结后对共同78题重新求解；不读取A确认成绩或复用其产物。相同题目仍是共享面板扩展，不是新独立数据；无更新的历史保留父版本，不挑其他重复中更好的候选。首次启动的输出截断被旧健康屏障误判为服务故障，已保留原记录；新v2协议显式区分模型交付失败与API服务故障，完整HTTP响应的截断仍记unknown但不阻断其他任务。C已完成3,744位置及逐回执复核；case_details净增9个通过均涉及交付变化，没有完整H语义胜负，也没有实际条件禁用。

### 9/25 修复轨迹进入更新：独立 F 对照

[public_repair_feedback.py](../skillopt/skill_validation/public_repair_feedback.py)读取A的公开初稿、公开执行回执和实际修订记录，严格回放任务/父版本/产物绑定；不读取H、不重新执行、不检索资料。输入180条独立请求轨迹（360个冷启动条件位置），输出全量公开转移摘要，以及按固定规则选出的最多6对详情；优先展开改坏、修好、未解决和unknown，并为未解决错误保留一个同题成功重复（若存在）。

两臂都看相同转移摘要、最终代码和引用目录；`trajectory`额外获得初稿与修订细节，`summary_only`没有这些细节。随后调用共同mechanism updater，各历史2次提案，预定只使用第0次；重复1只测稳定性。F真实12次提案已完成，2/3主历史的trajectory生成规则、summary为0/3，**这只说明产生了候选，尚不是效果结论**。新增规则证据仍集中于同一道区间边界修复，不能说已有多机制学习。

独立[源码修改难度诊断](../skillopt/skill_validation/patch_diagnostic.py)使用[24个固定任务](../skillopt/skill_validation/patch_tasks.py)：12个同作者小模块，每个有“保留旧默认行为”和“替换旧政策”契约，公开初始代码与4例；12个H案例只由宿主执行。No-Skill每题2次、同样一次公开修订，初稿/最终均48/48通过。该面板缺少正向提升空间，只适合作为目前候选的条件反转/非干扰诊断，不充当泛化成功证据或新独立校准。所有任务、失败和记录保留，不按成绩删题。

[repair_transfer.py](../skillopt/skill_validation/repair_transfer.py)已真实完成F主候选→固定24题→新No-Skill基线与候选求解→初稿/最终H分项。先重放全部12提案回执，仅取预定repeat0，再冻结并完成576位置；无规则的条件保留空父并报告缓存别名。只使用raw，不按宿主Near-Miss标签路由。实际注入规则的96轨迹全部通过，但相对Base的两项改善均为格式差。此次是已消费Coding开发集的探索性干扰诊断，不是已证正迁移、独立确认或获授权部署。

### 输出预算归因：不把交付差异当语义学习

[delivery_budget_diagnostic.py](../skillopt/skill_validation/delivery_budget_diagnostic.py)固定A的h0原始候选与完整78题，交叉No-Skill/候选、2048/4096输出上限，每题2次，共624个预登记新初稿请求。保留原提示词，所有请求先冻结、按固定顺序交错调用，全部初稿完成后才执行H；本诊断不进行公开修订、更新Skill或Research，不针对旧失败请求重抽。

输出分别给交付/解析/执行状态、已知结果下的配对差异、实际token和隔离执行成本。G已完成624次新请求及独立回执复核，显示输出预算确实影响原始分差。原提示词仍提及以后可能修订，而本次刻意只观察初稿，不能称完整Solver协议的复现；候选及面板来自已消费实验，不能称独立效果确认。运行中未按结果加题或改预算。

## 6. 主线 B：Coding Rubric 与 Research 怎样验证、怎样进化

Rubric 不直接给 Skill 文本打分，而是验证 **Skill 引导下的产物是否满足原任务义务**。同一批三条件产物的差异，才用于判断 Skill 的增量作用。

| 步骤 | 输入 | 处理 | 输出 |
| --- | --- | --- | --- |
| B1 找验证缺口 | 当前 Rubric、公开开发产物/执行，或明确标记的开发审计摘要 | 识别未覆盖义务、疑似误拒、证据不足 | 待研究问题；假设与已观察错误分开 |
| B2 提议可复用策略 | 相同开发证据，Research 臂额外允许限定资料 | 定义机制、义务、适用/例外、证据、检查生成和不确定性 | 版本化 Rubric/策略，或 no_update/invalid |
| B3 实例化检查 | 冻结策略、公开任务、匿名配对产物 | 生成该题 probes；同一组适用检查用于全部条件 | 调用、expected/关系、依据，不读取 H 补答案 |
| B4 执行前审阅 | 公开任务、固定 probes | 机械校验，再语义审阅依据、合法输入、预期与关系 | keep / abstain / unknown、原因码；不改 expected |
| B5 按事实缺口研究 | 只有 `missing_external_fact` 的具体检查 | 查限定官方资料、选择片段、再审**原检查** | 有来源的再审结论或保留未知，不自动采纳 |
| B6 隔离执行 | 保留检查、每个绑定产物 | 在安全执行器中实际调用 | 观察结果、状态变化、执行回执；动态 probe 的 match/mismatch/unknown |
| B7 聚合与校准 | 共同任务义务上的报告、宿主独立 H、冻结配置 | 比较检错、误拒、适用性、覆盖率、配对方向与成本 | Verifier Gate 结论和限定权限，不等于 Skill 准入 |

### 当前相关 Research 与策略实例化接口

- [research.py / stage2](../skillopt/skill_validation/research.py)：有界问题规划→最多三页 Python 3.11 官方资料→条件化检查提案，最多两次模型调用。受限检查方式包括公开示例、输入状态、公开不变量。
- [natural_policy.py](../skillopt/skill_validation/natural_policy.py)：可复用七字段策略→任务级 probes；目前每题最多两个，支持单调用 expected、双调用输出相等。后者不能表达所有复合/幂等关系，更不是通用可执行 Rubric 语言。
- [probe_fact_research.py](../skillopt/skill_validation/probe_fact_research.py)：执行前审阅发现具体外部事实缺口才调用，最多两个官方 URL、两次模型调用。模型选择片段 ID，宿主恢复原文；查询、来源、片段、缓存均绑定当前问题与检查。

Research 允许没有新增信息、检索失败或 no_update；不能检索当前任务答案、修复 PR 或隐藏测试。资料必须支持已有任务义务，不能把一般建议提升为新要求。引用可核对只证明出处，不证明推理成立。

审阅器不直接看实现、执行结果、Skill 条件或 H；但 proposal 的 rationale 可能带入产物感知生成器的观察，不能声称完全信息独立。算术错误、格式问题或题面歧义也不都需要外部 Research。

近期真实模型为 **BigModel `glm-5.3`**，审阅实验为 low reasoning；历史 PJLAB 运行单独记录。模块通过 transport 注入模型，并没有默认使用更强的独立评审模型。最新任务教师也使用 GLM-5.3，已暴露推理 token 耗尽而没有正文的问题。

### 执行检查与独立校准，分别在评什么

**执行检查**问：“这一产物在这条有依据的检查上观察到了什么？”主线结果为 `pass / fail / unknown / not_applicable`。通过只覆盖该项证据；API/解析/环境失败不是已确认语义错误；probe mismatch 也必须先有合法检查依据，不能自动宣判答案错。

**独立校准**问：“这套完整验证流程，相对 H 是否减少漏检且不过度误拒？”校准对象绑定可复用策略、检查生成、执行、适用性、聚合与源码版本；不能每题改标准却沿用旧授权。新版本须重新冻结与校准。[calibration.py](../skillopt/skill_validation/calibration.py)

风险约束、覆盖率要求与最低样本在运行前冻结；unknown 和成本独立报告，各版本使用共同义务分母。新增 [verifier_readiness.py](../skillopt/skill_validation/verifier_readiness.py)已统计独立错误/漏检任务族，但它只做充分性诊断；通用校准的 `min_natural_errors` 仍按产物/义务位置计数，**尚未全面替换成任务族级准入规则**。

自然运行另有 `natural_metrics.calibrate_policy`，只授权对应 Coding 开发反馈；它不等于 `admission.py` 的 Skill Gate。已消费面板回放与新审阅实验均不签发新授权。

## 7. 两道门与协同闭环如何连接

完整设计顺序为：

> 开发配对暴露问题 → Research/Rubric 候选 → 冻结并独立校准验证器 → 获准后重新生成开发执行反馈 → 更新 Skill → 冻结 Candidate/范围 → 独立三条件确认 → Skill Gate → 冻结后 final。

| 门 | 输入 | 决定什么 | 不能代替什么 |
| --- | --- | --- | --- |
| Verifier Gate | 冻结验证管线、独立校准 V/H、覆盖/风险配置 | accepted / rejected / pending；在哪些义务和条件下可提供反馈 | 不批准某个 Skill，更不证明跨域安全 |
| Skill Gate | 获授权验证器、No-Skill/Current/Candidate 配对、冻结范围 | 当前实现 Local Commit / Restrict / Reject / Pending | 不因某答案得分高就批准整个 Skill |

[admission.py](../skillopt/skill_validation/admission.py)区分目标收益区、原能力保持区、不适用区。范围只读执行前公开义务，不读隐藏机制标签、答案或执行后成败。新 Skill 不能继承旧版本授权；当前没有获准 Current 的继承部署路径，未获准/不适用时使用干净 No-Skill，而不是污染环境之后再“回退”。当前注册入口明确不支持跨域区域授权。

[closed_loop.py](../skillopt/skill_validation/closed_loop.py)已顺序连接两道门：验证器不足则不调用 updater；通过后生成真实执行反馈；候选冻结后才确认；final 只评价固定决策。**公开 CLI 使用 scripted Research/updater/Solver 和工程审计标签**，配合真实 Docker 执行；预注册 `reverse_list` 检查配方不是 Research 发明的算法。

历史 V16 则是真实多轮 Skill 与验证策略更新，但没有新主线的 Skill 准入/跨域部署链，且自然新增检错为 0。不能用 V16 的真实更新与新 CLI 的 fixture 准入拼出不存在的完整效果实验。

## 8. 各入口的实际状态与执行环境

| 入口 | 当前实际用途 | 最近状态 |
| --- | --- | --- |
| [natural_study](../skillopt/skill_validation/natural_study.py) | HumanEval+ 自定义自然面板、文本候选、策略校准 | 9/22 已完成；自适应分支未授权，共享固定反馈候选 |
| [natural_verifier_replay](../skillopt/skill_validation/natural_verifier_replay.py) / [probe_review](../skillopt/skill_validation/probe_review.py) | 同一批冻结产物比较验证器和事后盲审 | 真实旧数据诊断，不更新 Skill / 不读 final / 不部署 |
| [admissibility_study](../skillopt/skill_validation/admissibility_study.py) | 先审检查、再隔离执行 | 9/23 完成；`gap_research=false`，不是逐检查 Research 增益实验 |
| [development_repair_study](../skillopt/skill_validation/development_repair_study.py) | 同父分叉、全量反馈、一次公开修订 | 9/23 完成；已消费的 7 道回归诊断题，不是独立泛化 |
| [rule_learning_smoke](../skillopt/skill_validation/rule_learning_smoke.py) | 空规则包→反馈→规则修改/条件渲染 | 全部 scripted fixture，0 API、0 真实执行 |
| [curriculum_study](../skillopt/skill_validation/curriculum_study.py) | 历史目标→新任务家族→规则学习→共同确认 | A–D 共14次模型调用均 Pending；0真实 Skill 更新、无确认成绩 |
| [mechanism_study](../skillopt/skill_validation/mechanism_study.py) | 固定课程→同父同反馈更新→raw/conditional完整确认 | 44/44族资格、3,744评分位置完成；没有机制策略优势或有效条件禁用 |
| [public_repair_feedback](../skillopt/skill_validation/public_repair_feedback.py) | 绑定公开初稿与修订→摘要/轨迹对照→规则提案 | F共12次真实提案已完成；只证明轨迹进入更新，未证明迁移收益 |
| [solver_profile](../skillopt/skill_validation/solver_profile.py) | 共同预算/格式→单次公开修订→非回归选择 | 9/27显式接入两学习入口；真实工程smoke已完成，不是方法效果 |
| [patch_diagnostic](../skillopt/skill_validation/patch_diagnostic.py) | 固定初始源码与保留/替换契约→No-Skill难度诊断 | 24题×2次初稿/最终均48/48；明显天花板，不是学习收益 |
| [repair_transfer](../skillopt/skill_validation/repair_transfer.py) | F主候选冻结→原24题新基线/候选→初稿和最终分项审计 | 576个raw位置完成，实际注入96轨迹未观测干扰；+2通过来自格式差，非语义正迁移 |
| [closed_loop](../skillopt/skill_validation/closed_loop.py) | 校准→授权反馈→更新→准入→final | 工程控制路径已通过，未证明自然端到端效果 |
| [continual_eval](../skillopt/continual_eval/cli.py) | 外部冻结S0–S5→五域评测矩阵与跨方法配对 | 9/28新评测框架；无自动进化/新授权，尚无五域正式基线成绩 |

近期实验由本机 Python 调度、经 SSH 在 Linux Docker 执行代码。Docker 用于执行 Solver 产物、公开检查、参考/控制资格检查及宿主审计；不是调用 LLM 的替代品。镜像/调用/源码/回执有绑定，执行后需确认清理；隔离环境不可用时返回 unsupported/unknown，不裸跑候选代码。

相同请求可从完整终态回执回放；只有 intent 而没有终态时暂停核实，不自动重抽以改善成绩。源码或协议改变使用新输出目录；本机调度仍会受休眠/SSH 影响，不能视为已经部署到不间断远端调度。

9/25增加[专用SSH配置适配](../skillopt/skill_validation/mechanism_transport.py)：可连接本地Linux VM或其他明确指定的Linux执行器，仍复用原Docker策略、主机密钥检查及回执协议。没有macOS裸执行回退路径。当时PJLAB握手失败，9/25实验改用不挂载macOS主目录的专用Linux VM；当次未改变Clash路由或全局SSH配置。Docker29兼容修复生成执行器v2，旧快照和失败不改写。9/27可靠性验收已使用恢复连接的PJLAB Linux Docker，仍由本机调度；不同执行镜像与源码身份分别绑定各自协议。

可离线查看的入口（仓库根目录、激活 `skill` 环境后）：

```bash
# 已公开的真实记录摘录，零 API、不执行候选代码
python scripts/replay_research_demo.py

# 新规则更新的工程链路；全部 fixture，不是方法效果
python -m skillopt.skill_validation.rule_learning_smoke \
  --output outputs/skill_validation/rule_learning_doc_smoke

# 主线离线回归；此命令不是付费自然实验
python -m pytest -q tests/test_skill_validation_*.py
```

真实课程启动参数见[9/24 课程报告](skill-validation-capability-curriculum-20260924.md)；不要用新的源码直接续写旧目录。原始 `outputs/` 与 API 缓存不公开，公开 demo 只是精选材料。

## 9. 五基准持续评测流（9/28新增）

详细配置、原生依赖、恢复命令与限制见[五基准评测说明](skill-validation-continual-evaluation-20260928.md)。默认顺序为 **BigCodeBench → SpreadsheetBench → SearchQA → KOR-Bench → ALFWorld**。S0为空Skill；每完成一个来源学习阶段，由外部学习程序提交冻结S1–S5，再评全部五域。此处只接通评测侧，不会自己产生五阶段Skill。

| 步骤 | 输入 | 输出与边界 |
| --- | --- | --- |
| `prepare` / `check` | 本地真实任务、固定版本、工作簿/游戏资源、原生环境 | 标准panel与就绪状态；缺资源不伪造小题替代 |
| `freeze` / `checkpoint` | 分区/历史曝光、共同模型预算、源码环境、外部Skill与父版本 | 不可变协议、检查点身份；S0统一为空，后续来源声明不是训练独立认证 |
| `generate` | 检查点、任务公开字段、同预算模型 | 每题×重复的产物、请求与成本；不读取隐藏分数 |
| `score` | 冻结产物、原生隐藏评分材料 | pass/fail/unknown和原生指标；不反馈学习器 |
| `report` | 冻结清单及所有已完成/未完成位置 | 每方法/历史6×5矩阵、前后向迁移、对No-Skill/SkillOpt的配对与成本；缺域保留Pending |

新适配器前四域目前为共同一次生成，ALFWorld为固定步数交互；**不是9/27 DSL的`reliable_v1`**。Sheet公开目标坐标提供给模型、标准单元格值不提供。代码在Linux Docker执行，KOR官方评分也因表达式求值放在容器中；环境不可用不裸跑。配置先于运行固定，不能仅对候选增加修订机会。后续若升级原生工具协议，需重建所有对应基线。

**10/1共同长流式配置**：`continual-eval-v2`及新`continual-learning-v2`把`model.transport`的stream=true、read300、每HTTP wall1800、`completed_response_v1`健康策略传给实际CachedAPI，并绑定请求/服务身份。BigModel GLM-5.3明确low，Solver上限65536，学习reflection另限16000；本次reflection仍4096。默认v1、旧运行/缓存不变；API的131072仅用于上述显式v5诊断，不抬高常规比较预算。输入为冻结panel/空父/共同预算，输出为原产物、原生评分和学习账本；unknown仍Pending，不当0继续优化。新入口独立review通过，Linux含固定官方GEPA的625项相关测试通过。[评测模板](../configs/continual_eval/noskill_long_stream_v2.example.json) · [学习模板](../configs/continual_learning/long_stream_v2.example.json)。模板不是有数据的实验清单；常规runner与学习优化器仍没有恢复器的精确协作暂停能力。

**10/1真实新基线入口**：[prepare_long_baselines.py](../scripts/prepare_long_baselines.py)只读旧sealed panel/plan/manifest/源码，不导入旧回答或分数；校验400题与65训练题/64族＋64选择题/64族，另建源目录之外的新study。输出为eval-v2 plan、两个learning-v2 manifest及来源/预算绑定。共同空父、seed、数据角色与旧其余预算保持，Solver改65536；旧曝光development数据不是新holdout。`run_long_baselines_linux.sh`先`--check`，在同一Linux交互shell中`proxy_on`后执行：No-Skill先首响应再6并发，学习SkillOpt→GEPA各1并发；学习整个方法与No-Skill评分共用`native.lock`，防止两台8GB容器叠加。学习非零则停GEPA；No-Skill采集非零仍报告已完成记录，不静默补抽。01:14:30核验No-Skill已800/800采集、0截断；随后开始原生评分。SkillOpt因9份反思中2份JSON解析失败而Pending：129份任务结果完整、空父选择33/64、训练36/65，尚无候选；旧队列正常停止。01:38:58另行提交同manifest的GEPA独立队列，仍等待共同native锁，不称已完成。没有完整新准确率，不自动注册S1、运行五阶段或授予部署权。[配置与结果](long-response-baselines-20261001.md) · [夜间后续](overnight-baselines-20261001.md)。

**夜间只读监控**：[monitor_experiment_jobs.py](../scripts/monitor_experiment_jobs.py)读取上述运行目录的白名单计数、回执及意图身份、unknown原因与成本，输出到独立运维目录，每60秒观察、最多12小时。它不调用模型、不读正文或隐藏测试、不改实验、不自动重试/关闭调用；观察状态不是正式验收成绩。Linux后台即使Mac休眠仍留档，后续修复和实验必须另行核验和冻结。19项工程测试与独立review通过；01:49以新脚本/输出升级观察器，旧日志保留，只停止旧观察器，不停止实验。

上述Coding No-Skill已于02:38完整评分并核验：800位置为400 pass/399 fail/1官方内部timeout；0截断，800HTTP/324,867 tokens，800容器清理全部确认。两次重复有38题明确结果不同；旧新44份相同代码判分一致。GEPA随后获得native锁且首实响应通过，反思重提继续排队。[终态、评分审计和旧新比较](results/noskill-long-final-20261001.json)。此补记更新前段的采集/排队状态，不改历史时间节点。

GEPA于03:10:57完成两轮：空父33/64、完整验证候选28/64（4胜9负51平），最终选中空文本，故不生成重复空Skill的S1。实际162调用/HTTP、145,551 tokens、160开发评分、0unknown/重试。随后有限SkillOpt反思重提取得native锁，首实际响应正常并进入选择评分。[GEPA完整审计](results/gepa-long-learning-20261001.json)。

有限重提于03:25:24完成：候选31/64、空父33/64，2胜4负58平，拒绝候选、继续空父。新增70调用/HTTP、112,794 tokens，继承138调用/103,424 tokens单列；64条选择均已知、0重试，未启动S1。这解决了本次格式停止，但没有带来学习收益。[完整终态](results/skillopt-reproposal-final-20261001.json)。

**单轮内容策略shadow消融**：[feedback_ablation.py](../skillopt/continual_learning/feedback_ablation.py)输入相同65份已冻结训练轨迹、公开契约、H开发标量和空父；通过显式白名单排除选择集结果、隐藏测试、堆栈及旧反思。两臂仅更新策略不同：普通归纳，或明确可观察适用条件、例外、保留正确行为及避免无关干扰的机制归纳。每臂最多一次4096-token提案，合法新文本才由同一65536-token Solver跑完整64题选择，输出候选、配对胜负、原生gate、共享继承/新成本；`NO_UPDATE`不重采样父，非法响应/unknown为Pending。Linux76项合测、独立review和真实只读预检后03:32顺序启动；首普通臂响应已核验HTTP200/stop、28,760 tokens（其中completion802）、3,326字节合法Skill。两臂共用全部训练证据hash`7f3b9a80501a56a88535f86b7c1b7cc8e119abca4918c654651118406c78f0a4`，未筛选或截断证据。该单历史诊断不是完整Rubric＋Research、两轮等实际算力比较或独立泛化验证；H标量不归功于Research，无部署/scope授权，结果待核验。

**10/1有限反思重提分支**：[reproposal.py](../skillopt/continual_learning/reproposal.py)仅接纳上述第一次候选生成前、129份任务证据完整且7份反思合法/2份格式失败的Pending。`prepare/check`绑定父协议、原任务角色、回执、缓存、原生算法源码和环境；`run`逐字复原9份原analyst提示，回放7份旧响应，对2份失败各最多新提案一次，然后原生合并/排序/补丁。新Skill才评完整64题选择集；同文本直接`no_update`，不靠重抽旧Skill制造提升。继承138调用/103,424 tokens先从原总预算扣除，追加费用独立记录；任何unknown/中断仍Pending。原父目录加共享只读锁且不改写。Linux相关110测试、独立review、真实只读准备核验通过；协议`8823dc55f1b81e4f717222d7bb8f794e54a730cda1eeddd586c51968f731bf87`于01:55:49提交后台等待共同native锁。它是一轮诊断，不是旧两轮优化器续训、语义保真JSON修复或完整SkillOpt复现。

**共同预算的SearchQA基线**：[prepare_long_searchqa.py](../scripts/prepare_long_searchqa.py)只读旧400题开发面板和上述Coding新配置，冻结完整400×2新No-Skill；不导入旧模型回答/分数，宿主答案只供原生评分。共用同一冻结eval源码、host和GLM-5.3 low/65536/stream300/1800，文本EM/F1评分不占Docker锁。7项fixture测试及独立review通过；02:04:24已Linux后台6并发启动，首真实响应HTTP200/stop/流完整、1,079 tokens。此组用于以后跨域比较的同配置对照，不是Skill训练、final或纯预算因果实验。准备hash`494a1fe5acce5d6594f14a1c80b5b1c4fbb49c6df2e3e23e9e6ab812f68667b6`；另有每60秒只读监控，旧结果不变。

该组02:08:18全部评分完成：560 pass/234 fail/6 unknown，EM全800分母70.00%，可评794分母70.53%；6项均服务端内容过滤，0截断/通信超时/开放调用。800HTTP、875,617已知tokens，6项缺usage；34道题的两次硬结果不同。是同预算基线，不是Skill收益；宽松substring不替代硬EM。[完整证据](results/noskill-searchqa-long-final-20261001.json)。

**完整KORBench同预算准备**：[prepare_long_korbench.py](../scripts/prepare_long_korbench.py)只读旧500题/50规则族的完整开发panel与新版共同配置，每类100题、2次重复；不读取旧回答/分数、不筛选截断子集。输出新的1000位置No-Skill协议，Solver与Coding/QA相同65536/low/stream300/1800，原官方评分源码hash、300秒/4GiB/1CPU保留。9项新单测与基线准备合测32项、独立review通过；真实prepare/check为0API，准备hash`295ba9a22afd9b8b79c4607cde2a6a8387055646bc0f1a36777774b4b3453a81`。计划6并发、先首实响应健康屏障，评分共用native锁；与8并发S1模型组互斥，允许单个学习/诊断调用并行。旧混合预算恢复链和分数不变，不宣称预算因果改善；启动/终态见夜间报告。

**ALFWorld同模型预算准备（Linux已排队）**：[prepare_long_alfworld.py](../scripts/prepare_long_alfworld.py)读取旧修复目标保留后的B协议、完整39题/39词法族×2、原资产及共同模型/实际服务身份，输出78位置的新No-Skill协议。复用相同冻结求解源码，保留原ALF原生Python/软件包、seed42、50步、60秒环境等待和每步initial_observation；明确记录它的host与Coding不同，不强装同一Python环境。两域HTTP版本及共同GLM-5.3 low/65536/stream300/1800校验一致。旧8个未闭合调用不读取、不续抽、不移植。19新增测试、独立review和Linux实际prepare/check通过；计划`e31ebec5e4c09ff88cd6f6b3230b0a9751c5ce3491a81130b5f2cc421dd4dec8`。04:53:54进入持久队列，先核验KOR1000位置终态及原参考400清理；固定2workers，整个generate及score占native和模型组锁，不能只在最终评分时取锁。独立观察器每60秒留档，实验不依赖Mac连接。ALF原生子进程不声称Docker/硬内存隔离；排队不等于已有78结果，不接通ALF学习或旧episode恢复。

**后台任务交接补强**：ALF队列v2在原队列0API/0episode且仅等待时独立替换，旧启动记录保留、实验计划不变。[native_handoff.py](../scripts/native_handoff.py)逐条核对KOR交付unknown无容器、前置拒绝0容器、实际执行1容器的清理与两处镜像身份；不能只因锁释放推定清理成功。35项fixture及旧KOR1000真实回执只读检查通过。Sheet于06:07:38排在ALF之后；[process_handoff.py](../scripts/process_handoff.py)对已绑定的ALF自有进程/session做最多30秒只读等待，处理EXIT标记先于shell退出的竞态，不kill、不重试模型。21项fixture及独立review通过。两队列都只调用一次generate，缺证据则停；共享锁始终按模型组→native取得，等待前序终态时不占锁。[准备/队列快照（不是效果）](results/alfworld-spreadsheet-preparation-queues-20261001.json)

**跨运行来源域配对报告**：[compare_baseline_checkpoints.py](../scripts/compare_baseline_checkpoints.py)输入已封存No-Skill S0和已完成学习产出的非空S1，校验相同task/repeat、源码、模型实际请求预算、服务和原生执行身份；输出配对胜/负/平/未知/缺失及成本。使用实际学习授权划分65训练题、64选择题和271未参与该次学习的任务，并检查任务族重叠；后者仍是历史曝光development，不能称独立final。不执行模型或重评分、不制造S1、不回写旧记录；任一目录在写时拒绝报告。18项fixture与独立review通过，尚无真实S1效果结果。

报告v2进一步固定seed20261001、10,000次整任务族bootstrap，仅对已知配对的位置加权差值计算95%描述性区间；重复随任务族整簇抽样，不冒充新增独立题。unknown/缺失保留分母，另报全任务可能完成界限，不插补语义分数；少于2个已知簇Pending，全平/全胜的零宽区间标为经验抽样退化，不解释为无风险。词法族不保证语义独立，区间不纠正选择与历史曝光，不改任何gate。配对、准备及监控合测62项通过、独立review通过；Linux另名部署v2分析脚本，旧v1及实验源码不变，尚无真实S1效果。

**真实学习检查点准备**：[prepare_learned_checkpoint.py](../scripts/prepare_learned_checkpoint.py)输入完成的GEPA、有限SkillOpt重提或明确的两臂shadow结果、匹配的No-Skill面板和冻结源码，核验被选非空文本及完整64题选择记录、服务/预算/成本绑定；输出独立S1 study及可回放准备记录。支持完整BigCodeBench 400×2和同配置SearchQA 400×2，后者明确为Coding Skill原始跨域使用、无目标域训练。仅注册空S0元数据，不执行或移植S0回答；Pending、被拒/空Skill、证据不完整及活动写锁均拒绝。v2保留shadow及非Research、非等实际算力标记，28项测试、连同配对报告55项通过，独立review通过；另名部署不覆盖v1。尚无真实S1启动或效果，不读取优化器pickle，不授予部署权。

**BCB公开反馈接入仍有缺口，但不是没有公开检查依据**：10/1只读审计65道授权train，旧提取器覆盖0/65；进一步逐契约核对发现10/65含行内`>>>`，只是行首标准doctest为0。入口和输出声明均65/65，狭义字段/shape条款至少13/65，明确部分内容/顺序保留5/65，文件交付/路径操作14/65（含网络下载，不能视为全部离线支持）；没有依据将所有任务都要求为“整份输入不变”。严格直接调用＋JSON literal参数/预期静态识别1例，仍未执行或资格。源码导入保留原公开prompt，问题是格式/表示覆盖，不应从提取器0推断原材料不存在。[新覆盖审计](results/bcb-public-contract-coverage-20261001.json)保留[旧启发式审计](results/bcb-public-evidence-readiness-20261001.json)。未使用选择题、隐藏测试、参考或模型成败来设计检查。下一步先补保守公开格式提取与有限类型/结构/保留关系检查，再做可采纳性审阅和自然校准；这些原有公开依据不是Research新增知识。旧`conditional_feedback`的标准库JSON产物/公开修订假设仍与BCB一次多库代码生成不同，不直接宣称已经公平接通，也不修改冻结Solver。

**工作簿独立重算流程**：[sheet_recalc.py](../skillopt/continual_eval/sheet_recalc.py)读取冻结旧面板、全部预测和原分数，先以固定镜像运行7项真实控制资格，再`prepare`绑定所有160位置、任务/产物/源码/镜像哈希；`run`对150份已交付工作簿统一执行，其他10位置保留交付问题。参考与预测在各自断网非root容器中重算；先检查参考原生缓存一致，再比较预测，语义变化/不支持功能/参考漂移不猜测判分。输出是逐位置新旧转移、unknown原因、隔离成本及160总分母，0模型调用、无Skill更新、旧分数不回写。首次q1数组单格范围表示差异导致6/7；新q2只规范化同坐标range，7/7通过。10/1完整面板已完成，32个旧unknown可判定、36个旧可判定被保留检查/兼容范围拒绝，共同可判定62位置无翻转；尚非全功能Excel替代环境。固定资格不代表自然效果，完整结果见[环境报告](evaluation-environment-recovery-20261001.md)。

**10/1数值导出保真v3**：输入同一冻结全160面板，不调用模型。每本工作簿分别提取非公式、非数组派生数值literal；UNO核对计算前后类型与binary64（含signed zero）精确相等，才恢复其导出OOXML原数值文本。保留原始导出，不改公式、公式缓存、计算输入，不从参考向预测复制值；导入舍入/类型变化仍unknown。独立review、阈值敏感负控与真实LO q3 9/9通过；C目录01:00:01–01:09:01完成全量160重评：59 pass/41 fail/60 unknown，较v2恢复3题/6位置（5 pass/1 fail），原94已可判定位置全部保持。单工作簿120秒未变，165容器486.822累计秒、0API，564旧证据未改。相对最初原缓存评分仍有32 unknown恢复/30旧可判定降级，两方向均报告；不能宣称完整Excel等价或模型能力提升。[本轮记录](long-response-baselines-20261001.md) · [终态数据](results/spreadsheet-recalculation-v3-final-20261001.json)。

**10/1布尔等价表示v4**：继续同一全160旧产物。公式Tokenizer须完整往返，只有操作数边界的布尔literal与同值零参数函数可等价；不改字符串/引用/名称/含参函数/其他公式变化，FORMULATEXT等文本观察器存在时仍unknown。13项真实正负控制通过，独立review和85项Sheet测试通过；D于01:45:36–01:55:34重评得61 pass/42 fail/57 unknown，较v3恢复2题3位置（2 pass/1 fail），其余不变。167容器541.098累计秒、0API、0清理失败；564旧证据及v2/v3源码不变。输入/输出/参考均不互相填值，这是评分覆盖修复，不是更宽答案容差或完整Excel等价。[证据](results/spreadsheet-recalculation-v4-final-20261001.json)。

**UTF-16元数据v5资格与边界**：仅新版本私有XML reader接纳明确BOM的UTF-16LE/BE，严格解码后检查声明一致性、NUL、DTD/entity、外链及原/解码后双大小预算，不删除或重写原成员。[XML编码规范](https://www.w3.org/TR/REC-xml/#charencoding)作为依据；独立review补住重复BOM绕过声明检查的边界，旧UTF8和历史compat均不变。Linux120项Sheet单测通过；q5为17/17控制（15真实容器＋2前置安全拒绝，25.780累计秒、0API）。E于02:15:15–02:29:50完成全160旧产物重评：61 pass/46 fail/53 unknown，较v4仅2题4位置从unknown转fail，其余156不变。173容器755.622累计秒、0API/清理失败；564旧证据及v2/v3/v4源码未改，日期30未改。[完整证据](results/spreadsheet-recalculation-v5-final-20261001.json)。这些版本仍是历史产物独立重评，**未接入常规`backends.score`默认路径**；不改变正在运行的基线，不宣称生产工作簿环境已经完全修好。

**v5常规评分的显式适配（真实工程smoke已通过）**：[sheet_recalc_adapter.py](../skillopt/continual_eval/sheet_recalc_adapter.py)通过新`qualified_lo_recalc_v5_v1`配置接入`backends.readiness/score`和`runner.score_checkpoint`。输入为冻结预测工作簿、宿主私有参考、绑定新源码路径的17控制资格及独立LO镜像；生成镜像与重算镜像分开。输出为硬结果、原因、案例覆盖、实际容器成本和私有证据引用；不向模型回传参考值。每位置证据只存`host_only/scorer_artifacts/`，旧评分路径/v5/worker保持；unknown不静默回退，清理失败整体unknown。重复score只核验原资产/产物/回执并回放，不重新启动容器。30新增测试、450项评测测试及独立review通过，Linux相关150项通过；新冻结目录已重新资格17/17，通过`backends.score`执行3个不同历史任务（pass/fail/兼容unknown各1）并缓存回放，结果一致、回放0新容器，共19容器、0API、全部清理确认。旧来源及564证据未变。完整runner采集仍只做离线测试；没有新模型推理、Sheet学习或新全量基线，更非Excel等价证明。[真实工程回执](results/spreadsheet-production-adapter-smoke-20261001.json)

**工作簿共同预算新基线准备**：[prepare_long_spreadsheet.py](../scripts/prepare_long_spreadsheet.py)读取完整原80题/80词法族×2、原生成镜像和资产，仅替换显式评分profile并使用共同GLM-5.3 low/65536/stream300/1800；旧预测不导入、旧成败不用于筛选。新源码以共同长流式树为底，只叠加五个已审阅Sheet文件，核对生成函数/worker不变；不能整树复用较早适配目录，否则会带回旧API传输实现。20项fixture、独立review及Linux170项相关测试通过；新路径实际q17/17通过、15容器/35.695秒、0API，独立160位置prepare/check完成，尚无本轮模型结果。计划hash为`0cf09e040779c170c36903cb695fce95b91440b2c389f74ffe9c041ea321b04d`。后续全generate/score持native及模型组锁，固定2workers，生成/重算成本分列；同域后续S1必须沿用此新profile，不能与旧兼容口径S0直接配对。

**公开格式适配已实际运行，执行反馈尚未接通**：独立入口[bcb_public_examples.py](../skillopt/skill_validation/bcb_public_examples.py)的`extract_public_examples(public)`仅接受公开`prompt/entry_point`，静态输出原文位置、上下文、身份哈希及每个候选的支持/拒绝原因；不执行代码、不读H或参考。真实完整65题/64族确定性提取：10题含30个候选，1个格式支持、29个不支持（14赋值/前置状态、13非直接入口调用、2表达不明确），55题无标记；全部65记录保留。字符串和注释中的伪`>>>`、尾随文字、任意表达式均不能变成可执行预期。58项专项测试及相关232项回归通过；0API、0容器，重复提取一致，原来源不变。`supported`仅表示受限字面量格式可解析，始终保留`executed=False`和`admissibility=not_reviewed`，不授予验证器或Skill权限。仅1/65的格式支持不足以建立本轮反馈对照；仍需可采纳性审阅、多库/文件隔离执行和更广公开义务适配，不能把工程解析覆盖当Research或Skill收益。[实际静态输出摘要](results/bcb-public-example-extraction-20261001.json)

**公开工作簿公式预览修复（仅本机代码，尚未部署）**：真实160份输入回放中158份逐字一致，另1题×2的3个数组公式单元格被旧`str(value)`写成带内存地址的对象，未显示公式内容；其余任务/输入文件/产物身份链一致。新增[backends.py](../skillopt/continual_eval/backends.py)显式开关`runtime.spreadsheetbench.spreadsheet_preview_version="public-formula-preview-v1"`（传给后端的runtime是该子映射）：输入仅原公开工作簿，输出确定性的ArrayFormula `text/ref`、DataTableFormula公开字段；每文本字段200字符，缺失/截断/不支持明确标记，不调用未知对象的str/repr。普通标量/日期、20表×5行×20列限制及默认legacy保持，未知版本或缺依赖在调用模型前拒绝，runtime由既有plan身份绑定。43项新fixture、168项相关回归及主/独立review通过；不修补旧prompt、不部署冻结Linux树、不重跑或改分。后续使用此预览须新协议，并给全部比较条件使用相同公开信息；它不是Skill或Research收益。

上述新工作簿基线08:30:38完成：160位置63 pass/44 fail/53 unknown；152工作簿交付、其中45兼容未知，另8未交付。只有1次截断，5个运行异常因历史日志仅有类型仍无法归因；159生成与232重算容器全部清理，160API/326,508 tokens。实际新profile已跑通完整采集－评分，但覆盖107/160不足以声称环境完全可用；新预览尚未混入。旧v5重评及源码不变，[完整终态及成本](results/spreadsheet-long-baseline-final-20261001.json)。

**固定全量官方参考资格**：[reference_qualification.py](../skillopt/continual_eval/reference_qualification.py)输入原No-Skill完整400题/399词法族的开发协议、原始官方v0.1.4缓存及下载收据；核对公开契约/隐藏测试/来源，严格拼接`complete_prompt + canonical_solution`。宿主只做AST检查；参考仅在原生隔离容器中以相同300秒/8GiB/1CPU执行，不进入Solver、Research或Skill反馈。输出为新的400参考环境资格回执、未知原因、容器成本和完整分母，不覆盖旧模型结果。18新增测试及旧相关回归共121项、独立review通过；闭合unknown不重试，未闭合执行或清理不明则Pending，闭合边界可暂停恢复。与其他原生评分共用native锁，内置取锁不能再外套同一锁；零模型调用。04:57:10完成393 pass/7 fail/0 unknown、400容器全部清理，发现5个NLTK数据缺口、1只读文件系统、1离线URL。参考失败不自动证明同题模型失败由环境导致，参考成功也不证明所有合法实现都受支持。[完整真实资格](results/bcb-reference-qualification-20261001.json)

**已发现资源缺口的固定数据层修复（构建完成、资格Pending）**：[nltk_overlay.py](../skillopt/continual_eval/nltk_overlay.py)只下载允许清单中、固定官方提交和SHA256的`punkt/stopwords`数据；严格校验压缩/解压尺寸、路径、类型与派生文件树，宿主不反序列化pickle。输出私有build context及manifest，再从原不可变镜像构建仅新增数据的一层；不升级NLTK 3.8或其他包、改checker、覆盖旧tag、开放任务网络。v1的BuildKit外部元数据查询失败保留；v2仅在docker build子进程固定legacy builder，成功构建新镜像，核对原层和运行配置不变。24项测试、独立review通过；新资源版本不声称与论文历史数据完全相同。全400新资格实际397 pass/2 fail/1 unknown，400清理确认、0API；原393保持区392 pass/1 timeout，5个资源目标全部修复，另外2项隔离限制仍fail。预登记393保持＋5修复条件未满足，不能自动用于全800冻结复评，不重抽未知或修改旧分数。[构建回执](results/bcb-nltk-overlay-20261001.json)

**数据层变更后的全量冻结重评入口（代码已验收，实际未获资格）**：[frozen_rescore.py](../skillopt/continual_eval/frozen_rescore.py)输入完整新旧400参考资格、数据层构建回执和原No-Skill全部800份预测/评分；必须先满足预登记393参考保持及5个资源目标修复。输出另行全800执行记录、新旧转移、旧8个明确NLTK缺数据位置/其余792分层和容器成本，0模型调用，不改旧分数或学习准入。重复回放核验已封存记录；不补抽新运行的unknown或未闭合执行。v2修复真实回执中嵌套ANSI错误文本的识别，递归取字符串leaf而不是序列化整个dict；18项测试、独立review、Linux36联合测试通过，旧v1及其保守拒绝记录保留。新资格存在原参考pass→清理确认的timeout，实际prepare已按393＋5门拒绝、输出目录未创建、0API/容器；不放宽门，也不把执行器波动归功或归咎于数据层。[完整资格与拒绝控制](results/bcb-nltk-reference-qualification-20261001.json)

**进程池与官方安全包装器的工程控制（已完成）**：[pool_guard_controls.py](../scripts/pool_guard_controls.py)及[容器worker](../scripts/pool_guard_control_worker.py)不使用任何自然题、参考或模型产物。固定两镜像×原`safe_environment`开启/关闭×快速map/已确认仍忙的worker退出×3重复，共24个手写控制；SDK/Pool源码SHA绑定，每容器20秒外限、相同隔离和native锁，禁止补抽。输出阶段标记、kill拒绝次数、退出/超时、清理及成本，受限原始日志仅私有留存，不改正式worker或资格。v1在0实际执行时被主审发现装饰器源码定位错误、停止等待队列并保留；v2以`inspect.unwrap`定位真实SDK源，新增真实decorator回归，17项测试及两次review通过。真实24控制17完成/7超时，全部清理、0API；有guard的忙worker 6/6超时、快速map 1/6超时，无guard两组均0/6。快速map超时发生于旧镜像，证明已有兼容机制，不把它当新增数据层的语义回归；未捕获自然超时当次栈，不证明唯一原因，更不授权关闭正式安全层。[控制结果](results/pool-guard-controls-20261001.json)

**完整交付物与回复尾部截断的独立诊断**：[diagnose_kor_deliverables.py](../scripts/diagnose_kor_deliverables.py)只接受原KOR500×2已完整封存、零开放运行；按HTTP完整流、长度和完整双括号语法纳入全部length回复，不读取gold选例。输入整份未改原文，由原隔离官方评分器执行，不在宿主求值或手选答案；输出独立诊断与成本，原unknown不变、0新增API、无准入权。原来源/回执只读锁和实际native锁写入协议，19项测试通过。原KOR终态后冻结全部10个length，其中1份有完整括号且尺寸合规、9份无正文，协议`250a060a…`。实际在ALF终态/自有进程清理核验后执行：1份完整原文官方评分pass、9份仍unknown；1容器2.759秒且清理确认、0API、原1000位置哈希不变。正式基线仍746/243/11，不改为747通过。旧0执行排队被另名交接wrapper替换并留档，未改题目/评分协议；仅支持未来另行预登记KOR交付物完整性政策，不适用于不完整代码或无正文。[实际诊断](results/kor-frozen-deliverable-diagnostic-20261001.json)

**冻结候选的未提交补齐（仅诊断）**：[collect_remaining.py](../skillopt/continual_learning/collect_remaining.py)输入普通归纳臂原Pending、非空冻结候选、完整原来源与16个闭合记录；只授权原64题中尚未提交的48题，原unknown不重跑、旧结果不改写。输出为新48题回执及合并64题的pass/fail/unknown/missing、配对与三层成本（共同基础、原臂、补采），没有新提案/更新/准入，原gate永久Pending、不能授权S1。闭合unknown继续收集；未闭合调用、无从核实的费用/产物保留Pending和原始物理证据，不伪造零费用。全部旧执行源码含native worker必须同hash，Linux67测试和两次独立review通过；真实prepare/check为0API，协议`5c55756d11bc96893bf77bd361b1bb49ffe3f7c55bbc6d27943ac859323256d5`。04:05前后已后台提交、首真实响应正常；同native锁，单并发，与KOR6并发合计不超过7。它不是原优化器续训或通过补抽接受候选。

该补齐已完成：新48题27 pass/21 fail；合并34 pass/29 fail/1 unknown，对父6胜5负52平1未知。条件化臂32/64已拒绝，完整两臂对比条件化4胜6负53平1未知；当前只是单历史内容策略诊断，没有Research校准和泛化效果证明。原两臂终态、补采证据与成本分开保存，不为后续诊断继承部署授权。[完整配对记录](results/frozen-selection-collection-20261001.json)

评测只接受最多6,000 bytes的冻结文本，当前不实现Skill检索/路由或范围部署。`skillopt`、`ours_*`是可注册的方法身份，不是已经训练好的基线。逐阶段final分数不能回流修改Skill/Rubric/课程；命令隔离与`host_only/`不是操作系统访问控制。曝光登记仍需完整人工维护，自动族ID不等于语义去重证明。

框架工程验收0模型调用；五域×六阶段fixture测通回放，Linux工作簿正/负/缺依赖控制已执行。随后首个真实No-Skill已完成：旧SearchQA的400条development任务×2重复，BigModel GLM-5.3、并发10，PJLAB Linux冻结快照后台采集后自动评分，800/800回执闭合。EM为552/800＝69.00%，242 fail、6 API unknown；不使用Skill或Research，不是独立final。其他域按资源就绪程度顺序采集，见[基线安排与运行记录](skill-validation-baselines-20260928.md)与[简短汇报稿](noskill-baseline-summary-20260928.md)。

上述KOR完整性诊断补核：Cipher的2,177个括号答案正文一致，但官方仅比较首个，不检查后文矛盾。未来接收策略必须预登记唯一解析、重复及冲突处理；本轮不新增授权或回写分数。[一致性核验](results/kor-length-wrapper-consistency-20261001.json)。完整1000位置身份链独立复核还纠正了早先文字归因：Cipher 1 length，Puzzle 9 length＋1 network_error；不是10份length全部Puzzle。正式类别表和总分未变，[勘误证据](results/kor-unknown-category-correction-20261001.json)。

数据就绪与评分资格必须分开：[Spreadsheet准备入口](../scripts/prepare_continual_spreadsheet.py)保留原始archive和80/40/280分区。首次静态检查标出20/80风险，后续OOXML复核发现13题是合法空字符串缓存而非真正缺失，另7题需兼容上游目标引号。新`spreadsheet_compat.py`以显式runtime版本启用：保留旧评分默认行为，仅修正目标解析及`t=str`且存在空`v`元素的可观察性；不计算公式、不改gold、不猜缺失结果。Linux同80题资格80/80通过、0模型调用；模型产物真正缺缓存仍unknown，final一处gold错名仍blocked。新B协议单独冻结，不覆盖旧资格记录。

9/29完整B产物诊断进一步确认：62个unknown中52个是**预测**工作簿缺公式缓存（32题，对应gold无未解决缓存），另8个执行异常、1个缺工作簿、1个截断；实际159次Docker执行全部确认清理。当前执行器没有公式重算能力，异常分类也偏粗，因此该域还不能直接作为覆盖充分的正式基线。后续重算必须先资格验收、对全部150个已交付工作簿统一应用新协议，并保留160分母和旧分数；本次尚未实施重算。[只读归因与修改边界](spreadsheet-baseline-diagnostic-20260929.md)

KOR按类别＋完整规则冻结10/5/5/5分区；development为500题/50规则，另三区各250题/25规则。仅development×2完成：639 pass、201 fail、160截断unknown，原生评分在模型采集后执行。[完成结果](results/noskill-korbench-20260928.json)。ALF入口限制初始化到当前game、同步原生TimeLimit、确认有界清理；随后真实A暴露公开任务目标随五步history消失的问题。新B将`initial_observation`独立提供到每一步，不引入专家轨迹或won标签，两个8步fixture验证目标保留和episode隔离；A完整78位置保留但隔离，B于9/28 18:47启动，不能合并成重复试验或独立确认。

9/28后续采集已安排Linux单调度队列：KOR模型采集闭合→ALFWorld开发39任务×2次、每episode最多50步→BigCodeBench开发400题×2次。每次只放行一个10-worker模型池；ALF可与KOR原生评分并行，BCB的8GiB评分则等待其他原生评分退出。异常停止并保留intent/回执，不自动重新采样。排队不是运行完成，也不改变既定五域学习顺序。BCB使用官方v0.1.4，先按公开文本近重复族冻结400/128/128/484分区，再执行4道预选参考正控及1道错误控制；这些工程控制通过不意味着完整数据集或方法效果已通过。[BCB准备记录](results/noskill-bigcodebench-20260928-preparation.json)

BCB的800/800回答已完成，原生评分516位置后发生Docker清理客户端回收超时。冻结A源码不改：开放评分意图只能经身份核验标记基础设施unknown，不重跑取得有利标签；其他尚未执行位置可继续原评分。新backend将执行及清理客户端超时转为unknown，不能绕过清理确认报告pass。整个修改不调用LLM判分、不放宽单元测试。

外部训练已增加独立`skillopt/continual_learning/`及`scripts/run_continual_learning.py`。输入为仅development的互斥训练/选择任务族、共同空父、模型和预算；输出为调用账本、候选、选择轨迹和冻结阶段状态。GEPA使用固定官方Pareto/反思引擎；SkillOpt调用原生反思→合并→排序→补丁→来源选择门。共享`Ledger`绑定请求、产物、task/role、源码和环境；unknown/中断进入Pending，不自动重采样或把unknown当0。训练暴露明确授权的开发标量反馈，不暴露隐藏测试正文；评测侧`score_feedback_allowed=False`不变。最终数据不进入学习，当前不含五域自动训练、路由或部署。首个自然先导预设64训练族＋64选择族、两次更新、相同预算上限；GEPA小批与SkillOpt全量反思不等实际算力。离线测试已通过，真实效果尚未产生。[适配说明](continual-baseline-adapters-20260928.md)

**9/29实际接续**：上午队列已完成全部五个开发No-Skill面板；各域结果、unknown和成本见[完整基线报告](noskill-baseline-results-20260929.md)。下午恢复首先确认没有活跃旧实验或容器，不重复运行已完成的generate/score。学习独立环境47项测试无失败/跳过，依赖检查与Docker正负控制通过；冻结源码、官方GEPA及开发划分重新核验后，13:44:49启动SkillOpt单阶段真实学习。输入为同一空父、65训练题/64族与64选择题/64族，GLM-5.3 low/4096、最多两更新、学习器串行。输出保存于Linux `continual-learning-bcb-20260928-a/skillopt-run-20260929-a`，完成后才顺序运行同协议GEPA；任何非零退出停止后续队列，未知不补抽。该队列只做两个开发学习阶段，不自动启动五域final或授予部署权。首5个真实调用均HTTP200且完整，模型健康不等于学习有效。新操作队列可在方法边界读取PAUSE标志，但没有在途学习器的精确优化器断点；暂停仍需核对进程/意图，不能承诺任意中断可无损续训。

启动保护现改为**先完成第一个pending真实请求，再提交其余并发位置**；旧缓存不充当当前连接健康证明，首请求网络失败立即停下，不将未调用题目批量写成模型unknown。原A失败记录保留但不作准确率证据；pending恢复修复晚于B启动，没有改B快照或分数。Linux启动先执行`proxy_on`；因客户端不读环境代理，B的`model.proxy`显式冻结同一受信PJLAB网关，其他历史运行默认仍不启用代理，不改旧缓存。该网络路径已有真实HTTP200和完成回执，密钥不进入清单。

**9/29 16:48终态核查**：上述SkillOpt实际于14:50:45以`evaluation_unknown`停止。第一轮候选开发选择28/64，相同空父39/64，配对2胜13负49平，原生gate拒绝；第二轮父仍为空并复用父训练记录，新候选选择仅60/64（26 pass、33 fail、1截断unknown），余4未提交、无该轮gate决定。279逻辑调用/280 HTTP，372,248已报告tokens；所有调用回执闭合。截断响应为HTTP200/length，不是Docker或网络故障。接续队列和监测均已退出，GEPA从未启动；本次只读复核1219个终态绑定产物，没有重跑或修改协议。当前优化器不支持精确中断续训，不得直接补抽该位置。[完整结果总表](experiment-results-20260929.md) · [学习摘要JSON](results/skillopt-learning-20260929.json)

**9/29新授权：独立8192截断恢复诊断。** 新入口[truncation_recovery.py](../skillopt/continual_eval/truncation_recovery.py)不修改上述停止状态：输入为旧运行的封存源码、任务/候选、确证HTTP200/length的原调用及新恢复清单；`prepare`校验并冻结164个调用，`run`保持原system/user、模型、推理配置和评分，仅增加一次8192-token调用，`report`单独报告恢复子集的交付、原生评分和追加成本。KOR160、Sheet1与候选1可重新评分；ALF2仅重试已关闭环境中的原动作提示词，不宣称episode恢复。其他unknown和已可判定结果不重跑，原4道未提交选择任务也不自动补跑。开放恢复intent仍fail-closed，已完成恢复回放不再付费；这是事后诊断，不是完整8192基线、原优化器续训或Skill准入。专门测试在本机与Linux均15/15通过，独立review后18:09:51在Linux启动；首条真实响应完成后才释放最多10并发。18:11:44应用户暂停已退出：5个恢复结果保留、10个开放调用待核查、149个未提交。此次外层shell退出导致内存状态未保留，恢复不能直接CONT或静默重抽，见[暂停交接](truncation-recovery-pause-20260929.md)及[新协议记录](truncation-recovery-8192-20260929.md)。

## 10. 下一步与维护约定

**9/30终态核验与下一档预算**：8192恢复C实际于9/29 20:02:44完整结束，148/148、0开放调用，早于20:16暂停请求。105份确证length仍正文为空，构成下一轮全部输入（KOR104、Sheet1，68独立题/15家族）；已可交付的43份、A操作中断及B通信timeout不重抽。新`prepare-budget`入口已验收：读取完整冻结父协议/源码/回执，校验父运行完整、API缓存与位置回执匹配，生成独立v3的32768/read600协议；运行中锁定祖先只读，沿用原prompt、Skill、任务及原评分器，有界派发和协作PAUSE，不写回旧分数。默认8192和PJLAB上限不变，只在BigModel GLM-5.3客户端允许32768并绑定新请求身份。本机312相关测试、Linux178专测通过，独立review无阻断；D于15:11:36后台启动，首长响应HTTP200/stop（239.945秒、11,671报告tokens）确认后已释放最多10并发。首题交付恢复但原生评分fail，不能将交付当准确率提升。新旧成本与分母分层报告，不续训SkillOpt/GEPA、不补旧面板未提交题。[终态数据、实施状态与新协议](truncation-recovery-32768-20260930.md)。下方保留前一日实施与故障记录。

**9/29安全接续与通信等待修复**：Linux核查确认旧恢复A的5个完成结果仍在，10个开放调用没有API终态缓存；新v2的`prepare-resume`只冻结149个未触碰位置，另存B目录，父源码/证据保持只读。报告继承父5完成、10操作中断与原164分母，不把子任务叫完整恢复。调度改为最多10个在途任务，`pause`命令/正常停止信号停止新派发、等待已预留调用和评分落盘；不再使用SIGSTOP，PAUSE需用户明确resume后才能移除。恢复专测在本机/Linux各24通过。B于19:17:13因首请求3次timeout（366.361秒、用量缺失）停止，余148未提交；单独短健康请求成功（HTTP200、1.190秒、24tokens）。新C于19:25:11启动余148位置，保持模型/提示词/8192/重试不变，仅显式read120→300，绑定实际客户端、service及回执；默认API身份不变，父B终态失败不重抽。Linux同一shell启用`proxy_on`，客户端仍显式绑定批准网关；首响应确认后才释放并发。API与恢复专测Linux134通过、本机扩展217通过，独立review无阻断。A/B封存不再派发，后续仅在C协作暂停/续跑；尚无完整恢复结果，未恢复优化器或批准Skill。[续跑协议、命令与限制](truncation-recovery-resume-20260929.md)

C首个实际响应已确认HTTP200/length（142.506秒、8535报告tokens），达到既定连接健康条件并释放最多10并发；该题仍按输出截断unknown保存，不把网络可用或预算变大当作任务正确。原read120默认不变，C的read300也不等于整个请求总时限；可能发生原定HTTP重试。后续只观察已冻结面板，不因再截断临时增加预算或重复抽样。

9/28用户要求暂停：所有实际实验进程及接续队列已确认退出；ALF B保留50终态、10开放意图和18未启动，BCB保留800预测及516评分。不是所有在途任务都具备可恢复内存状态；恢复前必须核对意图/回执，不能自动重采样。[暂停与恢复交接](baseline-pause-20260928.md)。

9/29恢复按原样SSH复用可用主连接；禁用复用的新连接失败不等于别名不可用。操作者核验并闭合BCB唯一评分中断为unknown、ALF十个无可恢复环境的位置为unknown，保留所有旧完成记录，再运行未执行部分。额外未提交的原子临时意图被精确隔离、不计正式请求；冻结源码不变。接续队列等ALF/BCB完整回执后才做学习环境资格及Sheet B，内存受限原生评分不叠加；学习本身仍需单独验收，不自动长程启动。[恢复实录与报告入口](baseline-resume-20260929.md)

9/29 11:01暂停请求因SSH断开未能发送到远端；13:40恢复后实际确认上午队列已于10:51完成，而非仍处于旧快照。暂停失败记录保留，不把盒盖时间算成模型错误，也不因恢复连接重跑终态。新的单阶段学习与上述No-Skill输出隔离。

当前优先补齐五域真实数据与原生环境验收，先用开发数据诊断难度及交付，再冻结独立final和共同协议、采集No-Skill及真正训练的基线检查点。接下来才连接逐来源协同进化与全域检查点比较。保留修复轨迹学习，在未消费任务上分别评价相关收益、条件反转和无关任务损害；不重复接近满分的小题，不把回退率当学习效果，也不期待各阶段成绩必然单调上升。独立样本量、顺序、可接受退化界需另行冻结。教师课程与Research信息增量仍是独立问题，未经校准的Research不能伪装成获授权反馈；新评测框架不赋予Skill或验证器准入权限。

每次修改初始化、反馈、任务生成、Rubric/Research、判分、门控或运行入口时：更新本文对应输入/输出、实际连接方式、状态与限制；不要只改日期。新重要结果写入[账本](results-and-lessons.md)，保留分母、对照、成本、证据等级与存档链接。历史协议/结果不回写，新版本不继承旧授权。
