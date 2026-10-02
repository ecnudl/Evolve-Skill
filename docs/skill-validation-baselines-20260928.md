# 基线安排与首个 No-Skill 运行

日期：2026-09-28。状态：SearchQA B运行800/800采集、评分和报告均已完成；KOR采集中，Linux后台队列已安排ALF→BCB，尚不报告这些领域成绩。[简短汇报稿](noskill-baseline-summary-20260928.md)

## 当前运行

| 项目 | 冻结设置 |
| --- | --- |
| 名称 | `noskill-searchqa-20260928-b`；A为保留的基础设施失败 |
| 数据 | 既有 SearchQA train 的全部400题；development，不是新的final |
| 次数 | 1条历史、每题2次，共800个逻辑位置；不是800道独立题 |
| 模型 | 原有BigModel `glm-5.3`；temperature=0、low reasoning、每次输出上限4096 |
| 条件 | S0、空Skill、同一公开question/context、一次生成；无Research、无修订 |
| 并发 | 10；首个真实请求通过健康屏障后再放行其余请求 |
| 评分 | 所有产物冻结后原生EM，另报F1/subEM及unknown；不用于Skill学习 |
| 执行位置 | PJLAB Linux独立源码快照；先`proxy_on`，API显式绑定同一受信网关；tmux后台 |
| 计划哈希 | `c85dd295f33a8ccbaa776e083629d920a2a8d5c9eca73bbecfc8a66805495097` |

远端目录：`/root/continual-noskill-searchqa-20260928-b/`；原会话：`continual-noskill-20260928-b`。顺序为check→freeze→generate→score→report，已输出`CONTINUAL_BASELINE_COMPLETED`。`run/predictions/`保留每次产物和请求，`run/host_only/`保留评分。两份分母均800、0缺失，报告哈希`215ca04770a89278a8ca4d9bb5e5249694af6da156757408f343f33c46e4e5ce`。

本地准备文件在`outputs/continual_eval/noskill_searchqa_20260928_launch_b/`（私有、不随Git发布）。只将已有BigModel必要配置通过SSH送入私有目录，未复制其他供应商密钥，不在协议/日志打印密钥。原始数据、完整模型缓存和`.env`均不公开。

### 启动问题与修复

A运行直连BigModel失败：只有1条真实逻辑请求，3次HTTP尝试均连接超时、无HTTP状态，合计126.12秒；用量未知。旧backend把健康屏障异常变成unknown，致800位置都被写出，其中799未真正提交HTTP，不能称为800次模型失败或0%准确率。A的源码、产物、分数和错误回执全部保留，不覆盖；它不进入有效模型成绩比较。

独立网络诊断确认：直连TLS超时；远端`bash -ic 'proxy_on; ...'`后HTTPS HEAD立即200（0.109秒）。当前网关为`http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`，无需认证。`CachedAPI`的`trust_env=False`忽略环境代理，因此新增**显式且绑定协议**的受信网关支持，而不是全局打开任意代理或修改Mac Clash。

编排同时改为先完成首个真实位置，再判断服务健康、提交线程池。首次连接失败只保留该位置，其余仍missing；完整200但截断仍按预算unknown记录、允许健康服务继续。新配置和新目录重新运行同一400题，不筛题、不从失败位置补答案。单并发/10并发的失败、成功和截断分支均有mock测试；初轮相关API/评测测试256项通过。网络规则同步进[AGENTS.md](../AGENTS.md)。

这轮用于先建立新求解协议下的开发基线和成本/难度诊断。旧SearchQA train400、val200、test1400都已在历史GPT复现中产生过预测，不得将旧test直接改称新的独立final。正式新面板可从本地完整Arrow池按历史任务ID及问题指纹排除后预先冻结；不能看本轮成绩后筛出有利题目。

## 已完成结果与初步认识

| 重复 | 正确 / 全部位置 | EM全尝试下界 | 原生EM fail | unknown |
| --- | ---: | ---: | ---: | ---: |
| 0 | 272/400 | 68.00% | 125 | 3 |
| 1 | 280/400 | 70.00% | 117 | 3 |
| 合计 | **552/800** | **69.00%** | **242** | **6** |

794个可评响应的EM为69.52%；F1全尝试下界79.60%，可评F1为80.20%。宽松Substring Match为749/800＝93.63%，只是辅助指标，不能替代严格EM或包装成95%左右的正确率。242个EM fail也不一定全是推理错误，可能含答案形式、冗余或合法别名差异，需要另做归因，不能直接投入错误经验学习。

同题两次：258题均pass、103题均fail、22题fail→pass、14题pass→fail、3题均unknown。397个共同可评题中36个两次状态不同（9.07%），即使temperature=0也不能忽略执行差异；68%与70%不能当作学习进步。这轮只有No-Skill，没有Skill或Research收益。

共800逻辑请求、804 HTTP尝试：最终794个HTTP200、6个HTTP400，另4次无HTTP状态的传输尝试。6个unknown来自同3题的两次请求；没有收到具体错误正文，不能断言是限流或内容审核，没有重抽。已知报告tokens **875,172**，另6份用量缺失，重试的完整计费也未知；不能称为完整总成本。原始私有归档不含`.env`，已核对800份产物与800份评分哈希。[公开聚合JSON](results/noskill-searchqa-20260928.json)

运行后独立review还发现恢复时不能把旧缓存成功当当前连接健康：本地后续版本已改为先同步执行**第一个pending位置**，再放行其余；4个单/10并发恢复测试及旧逻辑负控验证通过。没有修改已完成B快照或重跑B成绩。最终完整相关回归**2,697 passed、0 failed/skipped**（165.47秒），Ruff、相对链接与差异检查通过。首次外层沙箱中2,681 pass/12 fail，失败均为旧macOS嵌套沙箱权限；该模块获准单独复核60 pass，最终全套也通过，原失败不删除。公开聚合计数/F1已与归档800份评分核对，归档未包含`.env`。

## 建议对照与真实准备度

| 优先级 | 对照 | 目的 | 当前准备度 |
| --- | --- | --- | --- |
| 已完成首域开发诊断 | No-Skill | 固定模型原始能力、逐域提升和损害的参照 | SearchQA400×2已完成；其他域待原生资源验收 |
| 首批 | Sequential SkillOpt | 普通Skill进化的主外部对照 | 上游训练/反思/聚合/编辑/门可复用；五阶段串联及同协议适配未完成 |
| 首批 | 有限反思＋经验累积 | 排除仅仅多看轨迹、多写经验的作用 | 需要小型wrapper；不冒称完整Reflexion复现 |
| 首批消融 | Ours＋固定Rubric | 区分Skill学习与验证器进化的贡献 | Coding反馈/更新组件已有，五域学习尚未接通 |
| 首批消融 | Ours＋自适应Rubric，无Research | 判断外部研究是否带来独有有效信息 | 复用同一审阅、执行及更新器；仍需对应领域独立校准 |
| 第二批 | GEPA优化同一Skill文本 | 增加独立的强文本优化基线 | 官方实现可用；本仓库尚无适配，不阻塞首个No-Skill |

完整的Ours＋Research是待比较方法，不把消融组叫作独立外部论文方法。SkillOpt的单文档文本优化和验证选择与当前接口匹配，优先使用真正重新训练的检查点，不拿旧弱Current冒充SkillOpt。[官方SkillOpt](https://github.com/microsoft/SkillOpt)

GEPA可通过官方适配接口连接评估与轨迹反馈，建议只优化同一Skill插槽，不能顺便改变基础输出格式、工具权限或评分器。[官方GEPA](https://github.com/gepa-ai/gepa)

SkillCommit等检索式Skill库方法放在后续：当前入口只有有界文本注入，没有冻结Skill库检索。简单拼接整库会改变其核心算法，不能据此声称原方法复现；是否使用作者实现需要继续核实。[SkillCommit论文](https://arxiv.org/html/2608.15165v1)

## 公平比较必须共同冻结的条件

- 同一Solver模型、基础提示、工具权限、公开修订机会、输出预算与原生评分；目前SearchQA是一次生成，不能直接横比旧harness的成绩。
- 相同学习来源顺序、开发任务和初始状态；迁入下一来源时重新评估父Skill，不拿上个benchmark的分数作当前门阈值。
- SkillOpt使用来源域门；如果另加历史回放，命名为单独对照，并给各方法相同回放预算。
- 预设训练/验证/Research预算上限，同时报告实际tokens、HTTP重试、执行成本和unknown，不能只匹配调用次数。
- 每阶段检查点在独立final评价，但final不参与候选选择、范围推断或后续课程；重复不是独立任务，首个开发诊断不提供跨域安全结论。

## 尚需准备的材料

当前不需要用户再提供key或答案。SearchQA本地原始池已存在；SpreadsheetBench的verified400压缩包已进入独立安全准备流程；BigCodeBench/KOR需要固定版本的官方数据及评分依赖；ALFWorld需在Linux安装TextWorld与真实游戏资产。以上资源准备不应阻塞其他已经就绪的基准。

跨域正式面板、顺序、规模、独立曝光排除记录和执行预算需另行冻结。当前只有SearchQA完成，其余四域保持Pending，不以部分均值冒充五域成绩。

## 后续资源资格检查：不能把文件齐全当作可评分

9/28继续准备时，新脚本[prepare_continual_spreadsheet.py](../scripts/prepare_continual_spreadsheet.py)复用原有固定来源校验、安全解包和不可覆盖写入，保留原80/40/280分区，不修改旧准备脚本或评分器。官方400题均保留；test中的42930有一个命名不一致的gold文件，未猜测配对或静默删题，因此final面板仍blocked。

开发80题的只读检查进一步发现：全部输入预览可读、gold可打开；**60/80无本次发现的先验评分风险，20/80有风险**，其中7题目标坐标字符串无法由当前严格解析器识别，其余73题中13题目标区域有公式缺缓存。7题未继续核查目标公式缓存；两类是本次检查阶段的互斥计数，不表示真实问题绝不重叠。没有筛除任务。此处“无风险”仅指本次资格检查，不保证任务或评分器完全正确；“有风险”也不是模型做错。未运行模型、未计算正式任务成功率、未重算gold公式，也未打开final工作簿做评分资格检查。完整私有记录在`outputs/continual_eval/spreadsheet_prepare_20260928_a/development_qualification.json`。

因此暂不启动SpreadsheetBench付费基线：先解决/明确版本化处理评分覆盖问题，再解释该域成绩，不能靠把unknown当fail或只报告剩余题制造效果。KOR的准备规模预定为官方125规则、1250题中的50规则、500道development题，按类别与规则整体隔离，每题2次；其余规则在模型输出出现前保留为独立用途。BigCodeBench完整原生镜像与ALFWorld环境继续准备。最新评测/API针对性回归239项通过，其中执行与恢复相关49项也单独复核通过（不相加为288个独立测试）。

Linux同一真实80题面板已准备并得到相同60/20静态计数。另执行3个自建原生控制：正确输出pass、错误输出fail、缺依赖unknown；首次含环境探测共4次容器调用、6.766秒。源码/回放约束修正后，新目录复测4次容器调用、4.239秒，再次回放0次；两次都清理确认、0模型调用、0正式题成绩，不能算6个独立控制样本。复盘还发现上游metadata有2条`exclude`说明（train/test各1），其中train提示在20个技术风险之外；未据此自动删除任务或改分母。[完整聚合记录](results/continual-spreadsheet-preparation-20260928.json)。

BigCodeBench全量镜像下载会话为`continual-bcb-download-20260928`，仅获取资源、尚未完成原生验收；ALFWorld资源下载会话为`continual-alf-assets-20260928`，使用独立环境，不修改既有实验环境。两者都没有发出模型请求，下载后台运行不等于基线实验已运行。

## KOR-Bench No-Skill：已启动，尚未出分

会话恢复后完成KOR真实面板与原生评分验收，已启动`continual-noskill-kor-20260928-a`。官方源码固定为`bb8194dff8e51e2e2247cf62aa9932c3d57d53d7`，1250题、125个规则；每类别按固定哈希顺序将25个完整规则分为10/5/5/5，分别用于development、验证器校准、Skill确认、final。**本轮仅500道development题、50规则族×2次＝1000位置**，其余三区各250题/25规则未调用模型。规则级隔离不等于证明无预训练污染或所有语义近重复已排除。

同SearchQA：BigModel GLM-5.3、temperature=0、low reasoning、4096输出预算、并发10、空Skill、一次生成，无Research与修订。生成后自动在隔离Docker内调用哈希固定的官方评分器；不向模型反馈隐藏评分。冻结计划`2cafefa8e2392d67629e91d263c21b6e25ca4ffba1a8e6aeeb5d972da7da97c6`，目录`/root/continual-noskill-next-20260928-a/korbench-run`。06:27:10 UTC早期检查已有15份产物，健康屏障已通过；这不是最终数量或成功率。

原生资格控制五类各一正一负，修正版10/10符合预期、清理全部确认；含探测11次容器调用、66.226秒，0模型调用。首次控制给本来已有括号的官方答案再次包装，造成2条正控失败，已保留失败回执；仅修正工程控制，不修改评分器/数据，也没有把失败算成模型错误。这十条控制不覆盖全部评分规则。

[启动聚合记录](results/noskill-korbench-20260928-launch.json)保留数据分母、版本、路径和证据哈希，实际用量、unknown与准确率均待完整回执。No-Skill各域可按资源就绪顺序采集；**后续Skill进化的五域顺序不变**。

## 恢复后的原生环境进展：不是模型成绩

- **BigCodeBench**：官方镜像19层压缩SHA、解压diff_id与config身份全部通过，已加载到Linux的独立`/data/docker`存储。实际包版本0.2.4，`untrusted_check`签名与worker一致；两个手写tiny unittest正负控制分别pass/fail、清理确认。尚未准备并验收完整真实任务集，不能据此称全benchmark环境完全正确。资格预算4GiB/1CPU/300s须在正式协议中另行冻结。
- **ALFWorld**：4027游戏资源已准备，旧39条train路径及sidecar/logic全部存在。独立环境补齐传递依赖；仅修改新入口，单游戏目录初始化、原生/模型一致步数上限、有界正常关闭与终止兜底。最新六类型原生专家控制6/6成功、look负控制fail，0活动子进程与资源泄漏警告；前一版本5/6及固定失败实例的事后9步人工见证均保留。专家控制有随机性，6/6不是GLM准确率，也不是Skill收益。尚未启动该域付费No-Skill。

上述修复没有改变运行中KOR的冻结源码；本地最新评测与API合并回归**253 passed**，Ruff通过。完整零模型环境回执私有备份在`outputs/continual_eval/resource_recovery_20260928/`。不能把数据下载、依赖导入、原生控制通过与正式模型基线完成混为一谈。

## 后续正式开发采集队列

9/28 14:49（UTC+8）已启动单调度会话`continual-baseline-queue-20260928-a`。KOR模型采集退出且1000位置闭合后，启动ALF；ALF完成后启动BCB模型采集。始终只有一个10并发模型池。BCB的8GiB原生评分等待其他原生评分结束；队列异常保留回执并停止，不自动重试不明确的模型请求。

| 待跑项 | 冻结规模 | 原生预算 | 计划哈希 |
| --- | --- | --- | --- |
| ALFWorld | 官方train中既有39任务/39场景族×2=78episodes | 每episode50步，独立ALF环境 | `f21770e1e7a812a53f404999f0a8fe30813b8f65b819a96e02d4700626efb0ba` |
| BigCodeBench | 官方v0.1.4本地development400题/399词面近重复族×2=800位置 | 官方0.2.4镜像，8GiB/1CPU/300s，评分串行 | `d6b3a86a8557793a2aa1c7c6016139fc081b53c3b0bcbb9bf957eb16b63087d4` |

两者均为GLM-5.3、low、4096输出上限、空Skill，独立源码/目录。ALF旧train确认为官方train，val/test未在本轮执行；BCB按完整词面近重复族先分400/128/128/484，后做4道预选参考解正控与1负控，均符合预期，0模型调用。词面筛查不保证完全语义独立。BCB实际主机cgroup14GiB，不能把8GiB预算声称为上游30GiB复现。[BCB完整准备记录](results/noskill-bigcodebench-20260928-preparation.json)

外部GEPA已固定官方commit、明确Pareto/反思/选择的接入边界；实际训练仍需开发反馈授权、预算与中断测试。没有把普通反思改名为GEPA/Reflexion，也没有将旧评测的隐藏评分暗中输入训练。[适配准备](continual-baseline-adapters-20260928.md)
