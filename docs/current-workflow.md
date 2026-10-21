# 当前完整流程：Skill 与验证器如何协同进化

**10/4新增KOR无标签适用性验证器（零调用、已审查）。** [kor.py](../skillopt/applicability/kor.py)（v5）只读KOR公开规则、题面和回答，按规则文本哈希登记25条规则（operation 10、puzzle 6、cipher 9），满足全部公开约束判通过、可证违反判失败、其余未知（精确有理数；无理数用区间包络，只能证伪；cipher在公开文本留有选择时按所有可接受读法判定，读法间不一致即未知）；[report_kor_applicability.py](../scripts/report_kor_applicability.py)把每个观测绑定到冻结计划、声明Skill的检查点、分数与预测，用黄金与官方分数只检验仪器。E/F两份S1上，无标签同位置净值（−14/−21）与官方（−13/−20）几乎一致，并发现14道KOR题黄金违反自身公开约束；v5的cipher检查与官方0分歧，F S3的cipher损害（20胜/49负）可不看标签测出。它是学习阶段检测跨域损害的测量仪器，尚未接入学习或部署。见[验证器报告](kor-applicability-verifier-20261004.md)。后续探针阶段试点（新探针上比较原S1、带无标签证据的机制化改写与无证据对照改写）的生成器与运行器均已审查，按用户选择待F完成后付费运行（v7约674次调用，按同规则真实均值更正后约4.0M tokens，启动前需用户再确认）；另备v8（探针生成器v5加入72道cipher探针、证据示例按类别轮流，约1,106次调用/6.0M tokens，需用户批准），见[方案](kor-applicability-step3b-plan-20261004.md)。

**10/4新增BCB反馈内容试点（已就绪、未运行）。** 学习v7新增仅限BCB＋SkillOpt的显式档案`bcb-execution-evidence-v1`：失败的训练执行在反思输入中另附脱敏证据（内置异常类、失败位置分类、候选自身失败行；不含隐藏测试正文、消息或期望值），默认档案仍为标量。[run_feedback_ablation_pilot.py](../scripts/run_feedback_ablation_pilot.py)复用F的SkillOpt S1为标量臂，只改反馈档案重跑一次，同面板同派生评测源码配对比较；Codex四轮审查ACCEPTABLE，零API真实冒烟通过，付费运行等F结束。见[试点报告](feedback-ablation-pilot-20261004.md)。

**10/5新增五域标准划分与test评测。** [fivebench-split-v2](fivebench-split.md)为五个bench固定train/val/test（及reserve）：train只用于学习、val只用于选择、test只用于最终报告；BCB/KOR/Sheet沿用项目9/28分区（development/skill_confirmation/final），SearchQA与ALFWorld用原生SkillOpt划分（SearchQA的test为原生test中固定抽取的400题）。清单绑定研究F并校验F只评测过train、只在train内学习；它声明的是“对所评方法留出”，不是经历史暴露过滤的独立final。此前C/D/E/F表中的分数都是train上的分数。[evaluate_fivebench_test.py](../scripts/evaluate_fivebench_test.py)在test上评测一个已完成研究的各个不同策略（No-Skill与每次被采纳的更新）：沿用该研究各域冻结的评测配置，只把面板换成test、分区改为`final`、重复1次，在其派生评测源码中运行并校验代码/运行环境身份；今后的主实验方法也按这份划分评测。

**10/3新增零成本范围路由诊断。** [report_scope_routed_deployment.py](../scripts/report_scope_routed_deployment.py)输入冻结五域研究的协议、阶段记录与公开契约结构，按“训练证据交付类型”授权Skill，范围外复用No-Skill观测，输出强制/路由两套配对矩阵；严格核对阶段链、方法、服务和复用观测的证据哈希，只读公开字段结构、不读结果。它不是部署授权，也不替代主线的Skill Gate。10/4在F上做了前瞻检验（规则在F任何阶段闭合前冻结）：S1、S3路由优于强制（+31、+44个净位置），S4反而差14个——Skill级授权随阶段累积，目标域一旦被授权，来自其他域的规则也一并进入，因此需要规则级适用条件（第3步）。

**10/3 18:57：新F（序列v4 / 学习v7）运行中，先SkillOpt后官方GEPA。** Skill接口提高到32,000字节；新策略在只改长度字面量、逐字节核对的派生评测源码中评测，Sheet评分器在派生源码下重新17控制资格；GEPA新增父Skill-unknown排除、候选新unknown取父分数并最终成对复核。**10/4 17:46 SkillOpt五阶段已完成**（5次尝试、4次完成学习，最终Skill=S4），只有QA有清楚收益；GEPA五阶段运行中，完成前不比较两种方法。详见[F报告](fivebench-f-skillopt-gepa-20261003.md)。

## 10/6工程更新：学习v8（泛化门控）与单域阶段重做

**背景（零调用诊断）：F在测试集上只有QA可信有效，因为S1/S4的接受都是64–99个选择位置上净胜1题的噪声，S2已接受的候选被后续失败丢弃，KOR学到的内容在未见规则上不迁移。** Codex独立审计另确认：v5–v7的成对选择允许“解决的未知”抵消“新增未知”，可在候选丢失确认通过题时仍接受（P1）。诊断表与依据见[学习v8说明](learning-v8-generalization-gate-20261006.md)。

**新显式版本 `continual-learning-v8`（[POLICY_V8](../skillopt/continual_learning/recovery.py)），不改写F/v7的任何记录。** 输入：开发面板内按种子抽取的训练族（KOR按类别分层30规则×3题）、**标准划分val部分作为选择集**（partition `skill_confirmation`；[role_partition](../skillopt/continual_learning/contracts.py)）、父Skill、预算、v8策略；反馈档案固定为`benchmark-labeled-failure-feedback-v1`（[feedback.py](../skillopt/continual_learning/feedback.py)）：失败的**训练**题附上期望答案（KOR/QA）或脱敏BCB执行证据，选择题和成功题仍只有标量，求解器提示永不含标签。门控（[skillopt.py](../skillopt/continual_learning/skillopt.py) `_margin_selection`）：固定分母配对净胜≥max(3, ⌈2%·n⌉)、改善族数>退化族数、双方已知覆盖≥50%、候选新增未知按失败计；候选新含≥12字符训练标签直接拒绝（`_label_leak`）；原生analyst提示追加迁移要求（`TRANSFER_PREAMBLE`）；后续迭代失败时保留已接受前缀。官方GEPA在v8下得到同样的标签反馈，其最优候选经同一门控与泄漏检查（[gepa.py](../skillopt/continual_learning/gepa.py) `_guard_official_best`）。求解行8线程并发：[ledger.py](../skillopt/continual_learning/ledger.py)加锁、回执发布与在途移除原子化、预检不把本进程在途调用当未知。输出与v7相同：候选或父、阶段状态、步骤记录（新增wins/losses/net_wins/required_net_wins/families等字段）、成本与证据，无部署授权。

**入口：[run_fivebench_g_stage.py](../scripts/run_fivebench_g_stage.py)（`fivebench-g-stage-v1`）** 在F的冻结引用上重做一个API-only域（BCB/QA/KOR）的学习阶段：`prepare`（零调用，开发面板须等于F协议记录的哈希，val面板按划分源文件哈希绑定，父Skill绑定F阶段记录）→`learn`（F客户端服务核对；BCB/KOR取F原生锁）→`test`（仅被接受的更新；用已完成测试评测的同一面板、派生评测源码、服务、评分运行时、代码身份评测一格，worker结果绑定请求与检查点，与记录的No-Skill测试格逐位置配对，unknown单列）。`--method gepa --gepa-source`在同一条件下运行官方GEPA（其反思提示追加同一迁移要求）；`--parent g:<已完成阶段目录>`把上一阶段部署的Skill作为父（仅限已完成阶段，同研究/划分、兼容工具哈希、重验清单/面板/结果绑定）；`test --test-benchmark <域>`评测其他域的测试格；`status`给出经验证的阶段结局（退出码0=接受更新、10=无更新、其余=停）。Linux启动：[单阶段](../scripts/run_fivebench_g_stage_linux.sh)、[三域重做队列](../scripts/run_fivebench_g_queue_linux.sh)、[GEPA重做队列](../scripts/run_fivebench_g_gepa_queue_linux.sh)、[三域链](../scripts/run_fivebench_g_chain_linux.sh)（BCB→QA→KOR，每个被接受Skill测三域）、[双链启动器](../scripts/run_fivebench_g_chains_linux.sh)；零调用汇总[report_fivebench_g_stages.py](../scripts/report_fivebench_g_stages.py)。边界：链覆盖API-only三域，不含Sheet/ALF（需原生学习环境），没有跨域val守卫（跨域效应直接在test表上看）。测试：v8专测16项、工具4项、回归345项通过；Codex两轮审查记录见说明文档。运行状态与结果以[说明文档](learning-v8-generalization-gate-20261006.md)和账本为准。

**10/7：显式`continual-learning-v9`（[POLICY_V9](../skillopt/continual_learning/recovery.py)），只改接受规则，其余与v8相同；v8的运行、记录与清单不变。** 动机是10/6的实测：同一Skill重复执行时6–10%的位置会翻转（见[学习v8说明](learning-v8-generalization-gate-20261006.md)§6），v8的固定边际（3–5题）约等于一个标准差的纯噪声，KOR上两次被val接受的更新在test上都不成立。v9的门（[skillopt.py](../skillopt/continual_learning/skillopt.py) `confirm_selection`，GEPA的最终守卫共用）：①第一遍val只做**筛选**——按**族**计符号（KOR一条规则、ALF一个场景、其余一题一族；每族取其配对差之和的符号），精确单侧符号检验p≤0.10且净胜>0、双方共同已知覆盖≥50%；②通过筛选的候选与其父Skill**都重新在val上取一遍新样本**（评测键带`rollout≥1`，只有v9允许选择集带rollout）；③**只用确认这一遍**决定：族级符号检验p≤0.05/本阶段可尝试的候选数（Bonferroni），净胜>0，共同已知覆盖达标。第一遍的任何数据都不进入被接受的p值，重复任务从不当作独立样本合并。统计含义：在这批固定的val族上，对“族级方向优势来自采样噪声与择优”的条件符号零假设做确认（每阶段误接受≤0.05）；不是平均增益检验，也不是对未见族泛化的检验（后者由test衡量；v9设计参考过10/6的test结果，同一test面板上的数字不是v9效果的独立证据）。预算：`reflection_max_tokens` 8192（10/6带标签的KOR反思曾溢出4096）、`max_metric_calls` 8000。解析器策略v2（`strict-json-invalid-escape-control-v2`，[reflection_json.py](../skillopt/continual_learning/reflection_json.py)）：字符串内的原始控制字符按词法转义、解码文本不变、偏移入审计——10/7首个v9阶段因analyst回复中的原始换行在策略v1下被判无效JSON而Pending（目录保留），修正后以新快照/新链标签重启；第二次启动又因analyst回复缺逗号（词法不可修）而Pending，因此v9再加`reflection_json_retries: 1`：解析拒绝后用同一提示附格式提醒重发一次（新逻辑id，两次回执与审计都保留），再畸形仍Pending；v8/v7不重试。入口仍是[run_fivebench_g_stage.py](../scripts/run_fivebench_g_stage.py)，`prepare --learning-version v9`；新增`test --replicate k`：对**已完成**阶段部署的Skill再做一个独立测试格（文件后缀`-r<k>`，不与主格合并；空父且无更新的阶段部署的是空Skill，其重复格即No-Skill的重复测量，用来估计基线自身的波动）；`status`/`learn`回放/`g:`父阶段在使用前核对存档学习证据（封存的identity绑定清单、结果记录的每个回执哈希仍在且无多余回执）。Linux：[run_fivebench_g_night2_linux.sh](../scripts/run_fivebench_g_night2_linux.sh)（No-Skill三域重复格→v9 SkillOpt链）；链脚本用`G_LEARNING_VERSION=v9`时要求复用的下游阶段也是v9。v9专测与工具测试见[test_continual_learning_generalization_v8.py](../tests/test_continual_learning_generalization_v8.py)（v9部分）与[test_run_fivebench_g_stage.py](../tests/test_run_fivebench_g_stage.py)；实现与fixture通过不等于实验证据，v9的效果以实际运行记录为准。

## 10/7工程更新：学习v10——主方法（Rubric→probe→Research）接入同一协议

**此前G系列（v7–v9）跑的都是两条基线优化器加方法无关的协议升级，主线B的验证器从未接到五域协议上；10/7按用户决定接入Rubric→probe→Research路线。** 显式`continual-learning-v10`、方法`rubric_research`（[POLICY_V10](../skillopt/continual_learning/recovery.py)、[contracts.py](../skillopt/continual_learning/contracts.py)方法/版本/反馈profile三者互锁）：v9的门、解析器、重试与预算全部保留，**只换失败train行的反馈来源**——不再附benchmark标签，而是附[verifier.py](../skillopt/continual_learning/verifier.py)产出的无标签报告。每步在父Skill已执行的train行上：①有界开发视图（公开题面、产物、宿主审计pass/fail——标为宿主信息）→plan→Research臂可取冻结的16页Python 3.11官方文档（经manifest登记的PJLAB代理）→synthesis出七字段可复用条件化策略（引用须是文档逐字摘录，v3起按空白折叠匹配——抽取文本保留硬换行；synthesis严格校验失败带确切错误只重试一次`synthesis_repair`；v5起验证器任一调用（plan/synthesis/probe/审阅/Research/裁判）的回复不是一个合法JSON对象时，同一请求附格式提醒（只含解析器固定原因与位置，不回灌回复内容）重新取样一次，二次失败才按原单元结果处理——真实运行中1,505次回复有8次不可解析，其中一次plan失败使SearchQA第0步退回默认策略；v5只用于新链）；②BCB每题≤2个公开probe（入口函数JSON调用＋期望值，同一实现两次调用相等，或v4起的`raises`——题面写明的异常，移植主线pilot的`expected_exception`；contract_quote须为题面子串），QA/KOR改为不知参考答案的裁判对策略义务判pass/fail/unknown；③BCB执行前审阅keep/drop，有语言事实问题且Research臂时取≤2页文档、可带引用修正期望值（引文规则与①同一函数`_citation`），未审阅的probe绝不执行；④BCB把kept probe生成官方harness格式`TestCases`，经评测同一条`backends._native`在同一pinned容器执行，逐probe判定（v4：只有末行以本组probe派生随机数标记开头的harness断言算fail、同标记的序列化错误算unknown，候选自己抛的异常一律是诊断性error，候选可控文本不能决定结果），清理未确认即停；⑤宿主侧校准（`host_only/verifier/<step>/calibration.json`）：宿主判pass的产物上失败的probe是误拒、整行丢弃，宿主判pass且执行了probe的对照行≥5、检出≥1且丢弃前误拒率≤0.25才授权本步报告与策略文本进入analyst，否则本步analyst拿到与v9相同的提示、Skill循环按标量证据继续，下一阶段只继承最近一次通过校准的策略。analyst端：失败行`Feedback.verifier`文本须等于重新读取的同一证据密封授权报告（[skillopt.py](../skillopt/continual_learning/skillopt.py) `_bind_traces`/`_authenticate_policy`，绑定manifest、步、策略哈希、本步rollout），系统提示附`VERIFIER_PREAMBLE`（禁止把probe输入/期望值/实体写进Skill）；每次容器执行先写intent再写receipt，清理未确认即阻止阶段完成；验证器调用按已提交intent封顶；提案identity含策略哈希与全部报告哈希；验证器调用是账本新角色`verifier`（`max_verifier_calls`/`verifier_max_tokens`单独封顶）；`verifier/**`与`host_only/verifier/**`进入阶段artifacts与G工具证据盘点。Rubric按域随链共同进化：结果记`verifier_policy`映射，`learned.json`记其哈希，`--parent g:<dir>`绑定读入，下一阶段取本域条目（无则冻结默认）。更新器仍是原生SkillOpt，因此v10对v8/v9隔离的是反馈来源这一个轴（标量／验证器／oracle标签）。工具：`prepare --method rubric_research --learning-version v10`，链脚本方法/版本互锁，新启动器[run_fivebench_g_main_linux.sh](../scripts/run_fivebench_g_main_linux.sh)；设计、简化与预期见[学习v10说明](learning-v10-rubric-research-20261007.md)；专测[test_continual_learning_verifier_v10.py](../tests/test_continual_learning_verifier_v10.py)。**实现与fixture通过不是效果证据**；Research源只对BCB定义，Sheet/ALF仍在API-only工具之外，校准用同一批train产物（主线pilot用独立校准分区）。

**验证器v6（10/8夜，Codex设计两轮一致、代码审查第14–15轮；只用于新链与注册重放，链e/f的v3/v4记录与分母不变）**：①plan可解析但不合模式（如缺`status`）时带字段级错误修复一次（`plan_repair`），合法弃权不修，加上v5格式重试plan最多4个账本请求；QA/KOR的plan提示多一句“三个字段都必填”，裁判提示与默认策略不变。②BCB的plan/synthesis/probe/审阅共享一段冻结的执行能力说明`HARNESS_CAPABILITIES`；新增`structure` probe：返回的pandas DataFrame（形状、完整有序列/索引标签）、Series（长度、名称、索引）、numpy ndarray（维数、形状）、matplotlib Axes（居中标题、x/y标签）或Figure（仅类型），可选文档化元组/列表元素（`select`）；期望里的每个非空字符串（含整数标签的字符串形式）必须出现在合同引文里，数字须由题面与JSON参数完全确定（审阅确认），空字符串/空名称须题面明确；选择或类型不符计断言失败，元数据读不出/MultiIndex/投影过大计unknown，失败信息保留完整观察投影供审计。④⑤校准分母只计**断言判定（pass/fail）的行**（只有报错的行不再算对照——v4下它们被算作对照，压低了误拒率）；`structure`须按原始结果单独达到≥5个判定对照行且自身误拒率≤0.25才准入，否则其结果记`unadmitted`（保留原结果）、不计入检出/对照/报告；按类型分别记录行数（对照、误拒、检出，准入前后）与probe数（报错、unknown、未准入），规则标识`train_host_audit_kind_admission_v6`。**机制筛查**：验证器改动先跑冻结train重放（[verifier_replay.py](../skillopt/continual_learning/verifier_replay.py)、[replay_fivebench_verifier.py](../scripts/replay_fivebench_verifier.py)、[启动器](../scripts/run_fivebench_verifier_replay_linux.sh)）——只读核验源阶段的身份、结果与完整证据清单，重建其第0步完整train产物（与源验证器所见行集合相同），用当前验证器从当前默认Rubric重跑、自有清单与账本、不调solver/analyst/门控/test；只在主表全部完成的标记出现后持F锁运行，不自动续跑，未决即无结论。是否开新链g的三条标准（结构类准入、≥1条经独立公开合同审计的结构检出、整步授权）在重放前冻结。

**验证器v7（10/8凌晨，链e KOR阶段事故后与Codex设计一轮一致；`rubric-probe-research-verifier-v7`、`verifier-feedback-v7`，探针harness仍为v6）**：只改验证器调用的交付处理，按恢复策略新键`verifier_delivery: closed_length_recovery_terminal_unit_v1`声明（没有该键的早期v10清单行为不变，账本也拒绝其验证器恢复）。①闭合长度截断（HTTP 200、完整流、冻结模型、`finish_reason=length`/`truncated_content`，含正文为空的纯推理回复）恰好一次长度恢复：同一请求、冻结恢复上限`length_max_tokens`=131,072、逻辑ID加`:length-recovery:1`，由账本`recovery_of`绑定到原intent哈希（与solver的既有规则相同，禁止恢复的恢复）；截断的部分回复从不解析。②恢复后仍截断、闭合的空回复（`stop`/`empty_content`，或ok但只有空白）、闭合的供应方过滤（`sensitive`/`provider_content_filter`）是该单元自己的结果：无值、无格式重试、无plan/synthesis修复；**一行中任何一次验证器回复（含有界Research的plan/解决回复）是终端结果，该行不执行probe、无判定**（Codex第17轮：否则Research不可用时审阅保留的probe照样执行）；其余未交付回执（断流、非冻结模型、HTTP错误、未分类结束原因）仍停阶段。③v5格式重试只针对完整非空却不是一个JSON对象的回复；一次`Verifier.call`最多4个账本请求（首次＋恢复＋格式重试＋其恢复），plan/synthesis各自的修复调用另计；全部计入`max_verifier_calls`与用量账；`max_reported_tokens`是提交前检查的**已报告用量停止阈值、不是预留**，大恢复在并发下可越过它并以预算停阶段。④每步校准与summary新增`coverage`（按宿主pass/fail分列的合格行、判定行、无判定行、无probe行、终端交付结果行；率只描述被覆盖的行）与`delivery`（调用、格式重试、长度恢复、账本请求与HTTP尝试分开计数、按类型的终端结果），重放结果同样输出。⑤链式Rubric映射：本阶段自己领域的记录必须是当前版本（缺省用当前默认），其他领域的记录在本阶段不起作用、原样（含原版本号）承接，可来自已完成的v3/v4，经领域键、七字段与哈希校验；以后激活旧记录的阶段在定义迁移前一律拒绝。**主方法S3替换（事先冻结）**：[run_fivebench_g_main_s3_linux.sh](../scripts/run_fivebench_g_main_s3_linux.sh)从链e已完成的SearchQA阶段（S2）以默认KOR Rubric新建KOR阶段（新链标签）、学习、若接受则测三格；无论结果如何（接受更新／完成无更新＝沿用S2的已有三格／pending＝S3缺失）都作为S3，不再替换；成功行只在测试格经[verify_fivebench_g_cells.py](../scripts/verify_fivebench_g_cells.py)零调用只读核验后写出（封存request＝工具为所部署Skill构建的request、result与检查点绑定、summary＝在临时目录重算的结果；无更新时核验S2的三格），已开始未完成的测试格不重新提交而是停队列待复核；链e的KOR尝试保留为中断记录与成本。注册重放随之修订为协议v2（运行v7、新输出目录与日志，源rollout与三条标准不变），完成标记换为三条基线/链f加S3替换队列，STOP守卫随之转到S3替换日志并只匹配该队列自己的停止行`STOP (main S3 <tag>)`（日志里还有工具JSON，如Skill文本）。**已执行（10/8）**：S3替换（标签h）04:16–08:10完成、无更新→S3＝S2三格（零调用核验通过）；注册重放08:20完成，结构性检出0→按冻结标准不开链g（数字见[账本](results-and-lessons.md)）。

**反馈归因研究（10/8，Codex两轮设计一致，GPT-6-Astra ultra；只用train/val，不改主表与任何冻结协议）**：主表分不出“Rubric演化是否改进验证器”与“验证器反馈是否改进Skill提案”，因此另起两个附加实验，[预注册与诊断](feedback-attribution-studies-20261008.md)。新包[feedback_study](../skillopt/feedback_study/)放在`continual_learning`之外（`contracts.sources()`与冻结文件不变，已与快照m逐字节核对），复用v10的裁判提示、解析、v7交付处理、账本与solver适配器。**L1 固定Rubric组件实验**（`fivebench-fixed-rubric-study-v1`，[fixed_rubric.py](../skillopt/feedback_study/fixed_rubric.py)、[CLI](../scripts/run_fivebench_fixed_rubric_study.py)）：S2父Skill在90个KOR train任务上一次新rollout，由冻结的默认/h0/h1/h2四份Rubric各判一次（`FixedRubricVerifier`：无提案、无Research，各组独立记录树与逻辑ID，执行顺序为封存的随机交错表，首格单独执行作健康屏障）；端点以全部合格行为分母，主对比h2−默认检出率（族级精确sign-flip），误拒安全条件与盲审包事先冻结。**L3 匹配单步反馈实验**（`fivebench-matched-feedback-study-v1`，[matched_feedback.py](../skillopt/feedback_study/matched_feedback.py)、[CLI](../scripts/run_fivebench_matched_feedback_study.py)、[启动器](../scripts/run_fivebench_matched_feedback_linux.sh)）：KOR，8个区组都从同一个S2父Skill出发；每区组一次共享新rollout→默认与h2两份冻结Rubric判同一批行并各自按v7规则校准→标量/默认/h2三组各一次原生提案（`propose_arm`与`propose_native`逐步相同，只是各组有自己的逻辑ID和自己的报告树；未授权组去掉报告与Rubric指导、保留独立抽取）→候选与处置在任何val调用之前封存→父Skill和每个变动候选各在完整val上评测一遍（登记的随机顺序与rollout），无更新/超预算回落到父Skill；主对比h2−标量的逐区组通过数差（区组级精确sign-flip）。任何原生提案失败（analyst JSON重试后仍拒、回复截断）都使整个研究pending、不续跑（Codex L3-1裁定保留）。L2（带门控的Rubric演化）推迟。**状态：L1 09:55–10:54完成（代码审查2轮后运行），登记主对比阴性（h2检出7/20、默认9/20，p=0.69），数字见[账本](results-and-lessons.md)；L3代码审查5轮后ACCEPTABLE（准备时封存并在运行前于锁内比对整个执行代码闭包），10/8 10:58–10/9 06:17完成：登记主对比h2−标量成立（+5.0/250，7正1负，p=0.047）；h2−默认不显著（+2.6，p=0.46），不能归因于Rubric演化本身。数字见[账本](results-and-lessons.md)。**

## 10/9工程更新：学习v11——主动证据驱动的Skill进化（无固定val关卡）

**背景与目的（用户10/9决定）**：v10的每个stage都以固定val集为接受/撤销的必经关卡；验证器的检查是域级Rubric逐行实例化，没有"要区分什么"的原因假设，报告按步整份授权，更新后没有新任务或回放证据；L1/L3只能说明验证器反馈改进单步提案、归因不到Rubric演化。v11把进化主线改为 train执行→识别验证缺口与原因假设→按需Research→生成并执行诊断检查→条件化分级反馈→修改Skill→少量**新**任务＋历史回放→保留/撤销/暂存，**不再有val角色**（动态任务与回放是学习过程数据，不是最终评测；test仍只按要求报告一次）。设计文档：[学习v11说明](learning-v11-active-evidence-20261009.md)。

**实现（零调用，分支`research/active-evidence-skill-evolution`）**：新兄弟包[active_evidence](../skillopt/active_evidence/)（与`feedback_study`同理放在`continual_learning`之外，冻结学习源码不变）。协议记录是**v10形状的兼容记录**（账本/适配器/反馈投影/原生桥按版本字符串门控，`contracts.manifest`又拒绝空selection，故包内按同一字段形状构造，`selection_families=[]`、全部development任务以低层`train`角色授权），真实身份在扩展`active_evidence`（协议`active-evidence-learning-v11`、step/challenge族划分、臂、限额、包与执行代码闭包哈希）。每步：step子集新rollout→绑定行（挑战池任务永不进入反思/诊断，由封存manifest推出而非调用方参数）→**任何更新支出前预留挑战容量**（不足→pending）→诊断臂：纯代码triage与批摘要、按冻结配额选代表案例（失败/成功各半、同族配对优先）、一次diagnoser调用给出≤4条原因假设（支持/排除观察、可选事实问题、需保留的案例）、假设绑定的检查（BCB：冻结probe提示＋新`state`种类——参数调用前后JSON快照比较，只有合同引文命中"保持输入/原地修改"线索才可采纳；确定性去重→**有限盲审**（不传产物、宿主状态、rationale、假设结论）→容器执行；QA/KOR：冻结裁判加焦点）、按需Research（只在审阅提出事实问题时：≤3页白名单文档、引文须逐字且与问题共享内容词、修正期望重新准入、无来源/失败/无引文→不执行）、**分级**（`confirmed_violation/preserved`需审阅keep＋契约引文＋执行判定＋依据为contract/documentation；裁判最高`pending`；未解决事实`unknown`；契约未规定`not_applicable`；抛错`error`）、每行分项报告（成功行也可带PRESERVED）与步级摘要（确认/排除/保留/范围/例外/未证明）→原生更新器（报告与摘要须等于从磁盘重读并校验封存的记录；analyst系统提示不再把Rubric注入为规则）→候选冻结后封存抽样（`fresh`挑战池真实任务、`replay`Current通过的step行、`local_fix`Current失败的step行，族分层、按协议身份与步号种子、排除此前步抽过的任务；执行前对照manifest与本步评测校验）→**两个Skill都重跑**（新rollout key 1000+10·step+{0,1}）→冻结穷举决策表（no_update／无挑战臂直接采纳／成对已知不足或挑战未完成→park／回归超限或净负→revert／净胜≥阈值→keep／其余park并记建议限制的新增hunk；候选unknown不计输）→证据链`chain/<step>.json`（每环`intervened`为可观察参与，不是因果收益；`fact_needs`记录假设声明需要的事实是否真的到达Research、未到达的原因，未解决的事实以"不可编码为规则"的措辞进入analyst摘要——10/9首轮真实运行发现h1的事实需求从未被咨询而链上只有空`research`，由此补上）。中断返回完整封存pending记录，从不续跑。四个登记对照：`feedback∈{scalar, diagnosis, diagnosis_research}`×`post_update∈{none, challenge_replay}`。

**入口**：[run_fivebench_g_stage.py](../scripts/run_fivebench_g_stage.py) `prepare --method active_evidence --learning-version v11 [--arm-feedback] [--arm-post-update]`（不读val；step子集=F的outcome-blind train抽样，挑战池=F development面板其余任务，全在canonical train内）→`learn`→`status`/`test`/`--parent g:`（`learned.json`含`decisions/arms/evidence_chain_hashes`与每步`decision/challenge_summary`；证据盘点含`chain/challenge/diagnosis/host_only/triage`与顶层标记）；工具10/8版本哈希`d5c1e017…`进入兼容表。Linux启动器[run_fivebench_active_evidence_linux.sh](../scripts/run_fivebench_active_evidence_linux.sh)（`G_SOURCE_ROOT`必填、`G_SKIP_TEST`）。预算`BUDGET_V11`=v10＋`max_iterations 1`、`max_metric_calls 12000`、`max_verifier_calls 3000`、`verifier_max_tokens 8192`。离线smoke：`python -m skillopt.active_evidence smoke --output <dir>`（全fixture，只证明控制流程）。测试：[test_continual_learning_active_evidence.py](../tests/test_continual_learning_active_evidence.py)51项＋[工具测试](../tests/test_continual_learning_active_evidence_tool.py)7项（10/11；10/10傍晚为41＋3项，10/9为31＋2项）；v10/工具/L3回归124项不变（全量continual_learning/feedback_study/docs边界测试522项通过）。Codex代码审查两轮：第1步6项与第2–4步8项must-fix全部修复（中断记录落盘、边界来源、draw校验、含更新器估计的预留与逐案容量检查、报告认证、迭代上限、修正期望二次盲审、`state`精确比较与否定感知线索、摘要试探措辞、v11研究提示、格式重试交付规则、按步页数上限），清单见[学习v11说明](learning-v11-active-evidence-20261009.md)§5。

**边界与刻意不做**：Sheet/ALF不支持；QA无执行、KOR形式检查未接入；文档白名单仅标准库；`state`线索为正则启发式；有限盲审仍看到检查本身；`--rollout-source`（导入封存v10 rollout共享训练经历）、`restrict`受限修订、KOR合成实例、Rubric前瞻晋升、`reference_val`均预留未做；**实现与fixture通过不是效果证据**，真实单轮运行见[账本](results-and-lessons.md)。

**已演练（10/9下午，真实GLM-5.3 low，BCB；逐条记录见[账本](results-and-lessons.md)，公开导出[fivebench-active-evidence-20261009.json](results/fivebench-active-evidence-20261009.json)只含计数/哈希）**：主线r（diagnosis_research/challenge_replay，父=空）一轮keep→test 256/484 vs No-Skill 239（净+18，与此前每个"有Skill文本"策略对同一格的差距同量级，不归因于机制）；对照臂scalar/none与diagnosis/none各一轮按臂定义直接采纳，三份Skill同为"按合同逐条审计"类通用文本；第二轮s（快照u：探针归一化＋修复调用＋覆盖感知推断）同配置park（fresh净0、replay 2处回归）。共同事实：执行检查几乎只得到"保持/待定"，0确认违约、0次Research介入，宿主侧失败多为隐藏期望值断言——BCB上v11的信息瓶颈与v10相同。t（快照u，父=r的Skill）同配置keep（fresh净+2恰在阈值）→test 256/484、净+17，与父r的256/484逐位58处对称翻转——4处新增规则在test层面不可分辨、只增加58%的test成本；v（快照v：`fact_needs`记录，父=空，与r/s同配置）park（fresh净0）——链上第一次记下Research未介入的原因（h3的库事实需求名下无可准入检查）；同配置三次仅r一次过阈值。对照臂test格未跑、阶段w（快照v、父=r）准备未启动（决定）。**10/10 判决实验**（零调用Step 0表明Skill文本可测地改变产物但不同Skill都落在同一区间；Codex方向审查四轮后ACCEPTABLE）：新增研究臂`--arm-feedback hidden_failure --arm-post-update matched_scalar_branch`（只能成对出现）——同一rollout喂两个更新器分支（S=scalar臂原包，M=失败开发行的有界隐藏测试异常消息，释放档案封进manifest并先审计），两个冻结候选在候选冻结后抽的242题开发留出集上配对比较（Tango区间/双侧符号检验/unknown最坏情形，预先指定的结局类），不部署、不读final；设计见[v11说明§7](learning-v11-active-evidence-20261009.md)。x4结果：242题留出集上消息分支对标量分支净+3（d=+0.012，95%区间[−0.038, +0.064]）→`inconclusive`，排除大效应；同设计下方法自身的`diagnosis_research`包（阶段y2，Research首次介入）净+1（d=+0.004，[−0.042, +0.050]）→`inconclusive`。两项合起来：反馈内容经Skill文本通道能改变的通过率只有几个百分点（BCB、GLM-5.3 low）；下一步转向KOR或改变Skill作用方式，先用同样的配对设计验证。逐条见账本，导出见[fivebench-active-evidence-study-20261010.json](results/fivebench-active-evidence-study-20261010.json)。**10/10下午：配对研究v2（同期参照分支）**——事后零调用对照显示x4/y2的四个候选在同一留出集上对空Skill也只有0到+4个百分点（F的No-Skill开发集基线，八个区间全含0；见账本），而原设计没有同期的“无更新”分支，只能回答“包A对包B”。因此`matched_scalar_branch`升级为研究v2：两个分支解完留出集后，**父Skill**以及`prepare --reference name=g:<已完成的G阶段目录>`指定的至多4个**具名参照Skill**（如带验证集门控的基线阶段部署的Skill；工具核对同研究/同划分/已完成/Skill哈希，且其训练族与本阶段挑战池不相交，不重新核验其学习证据）各在同一批留出位置上求解一次（rollout键`1000+10·step+3+i`，封存于`challenge/<step>/references.json`，只评测、不部署、具名参照的文本不进任何诊断/分析提示）。配对记录新增：每个分支减每个参照的同一套统计与结局类、单侧“不比参照差超过5个百分点”标志（仅就共同已知位置；整批另看unknown最坏情形）、具名参照减父的**仪器检查**（只有它为`useful_gain`时对该参照的比较才可解释，`q3_interpretable`）；分支未产生更新、与参照逐字节相同或参照与父相同的对比记为未测量。处理包未送达（诊断未完成、没有任何行报告、或超过一半被尝试案例因格式失败丢失）时，研究在任何更新器调用之前以pending停止；逐案交付记账（`checks/format_failure/no_checks`，以修复后的有效回复为准）进入摘要与证据链，方法自身的臂行为不变。设计备忘`docs/handoff/active-evidence-reference-study-design-20261010.md`（Codex三轮：2项、3项must-fix后ACCEPTABLE）；测试39＋3项。首次运行在SearchQA（唯一有清晰Skill效应的域，方法本身不做任何改动；该域诊断走裁判检查、Research不可达）：阶段`searchqa-active-a`，参照=SkillOpt v9与主方法v10的QA阶段Skill（与本阶段同一128个训练族），结果见账本。结果：留出242题通过数 父169／S 194／M 196／main_v10 197／skillopt_v9 204——一步、未经任何选择的更新比无更新高约10–11个百分点（`useful_gain`），与带val门控的v10的Skill没有显示出差异、比标签反馈的v9低3–4个百分点；诊断包对标量包未确立差异（M−S +0.008）。**10/10傍晚：更新后决策规则v2（方法的一部分）**——零调用的条件重抽样表明v1的fresh规则（24题净胜≥2）在已实现结果上以噪声级行事（对观测到的+10个百分点差异只有约3/4的保留频率，对与0相容的对比保留或撤销各0.2–0.4）。v2：证据单位为**族**，对非持平族做精确单侧符号检验；顺序为 回放损害显著→revert、fresh共同已知不足→park、fresh损害显著→revert、fresh增益显著且总量护栏（题级净胜为正）且不利补全（unknown位置记为候选失败后仍成立）→keep、其余park；每个集合按种子分两半以平衡顺序执行（一半先父后候选、一半相反）；请求限额fresh 96／replay 32／local-fix 8（只报告）／α=0.05，有效fresh数按挑战池封顶、`min_paired_known`=ceil(0.9·n)在准备阶段封进manifest；针对一次候选决策步、在“各集合内非持平族符号独立且公平”的条件零假设下P(keep)≤α、P(revert)≤2α，不声称阶段级或链级保证。措辞约定：决策使用**从固定保留的开发挑战池中抽样的新面板**，不使用规范val划分与重复的整面板验证，但保留池承担选择功能；运行点是用开发证据（含SearchQA）选定后前瞻冻结的。设计备忘`docs/handoff/active-evidence-decision-v2-design-20261010.md`；实现与测试见[v11说明§9](learning-v11-active-evidence-20261009.md)。三个方法模式阶段与另一种子的独立重复结果一致：SearchQA keep（13胜0负；11胜1负）、BigCodeBench park（两次都是5胜4负）、KOR park。**10/11：日志审计后的两处改动**——(1) 证据交付修复：裁判判定显式进入报告与摘要（`JUDGED …`、裁判线索），摘要不再把“无可执行检查”写成“建议不改”、不再引用Rubric字段（其“例外”句曾在每个SearchQA阶段变成Skill里的弃权规则），诊断器视图按字节预算保留完整题面，未被假设引用的案例做通用检查，探针与假设文本的表面问题确定性修复；(2) **组合感知筛选**（`prepare --arm-update screened`）：原生提案后在全部已知训练行上实测精确文本（候选、去一变体、单编辑变体、父的两次对照，交错执行），按冻结规则选一个或弃权——这是训练行上的分数监督选择，不是效应估计；更新后决策（规则v2）不变。新增研究臂`--arm-post-update matched_selection_branch`（筛选的选择对原生候选）、`--train-families`、`--limit key=整数`（只能覆盖诊断/更新的形状类限额，如`view_rows`；决策与筛选的运行点不可覆盖）、以及`--parent`/`--reference`的`m:<研究目录>:comparator|treatment`形式（已完成研究里未经选择的分支）。(3) **通过案例对照**（10/11凌晨，诊断内）：一条“解释失败”的假设隐含“通过的产物上不出现该违约”，此前没有任何检查去看（裁判线索读作“4个失败案例中4个、0个通过案例中0个”）。现在每个**通过**的代表案例会被分配至多`max_checks_per_case`条尚未引用它的错误类假设作为对照（按稳定的假设顺序轮转、确定性；分配封存在摘要的`controls`里）；逐案提示里对照条目只带**中性角色`probe`**（不告诉裁判/探针生成者该产物已通过宿主评分——对照身份留在宿主侧的封存记录里）；摘要把“失败案例上被判失败数”“已判的通过对照上被判失败数（另列分配数）”与“假设自己声称的通过案例”分开计数；若一条假设的执行违约既在它解释的**宿主失败**案例上被确认、又在通过对照上被确认，推断记为`also_on_controls`，摘要措辞为“在通过对照上也观察到（特异性与原因未定——探针的期望、对契约的读法或隐藏测试的覆盖都可能有问题）”，不写成“不解释失败”。解释限度：对照上的裁判判定仍是模型判断；分配不保证裁判真的检查了该假设；对照只在已检查的少量案例上说明“未能干净地区分”，不证明假设无关。(4) **探针路径的格式修复**（10/11清晨，快照h，仅影响BigCodeBench的可执行检查）：探针缺少`obligation_id`时补为唯一可采值（写了其他取值仍拒绝）；回复超过`max_checks_per_case`条时按给定顺序保留前几条并记`over_limit`（此前整包拒绝）；状态类探针的“不适用”记录改从解析器所见的规范化探针重建。未改：引文仍只校验“是题面子串”，引文与期望是否相关依赖有限盲审；模型主动返回空探针列表的案例（封存日志里约三分之一）没有检查。**读数工具**：留出集一个族有多题时（KOR-Bench：一条规则10题）配对研究记录里的题级区间只作描述，主读数改用[active-evidence-family-summary-20261011.py](handoff/active-evidence-family-summary-20261011.py)（零调用：按族的通过率差取均值与t区间、非持平族的符号检验，逐对比的覆盖率与资格检查），约定见`docs/handoff/active-evidence-kor-study-design-20261011.md`。**10/11夜间已演练的范围与状态**（结果见[v11说明§11](learning-v11-active-evidence-20261009.md)与账本）：配对研究7次（SearchQA 6、BigCodeBench 1）、选择研究与精修试验8次、方法模式9次（其中`scalar/challenge_replay`即“pass/fail一步更新＋决策规则v2”在SearchQA五个种子与BigCodeBench各跑通，带筛选的方法模式跑通1次）；诊断包与精修的增量都**未建立**，筛选/弃权/对照/决策机制按设计工作；快照h的两条探针修复路径在真实运行里尚未被触发（只有离线测试证据）；KOR-Bench配对研究运行中；“把精修回合集成进主循环”暂缓；本次10/11夜间的阶段都没有读取test（此前v11的r/t阶段在10/9读过；后续读取需负责人批准）。设计约定见`docs/handoff/active-evidence-screen-design-20261011.md`与`…-refinement-design-20261011.md`，实现见[v11说明§10](learning-v11-active-evidence-20261009.md)，结果见账本。运维：tmux等待循环须用精确会话名`-t =name`（前缀匹配曾让对照臂队列空等2小时）。

**10/11下午新增（快照i＝h＋本项；Codex方向审查1次、代码审查2轮后ACCEPTABLE；v11测试60通过、更宽回归564通过/17跳过）：可选的训练行影子读数**。输入：方法模式（`challenge_replay`）阶段在`prepare`时加`--limit train_panel_rows=N`（缺省不存在该键，缺省阶段的限额、抽样、结果与决定都没有新字段）。过程：候选冻结后，从训练步的**整个任务名单**（含步内评测为unknown的行）按步族分层轮转、不看结果地抽N行（`train_panel`），与回放/局部修复的成员互不影响；与它们重合的位置复用其评测（每题每个Skill只解一次），其余位置按自己的ABBA顺序求解；运行前由封存清单、面板文件与本步封存评测**重建并逐项比对**抽样。所有挑战抽样与执行顺序的种子取"去掉可选限额后的清单哈希"（`sampling_identity`），因此fresh面板及其顺序不随是否加面板而变。输出：结果里多出`train_panel`摘要（与fresh相同的按族配对摘要＋按步内状态分层的计数＋复用位置数）与`fresh_size_matched`（fresh抽样顺序的前n个位置；fresh不足时标为不可用）；决定记录里多出`in_sample_shadow`——把规则v2的表原样套在训练面板上会得到的动作（同样的回放否决、90%覆盖、族检验、总量护栏、不利补全），标记`decision_input: False`。**生效的决定仍然是规则v2在保留池fresh面板上的决定**，下一步Skill不受影响。用途与边界：这是一个**证伪试点**——测量"只用训练行做决定"是否与保留池的决定一致、训练行上的效应是否虚高；分析者见过这些行，所以其p值只是操作性启发，一致也不等于可以把规则换成只用训练行（那需要新版本与在未用过的数据上的前瞻比较）。约定与读数脚本：[设计备忘](handoff/active-evidence-in-sample-shadow-design-20261011.md)、[shadow-summary](handoff/active-evidence-shadow-summary-20261011.py)、[相对快照h的diff](handoff/active-evidence-in-sample-shadow-20261011.diff)。状态：已实现并审查；真实运行（SearchQA/BigCodeBench/KOR-Bench各一条历史起）10/11 14:40排队，结果见[账本](results-and-lessons.md)。同日的两份**未执行**文档：[一次前瞻留出读取的协议草案](handoff/active-evidence-prospective-holdout-protocol-draft-20261011.md)（负责人批准了一次读取并要求留出性不可质疑；草案指出规范test单独不够，并给出零调用的暴露审计与多臂设计，待负责人定）与[SpreadsheetBench/ALFWorld接入v11所需改动的清单](handoff/active-evidence-sheet-alf-wiring-notes-20261011.md)（只读调查；pass/fail臂可接，诊断臂暂不可；未动代码）。
**10/11晚新增（快照j＝i＋本项；`active_evidence`包与快照i逐字节相同，只改阶段工具；Codex方向＋代码审查：代码无阻塞问题，读数与措辞按其要求修改后放行；v11与工具测试69通过，开发机快照内同样69通过）：固定文本参照，用作“通用指令”对照**。输入：配对研究阶段（`matched_scalar_branch`／`matched_selection_branch`）在`prepare`时可加`--reference name=f:<文本文件>`，与已有的`g:`（完成的G阶段部署的Skill）和`m:`（研究阶段未经选择的分支候选）并列，最多4个具名参照。过程：工具读入该文件作为一份**固定的、由操作者提供的**Skill文本（非空、通过同一Skill字节预算与命名规则），阶段记录封存文件路径、字节数与sha256（`action: fixed_text`），清单携带文本；学习阶段像其他具名参照一样，在两个分支与父参照之后用它把留出集各解一遍（自己的rollout键），它不作父Skill、不进入诊断器／分析者／Research的任何载荷、不参与任何决定。输出：研究记录里“参照−父”与“各分支−参照”的配对差与区间（研究v2原有的计算）。**边界**：`f:`路径信任所给文本，无法证明其作者见过什么——这一点只能由设计备忘披露（[通用指令对照设计](handoff/active-evidence-generic-control-design-20261011.md)：三段文本由操作助手在读过一份学到的SearchQA Skill和token分析之后手写，是“知情的平凡基线”）；参照按块排在分支之后、不与分支交错，服务漂移可能偏置参照对比。状态：已实现、离线测试与真实数据的仅准备（零调用）演练通过；六个带参照的阶段（SearchQA×2、BigCodeBench×1、KOR-Bench×3）已准备，是否已运行与结果见[账本](results-and-lessons.md) 10/11晚各条。

**10/11深夜新增（快照k＝j＋本项；`active_evidence`包仍与快照i逐字节相同，只改阶段工具与报告工具；Codex审查GO、无必改项，可选建议已采纳；v11与工具测试71通过，开发机快照内同样71通过）：固定文本作父Skill，空Skill作具名参照，用于“从通用指令出发再学一步”**。输入：v11阶段在`prepare`时可用`--parent f:<文本文件的绝对路径>`（旧方法拒绝），配对研究另可加`--reference name=none`（只在父非空时允许；父为空时父参照本身就是空Skill）。过程：工具读入文件作为阶段的父Skill（非空、通过同一字节预算），阶段记录封存`parent_action: fixed_text`与文本的sha256，清单携带文本；此后每次加载阶段都重读该文件，文本变了就拒绝（`Parent changed`）；训练步的rollout、两个更新分支和父参照都从这份文本出发，空Skill参照像其他具名参照一样只把留出集解一遍。输出：研究记录里“各分支−父（固定文本）”“空Skill−父”“各分支−空Skill”的配对差与区间；报告工具导出时只写文件名与哈希。**边界**：`f:`路径信任所给文本（作者见过什么只能由设计备忘披露）；各臂按块运行、不交错，服务漂移可能偏置任何与参照块的对比（含主对比）；配对研究不部署任何Skill。状态：已实现；离线有工具级测试（准备、重载校验、拒绝情形）与包级完整流程测试（非空父＋空参照的配对研究）；真实数据零调用准备演练通过（fg17：与gen17同一批训练行、限额、包与模型记录）；付费阶段fg17／fg19已排队，是否完成与结果见[账本](results-and-lessons.md) 10/11 21:41条及其后各条；设计见[从通用指令出发的设计备忘](handoff/active-evidence-from-generic-design-20261011.md)。

**10/12新增（快照l＝k＋三个新脚本；阶段工具与`active_evidence`包不变；Codex三轮审查，前两轮的14项必改全部采纳；相关测试81通过，本机与开发机快照内一致）：在新题上成对评测冻结的Skill，用于“从合理初始指令学习还剩多少”的主对比**。(1) **新题样本**`scripts/make_searchqa_fresh_sample.py`：从本机已缓存的`lucadiliello/searchqa`（原生val／test所在的`validation`划分、同一修订）里按种子抽4,000题，剔除全部2,000道原生题和规范化后重复的问题，分成四块各1,000题；只输出计数与长度统计，不显示题目内容；物化数据写在`data/`下（git忽略）。块A用于本次研究，块B留给后续对照，块C、D留在操作者本机、不拷到实验机，留给那一次留出读取。(2) **零样本初始指令**`scripts/generate_zero_shot_skill.py`：分析模型只看一张公开任务卡（求解器固定指令原文、输入字段、公开指标），经v11账本做一次reflection调用写出初始Skill；只生成一次、不挑选；`check`子命令只在生成记录为completed且文件哈希相符时放行。(3) **面板评测**`scripts/run_active_evidence_panel_eval.py`（`prepare`／`run`／`report`）：输入一份外部题目文件与若干具名Skill（`name=none`空Skill、`name=f:<绝对路径>`固定文本、`name=g:<完成的G阶段目录>`该阶段learned.json记录的Skill）；`prepare`拒绝与规范划分任何分区共享题目id或族的面板、拒绝在面板的族上训练过的阶段，并在读取阶段Skill前核对其封存的清单／面板／结果绑定与全部留存学习证据；`run`经v11同一条调用路径（冻结的求解模型、账本、适配器、评分器）让每份Skill把每道题各解一次，题目按种子打乱切块、块内各臂顺序逐块轮转；结果从落盘的封存评测记录重建，任何中止都留下可读的pending结果，从不续跑；`report`零调用，给出各臂通过数与成对对比——单文本对单文本为Tango区间，组（多条学习历史）对文本或按记录种子配对的组对组另给逐历史值、历史层t区间与保守的交叉区间，覆盖率按计划题数计算并给出缺失结果的上下界。输出：`eval.json`（封存的准备记录）、`learning/`下的调用与评测记录、`result.json`。**边界**：只做评测，不学习、不选择、不部署；新题在包里带`development`标签，表示开发阶段的评测数据，读过之后即为用过的开发证据，不是最终测试；交叉区间是近似的保守做法，5条历史时不保证恰好95%覆盖。学习历史用现有阶段工具的`scalar／none`臂（只给对/错的一步更新，不经任何选择直接采纳）配`--parent none`或`--parent f:<文件>`产生。设计见[从合理初始指令学习的设计备忘](handoff/active-evidence-learn-from-b-design-20261012.md)，队列脚本[u1](handoff/active-evidence-learn-from-b-queue-u1-20261012.sh)；状态：已实现、离线测试与真实数据零调用准备演练通过；付费运行是否完成与结果见[账本](results-and-lessons.md) 10/12各条。

**10/13新增（负责人10/13凌晨的三项指示；快照o、p；都经Codex审查；`continual_learning`冻结代码一行未改）**。(1) **用生成的测试任务代替验证集（回到Rubric＋Research版本，快照o）**：`scripts/generate_searchqa_tasks.py`（`prepare`／`run`／`check`）从某个种子的128道**训练题**出发，写手模型只看每题的公开字段（问题、检索片段），为每题写至多2道关于片段中**其他事实**的新问题，答案必须是片段里的原文片段并附支持引文；先过确定性过滤（答案与引文须在片段中逐字出现、引文含答案、问题不含答案、长度限制、与开发集问题及已收题目不重复），再由独立的审阅调用判定“有依据／唯一／最短自然形式／不是原题的改写”；不使用任何参考答案、验证／测试／备用分区的题或求解结果，过滤也不看求解器答案。输出与原生SearchQA同构的`items.json`（题＝原题片段＋新问题＋所提答案作唯一参考）。阶段工具`prepare --generated-val <生成目录>`（替代`--val-source`，只对`skillopt`与`rubric_research`方法）把一次**已完成**、且恰由本阶段训练题生成的结果绑定为选择集：同一训练题写出的多道题在门的符号检验里算**一个族**；阶段记录写明`selection_source: generated_from_this_stage_training_tasks`，不读取任何规范验证数据。此后冻结的v10学习器原样运行（验证器、更新器、两遍符号检验门、至多3轮）。**边界**：仍然存在带标签的选择题，只是它们是合成的；生成题与训练题共用片段、并不独立；目前只有SearchQA有生成器（代码题需要可执行测试，KOR需要规则实例生成器）。设计：[generated-validation-design](handoff/generated-validation-design-20261013.md)。(2) **跨数据集选择实验（快照o）**：`scripts/run_cross_bench_selection.py`（`prepare`／`run`）用两份**已准备、未开始**的v9 SkillOpt阶段作输入，围绕冻结函数（`Adapter.evaluate_rows`、`propose_native`、`confirm_selection`等）逐步重跑v9循环：训练行与带标签的提案来自数据集A，两遍符号检验门作用在数据集B的验证行上；A的验证行与B的训练行不参与学习和选择，循环结束后用来对空Skill、最终Skill与具名参照做留出评测。两套账本各自记账，同一把锁；任何中止都留下pending记录、不续跑。设计：[cross-bench-selection-design](handoff/cross-bench-selection-design-20261013.md)。(3) **分析者提示词档位（快照p＝o＋本项）**：v11包的`updater.ANALYST_PROFILES`与清单字段`analyst_profile`（默认`native`时清单形状不变）；`generalize_v1`只在分析者系统提示后追加一段“泛化要求”（把问题分成答题契约／过程／个例并只为前两类改；每处修改写成一条带条件的规则；需两条轨迹支持；优先改写已有规则而非追加；保持简短），求解器、合并、排序提示与更新机制都不变；只允许用于pass/fail反馈＋原生更新；阶段工具`prepare --analyst-profile`（其他子命令给出该参数即报错）。设计：[prompt-chain-design](handoff/prompt-chain-design-20261013.md)。状态：三项都已实现，离线测试通过（本机相关套件91项），真实数据零调用准备演练通过；付费运行在10/13凌晨排队，是否完成与结果见[账本](results-and-lessons.md) 10/13各条。

**10/13凌晨的执行情况与读数工具（无新的方法代码；队列脚本与只读辅助脚本存于`docs/handoff/`）**。(1) **已真实演练**：生成验证的整条链路（生成→`--generated-val`准备→冻结v10学习→在新题上读数）在SearchQA三个种子上各跑通一次；跨数据集选择完成一个方向（SearchQA训练→BigCodeBench把关），另一方向两次因基础设施中止、仍在重复；分析者提示词档位四个阶段完成、一个中止。结果与分母见[账本](results-and-lessons.md) 10/13条。(2) **编排**：02:57起由一个串行主队列`master-queue-z1-20261013-*.sh`接替原先四个队列（E2读数→跨数据集重复→提示词评测→新题块Q32–Q40→E1→跨数据集进一步重复），另有`generated-validation-queue-z2-20261013.sh`（E2在另两个种子上的重复）与`cross-bench-foreign-texts-queue-z3-20261013.sh`（探索性对照）；所有付费运行共用同一把原生锁，逐个执行。启动闸门：评测前要求握手级探针连续12次正常（约2分钟），跨数据集运行前30次；评测工具运行中的闸门、每块一次重复、从不续跑的规则不变。跨数据集重复脚本从**封存记录**判定目录状态（absent／prepared／begun／pending／completed／invalid；结果须以`cross_hash`绑定到`cross.json`），只在封存的pending之后重复，至多到`-r3`，其余状态一律停下等人工处理。主脚本日志里的`(exit N)`字段无意义（脚本运行中不可改，已披露）。(3) **只读辅助**：`read_reports.sh`（开发机队列目录内）为每个评测块只取**已完成**的那次尝试（首次，否则其`-r1`），列出重复与缺失的块，再调用评测工具的`report`（注意`report --output`是一个参数后跟多个目录）；`cross-bench-foreign-texts-extract-20261013.py`零调用地把封存记录里的Skill文本（含pending运行的候选，经长度与哈希核对）写成固定文本文件并记录来源。(4) **尚未实现**：BigCodeBench与KOR-Bench的生成验证（代码题需要带可执行测试的生成任务；KOR现成的规则实例生成器只覆盖一个阶段30条训练规则中的12–14条，且与官方评分器的参考答案比对不匹配，评估见账本）；提示词档位在代码与规则任务上的运行。**负责人10/13上午的决定**：跨数据集选择这条线到此为止（两个方向都没有被接受的更新，KOR方向不做）；提示词档位做确认实验——队列`prompt-chain-queue-z5-20261013.sh`（8个新种子各学两份一步Skill，原提示词与`generalize_v1`各一，在750道未用过的新题上评测；主对比只用新种子，读法见[prompt-chain-design](handoff/prompt-chain-design-20261013.md)第5节），11:23启动，结果出来后记入账本。

**10/13下午：扩展研究——用LiveMathematicianBench（`livemath`）与OfficeQA（`officeqa`）替换BigCodeBench与KOR-Bench（负责人10/13决定；快照u、v；Codex三轮审查后GO；五域研究F、其划分与全部既有产物不动，在各自快照下仍然有效）**。(1) **为什么换**：BCB与KOR上三种方法都没有被接受的更新，通用或学到的Skill文本只带来几个点以内的变化；SearchQA上一份零样本指令已拿走全部增益。SkillOpt论文的方法对比图显示（求解模型未注明）OfficeQA与LiveMath上“模型自己写的Skill”几乎无效而学到的Skill有十几到二十个点的增益，DocVQA则与SearchQA同型且只有图像输入（本工具链的客户端只发文本）。(2) **新增的两个任务（单次调用）**：`livemath`——公开字段为问题与五个选项（已按题目哈希固定顺序渲染为“A.…E.”），求解约定“只在`<answer>`里给出一个选项字母”，宿主评分为最后一个答案标签内的字母与正确选项字母相等；`officeqa`——**单次调用形式**（问题＋题目来源提示所指的已解析公报页面，不是论文测的多轮检索），约定与SearchQA相同，评分为原环境的规范化精确匹配（无数值容差）。两者都**严格**：已送达但不合格式的回复判错并计`invalid_format`，从不记为unknown；服务商已完成且报告了用量的空回复同样判错，未送达／截断／被过滤／超长的回复仍为unknown。求解消息与两份余量试验逐字节一致（有测试）。(3) **代码位置**：`continual_eval/datasets.py`（`EXTENSION_BENCHMARKS`、模式、导入器、五选项与文本上下文校验）、`backends.py`（约定、`_score_answer_tag`、空回复处理）、`core.py`（`LEARNING_EXTENSIONS`只放行学习清单里的运行时项，五域评测计划不变；OfficeQA评分器进入源码身份）、`continual_learning/feedback.py`与`skillopt.py`（带标签反馈的文本＝答案；livemath为正确选项字母，短标签不触发泄漏检查）、`verifier.py`（两个领域的默认Rubric、任务文本与视图；OfficeQA只判答案形式与问题范围）、`active_evidence/profiles.py`与`protocol.py`（两个受支持的画像，**只实现“对/错反馈、无更新后步骤”这一臂**，其余臂在准备阶段即被拒绝）。(4) **扩展研究与划分**（`scripts/make_extension_study.py`，零调用）：`data`把一个任务的题目物化为开发面板、验证面板与划分之外的评测块并封存布局；`study`写扩展研究协议`extension-study-v1`——逐字沿用研究F的模型记录、学习服务、重试选项、原生锁与Skill预算，绑定新开发面板的路径与哈希，无参照计划、无评测源码；`split`写划分清单`extension-split-v1`。阶段工具的`_study`在每次加载时复核它与F的一致以及所固定布局的哈希；`check_split`要求扩展划分**恰好等于**所固定的布局（各部分、族、面板哈希、评测块、计数——记录自己的哈希只证明它自己）；`check_val_source`要求验证源就是布局自己的文件；`check_evaluation_block`只允许评测布局自己的、未改动的评测块；`test`对扩展研究直接拒绝（暂无测试格，封存的测试部分只以题号存在）。扩展研究里v9／v10阶段可以用固定的初始指令作父Skill（那里没有链、没有测试格；默认起点为初始指令）。(5) **LiveMath布局（已在开发机建成）**：608题、每题五选项、一题一族（一篇论文一题）；测试＝论文划分的125道测试题（只列题号、从不渲染）；评测块＝余量试验用过的200题（2026-03至06月，8块×25，在划分之外）；验证128题；训练池155题（每阶段按种子取128）。**OfficeQA布局（负责人10/13晚决定：按SkillOpt论文自己的划分）**：训练＝论文的50道训练题（每阶段按种子取48道，v11需留非空余量），验证＝论文的24道验证题，测试＝论文的172道测试题（只列题号、从不渲染）；**没有评测块**——每道题都在划分之内，面板评测工具对OfficeQA的任何题目文件都会拒绝；一题一族，论文的划分并非按文档互斥（训练与测试之间共用40份公报）。因此OfficeQA上在读测试集之前只能看到带门控学习器的门控结果（24题上的两遍符号检验：初筛4胜0负起可过，复核需6胜0负或如9胜1负）；任何OfficeQA Skill的留出测量就是那172道测试题，属于读测试集，需负责人明确同意并另建放行机制（目前工具拒绝测试格与划分内题目）。(6) **两份余量试验**（`scripts/pilot_livemath_headroom.py`、`scripts/pilot_officeqa_headroom.py`；设计与读法见[试验备忘](handoff/benchmark-replacement-pilot-20261013.md)）：在接入前用冻结求解器测无Skill／零样本指令／原代码库的人写初始Skill／论文的GPT-5.5参考Skill；直接经冻结客户端调用（学习账本当时还不认识这两个任务），每个位置先写封存的意向再写结果、提交前预留最坏情况的失败余量、按尝试累计用量、从不续跑；提交为滚动式（至多8个在途），因为个别回复会推理到token上限、耗时半小时以上。(7) **已知风险**：LiveMath上个别求解耗时极长（65,536 token上限加一次131,072的长度恢复），一次rollout要等最慢的一行，带门控的阶段会很慢；一题一族、通过率接近五选一的随机水平，门的检出力有限；OfficeQA的访问条款含“不得用答案训练在OfficeQA上评测的模型或抬高分数”，负责人10/13决定按SkillOpt论文的做法（训练题答案作反馈、留出题只评分），数据与答案不发布。设计：[extension-study-design](handoff/extension-study-design-20261013.md)。状态：接入已实现并审查通过（本机评测与学习套件1,535项通过）；LiveMath的布局、研究与划分已在开发机零调用建成；LiveMath余量试验已读出（各臂均高于五选一的随机水平，见账本）；首批学习运行已排队：LiveMath的一步学习六个阶段（队列z9a）→OfficeQA的三个带门控阶段与六个一步阶段（队列z10，快照w）→LiveMath从零样本指令出发的SkillOpt v9与Rubric＋Research v10、从空出发的SkillOpt v9及200道评测题上的统一评测（队列z9b）；结果见[账本](results-and-lessons.md)。

**10/14：OfficeQA的生成题验证（把10/13在SearchQA上的`--generated-val`接到OfficeQA；快照x＝快照w＋本段四个文件；`continual_learning`与`continual_eval`一行未改，阶段身份不变）**。(1) **为什么**：论文划分的验证集只有24题，冻结的门在24个家族上要6胜0负或9胜1负才接受，10/13夜间三个带门阶段的候选首轮多数偏正却无一通过（见[结果台账](results-and-lessons.md) 10/13 20:04–10/14段）；生成题的家族数上限是训练抽样的48。(2) **生成器**`scripts/generate_officeqa_tasks.py`（版本`generated-officeqa-tasks-v1`；`prepare`／`run`／`check`）：输入是某个种子的阶段训练抽样的**公开字段**（题目与随题的解析页面），不含参考答案、验证或测试题、求解结果。出题调用**不写答案**，只给题面、1–6个页面上印出的数字（原样的值＋逐字引文）、这些数字上的算术表达式（＋−×÷、括号、常数、abs／min／max）与小数位数；**参考答案由代码在有理数上精确算出**（表达式只按封闭文法解析并遍历语法树，不编译、不执行模型文本）。确定性过滤：各字段先限长再解析；引文逐字在页面内，且在页面里引文所在位置，该数字就是某个表格单元格（同一行两条竖线之间）的全部内容（至多带货币符号、百分号与`10/`式脚注标记）——白名单，读页面原文，裁剪引文绕不过，正文里的数不算；表达式里的常数按写法精确读取，且每个数字换成别的值都能得到有效而不同的答案；不是进位边界、小数末位不为0（官方评分是规范化后的字符串精确匹配）；题面任何数字记号的数值不等于所用数字或答案；与源题／训练题／已收题不同。再经一次独立复核调用（数字是否所指、计算是否所问、读法唯一、单位与取整写明、与源题不同、只有读页面才能作答，六项全真才发布）。生成题保留源题的页面作上下文，同一源题的题为一个家族。(3) **共享流程**：运行生命周期（两把锁、封存的意向／结果、任何中止都是不带题目文件的pending、从不续跑）沿用`scripts/generate_searchqa_tasks.py`，后者为此加了benchmark钩子（过滤、载荷、题目形式、版本与工具身份）；SearchQA的行为与既有生成目录的可核对性不变（原测试原样通过）。OfficeQA生成的工具身份同时绑定两个文件。(4) **阶段工具**：`--generated-val`按`GENERATED_VAL`表分派（SearchQA、OfficeQA），核对生成与阶段同研究、同划分、同种子、源题哈希恰为该阶段的训练抽样，且生成题与划分内任何题／家族不重合；用了它的OfficeQA阶段不读`val_panel.json`，也没有测试格。学习器（v9／v10）不改。(5) **局限**：只有数值题与四则运算，没有几何平均、回归、日期／文本答案或图表读数；题面写明单位与取整，检验不了真题的书写习惯；出题、复核、求解是同一模型；生成题与训练题共用页面，**被门接受不是结果**，留出测量仍是封存的172道测试题。设计与事先写定的读数规则见[备忘](handoff/officeqa-generated-validation-design-20261014.md)；队列脚本`docs/handoff/extension-officeqa-queue-z12-20261014.sh`（一次生成＋同种子三个阶段，生成题不足30个家族则不跑阶段；任何中止——含某个阶段pending——都结束队列，不越过它继续）。(6) **状态**：离线测试`tests/test_continual_learning_officeqa_generated_validation.py`（5项：精确算术与封闭文法、确定性过滤、生成＋发布＋评分、阶段绑定与冻结v9学习器在生成题上过门、真实论文划分布局下的零调用准备与v9／v10×空／固定父Skill的绑定，并用探针确认这类阶段不打开验证面板）；全量离线套件1,531项通过。Codex七轮审查：前六轮NO-GO（逐轮收紧确定性过滤——常数经浮点、符号与数字片段、裁剪引文、平凡表达式、指数写法、分数；过滤从黑名单改为“表格单元格全部内容”的白名单；读数规则删去两处过强推断；队列在pending处停机），第七轮对生成与三个阶段均GO。开发机零调用冒烟（快照x）：与快照w只差本段的五个文件；48道源题恰为`oq-v9-z41`的训练抽样；同参数阶段的清单哈希与快照w下相同（学习身份未变）。10/14 09:56队列z12启动（一次生成`officeqa-gen-g41`，随后三个阶段）。真实运行的结果见结果台账，代码存在不等于方法有效。(7) **10/14下午的探索工具**（负责人的“rubric作为可运行代码”想法；不是流程的一部分）：`scripts/pilot_officeqa_rubric_exec.py`——结构化求解约定＋宿主可运行rubric（数字是页面单元格、封闭文法表达式在有理数上精确求值、按要求位数取整），派生臂以重算值计分，零新增调用；设计、读数规则与零调用证据见[探索备忘](handoff/rubric-exploration-20261014.md)。它改变的是求解形式，不是Skill进化。(8) **10/14夜：rubric形式与粒度的配对反馈研究**（负责人20:30的问题；`skillopt/feedback_study/rubric_form.py`＋`scripts/run_rubric_form_study.py`，协议`fivebench-rubric-form-study-v1`，与L1/L3同一机制、在冻结学习代码之外绑定）：同一批训练执行，八个反馈臂（对/错；参考答案；默认rubric／全局rubric／按题型分节的rubric／格式检查文字版——均由模型判定；格式检查与父Skill规则的合规检查——由宿主执行、零调用）各提一个候选，在同一选择集上配对比较；主流程不变，只换反馈这一环。设计与事先写定的读数规则见[备忘](handoff/rubric-form-study-design-20261014.md)；Codex三轮审查后GO，队列z15。结果见结果台账。**已演练（10/15）**：六块一研究在冻结恢复策略的“成本未知尝试”上限（每账本64次）下跑不完，改为一块一研究串联（`prepare --series <标签>`；队列z17；合并读数脚本[`rubric-form-series-reader-20261014.py`](handoff/rubric-form-series-reader-20261014.py)只合并协议除标签与块数外完全相同的研究、拒绝重复块；pending的研究保留不续跑），OfficeQA 8次尝试、6块可用（台账10/15 03:45条：形式无差别、粒度无一达标）；SearchQA串联运行中。零调用的候选文本分析脚本[`rubric-form-candidates-20261015.py`](handoff/rubric-form-candidates-20261015.py)、[`rubric-form-positions-20261015.py`](handoff/rubric-form-positions-20261015.py)。**后续：验证文本绑定研究**`skillopt/feedback_study/rubric_binding.py`＋`scripts/run_rubric_binding_study.py`（协议`fivebench-rubric-binding-study-v1`）：同一仪器，绑定臂复用基臂报告、只给失败小批analyst加登记的绑定前言；[设计](handoff/rubric-binding-study-design-20261015.md)；**已演练（10/15）**：OfficeQA一块一研究串联6块（队列z18，快照z4），两个主对比各3个信息块、都判定不了，差都在同输入重提案噪声之内（台账10/15 09:20条）；SearchQA部分未跑（判定rubric在SearchQA几乎不触发）。零调用工具：合规审计[`rubric-binding-compliance-20261015.py`](handoff/rubric-binding-compliance-20261015.py)、同输入噪声[`same-input-noise-20261015.py`](handoff/same-input-noise-20261015.py)。**10/15 负责人批准的下一步（实现中，尚无结果）：泛化反馈研究**`skillopt/feedback_study/generalization_feedback.py`＋`scripts/run_generalization_feedback_study.py`（协议`fivebench-generalization-feedback-study-v1`；[设计与修订](handoff/generalization-architecture-20261015.md)）：训练题按公报文件拆成L（学习32）与H（留出16）；生成器v2按类别在L的页面上出诊断题D（`scripts/generate_officeqa_diagnostic_tasks.py`），在H的页面上只给页面出迁移题T（`scripts/generate_officeqa_transfer_tasks.py`）；父Skill对D、T各跑3次校准（`scripts/weak_solver_probe.py`），D只留至少错一次的题；每块共享一次训练执行（L真题＋D），文本层（全局rubric判定）×代码层（宿主按已知推导做误差模式诊断）的2×2加`scalar_repeat`噪声参照，候选在T上各评两次。主流程不变；信息上的改变：代码层把生成题（我们从训练页面自己算的）答案与推导给analyst。另有只评测的求解器强度探针（同一提示、同一评分器，换更弱的型号）。

**10/16 晚：五 bench 主实验"Skill 与考官协同进化"（10/16 的设计记录；10/17 的定稿与实现状态见下一段）**。负责人 15:03 定框架（SearchQA → OfficeQA → LiveMath → SpreadsheetBench → ALFWorld 依次进化，每步测五个测试集；GLM-5.3 主表、deepseek-v4-flash 复现；从空白 Skill 出发），18:10 认可方向、同意 DeepResearch 联网、顺序交给操作助手定。计划改动的环节：Skill 分为共享部分与各 bench 分区；评分细则改为文字项＋代码项并用一致率衡量；DeepResearch 由 GLM-5.3 写搜索词、程序执行搜索与存档并核对逐字引用（现有冻结代码只能读 16 个 Python 官方文档页，没有搜索引擎）；出题器 v4 为每条规则出迁移题与边界题；逐条检验 X v2（格式翻转与内容分开计、"无关文字"对照、跨 bench 回归）。只读核对发现的缺口：阶段工具不支持 SpreadsheetBench、ALFWorld 的学习，二者没有默认细则与 bzero；OfficeQA、LiveMath 没有测试格；deepseek 只能跑 SearchQA、OfficeQA 且不能跑测试题。全文与理由见[五 bench 方法与通路](handoff/five-bench-method-proposal-20261016.md)；下一步是正式登记与 Codex 设计审查。

**10/17：五 bench 协同进化的正式登记定稿（协议 `fivebench-coevolution-v1`；三批代码与各批审查的修改已完成，没有任何付费运行）**。[正式登记](handoff/coevo5-registration-20261016.md)经五轮 Codex 设计审查，第 5 版 16:31 ACCEPTABLE。已写的代码只在新包 `skillopt/coevo5/`（冻结代码一行未改）：`protocol.py`（常数：容差、重做次数、各步花费上限、工作簿大小上限）；`outcomes.py`（回答分类的有序判定表，11 行、取第一条适用的；配置错误、预算拒绝、清理未确认三行先查全部记录，最后一次回执先于后端原因；SpreadsheetBench 逐个用例分生成、结构检查、判分三段，给出重新执行／重判／ALFWorld 重开的补救）；`ledger.py`（一次尝试的上界＝请求字节＋512＋max_tokens、预留＝4 倍上界；逐次尝试结算：报告用量照记、未连上与 4xx 记 0、其余记上界、没有回执记预留；基线学习步最坏 92,699,392 → 预留 9,300 万）；`gate.py`、`stats.py`、`skill.py`、`checks.py`、`scoring.py`（门的两轮判定、保守上下界、合入子集与长度上限）。离线测试 137 项通过。**第一批（基础设施层）已写完；Codex 代码审查第 1 轮 NOT ACCEPTABLE（14 条，[原文](handoff/coevo5-code-review-b1-r1-20261017.md)）、第 2 轮 NOT ACCEPTABLE（6 条，[原文](handoff/coevo5-code-review-b1-r2-20261017.md)）、第 3 轮 NOT ACCEPTABLE（3 条，[原文](handoff/coevo5-code-review-b1-r3-20261017.md)）、第 4 轮 NOT ACCEPTABLE（2 条，[原文](handoff/coevo5-code-review-b1-r4-20261017.md)）、第 5 轮 NOT ACCEPTABLE（3 条，[原文](handoff/coevo5-code-review-b1-r5-20261017.md)），都已改完；按负责人指示不送第 6 轮，第一批收尾**：`data.py`（五个训练池＝各 benchmark 的历史 train＋val，所有输入文件按 SHA-256 固定；训练抽样与回归面板按种子哈希排序、各链共用；除评测步骤外，任何读取器碰到测试题号就拒绝；OfficeQA／LiveMath 的上游原始文件同时含测试题，只有评测步骤带着测试读取凭证才能读：先用产生训练题的同一渲染器重渲全部训练题、逐题与冻结面板比对一致，再渲染测试题；只读布局文件固定的上游文件（读一次、核哈希），重复题号拒绝；OfficeQA 测试题的出处找不到任何页面就排除并报告，超过测试题数的 1/10 即暂停）；`budget.py`（跨进程 token 账本：先预留后结算，总量／链／步三层上限；超限时若还有在途预留就等，没有就停；进程已死（含僵尸进程）的预留按全额记；每次改动先追加到事件日志并落盘，状态文件只是日志的缓存，崩溃后从日志重放；回执报告的用量超过预留的假设时，按报告用量结算并记下超出量，结算与全局停发是同一条日志事件，直到记录了负责人的决定才恢复；每个单元尝试开始时记下账本的停发代数，之后的每次预留都核对它：其间停发过（即使已恢复）就拒绝，所以排队、冷却等待中的调用也不会越过一次停发，重做要换新的调用端；预留或结算的任何失败（写盘失败、被拒的操作、读不出账本）都在同一把锁里写一条事件：全局停发，并放回没发出调用的预留、补记没写进去的结算，然后抛出"账本失败"；连这条也写不进时由负责人核对）；`calls.py`（并发槽；调用包装：没送达的请求冷却 300 秒后原样重发，至多 2 次；超界回执先锁住调用端、再记录、再结算，随后这个调用端不再发任何请求；账本的任何失败也锁住调用端并让这一格暂停，不管冻结的做题程序把异常当成什么；一个调用端只服务一次单元尝试；写进全局账本的只有固定类别与数字——判定表认得的错误类型、三项用量、每次尝试的状态码或异常类名——原始回执只留在格记录里）；`cells.py`（一格＝一个 Skill 解一道题一次，经冻结后端与判定表；每格先独占认领再运行；判分前预检：停止项，以及不评分也能确定的结果（某个用例的工作簿结构无效或程序异常；所有用例都还没有可判的工作簿）不调用判分器，其余照判定表先评分再分类；补救只重放已交付的回答、不换答案；回答与判分结果按内容哈希只存一次，记录里只留哈希与状态；每格记录只写一次；遇停止项先写记录再暂停；任何错误都让并行调度不再派新格）；`qualify.py`（SpreadsheetBench 参考答案资格检查：每道题用参考工作簿当答案判两次，零模型调用）；`evaluation.py`（每条记录都写明所属的运行（开跑清单哈希），不能跨运行复用或解封；一个评测单元由一个进程独占；尝试目录按数字编号（只认 ASCII 数字的目录），暂停或中断之后的重做必须有负责人记录的决定；只记完成格数与未知数、不记分（未知原因只报判定表自己的固定类别；评测期间本进程的标准输出与标准错误——包括第三方库引用工作簿内容的警告和子进程输出——都转进封存的诊断文件；恢复输出前先把所有缓冲冲进该文件，冲不进就从此丢弃输出、不再恢复并暂停；评测出口只放出不带原错误的新异常，完整回溯只进封存文件；第二批须让每个评测单元在子进程里跑、其输出从一开始就是封存文件）；读测试集要有负责人的书面同意；首次评测登记测试面板哈希；SpreadsheetBench 测试侧资格检查全局只做一次、串行，每次尝试用新目录，完成后写一次指针，某次尝试暂停后，等着的评测也停下、不自动重做；Skill 字节不变则复用前一单元——同 bench、同求解配置，且是本链上一阶段，或登记的共享第 0 阶段评测（E-glm 与两条基线共用）；基础设施未知超过 1/10 即暂停；整条链完成或终止后才解封分数，且只读本链自己的单元）。离线测试共 267 项通过（1 项只在 Linux 上跑）。开发机零调用检查（快照 `/data/coevo5-20261017-source-a`）：五个训练池按登记大小加载；OfficeQA 74/74、LiveMath 283/283 道训练题渲染与冻结面板逐题一致（这次核对用的是审查前的旧代码，把含测试题的上游文件整份读进了内存，只打印计数，未打印、保存或使用测试内容；将在登记第 6 版说明）；SearchQA／OfficeQA／LiveMath／ALFWorld 后端就绪；SpreadsheetBench 未就绪——冻结的 v7 评分器把认证时代码目录的绝对路径绑进引擎身份，须按 F 的先例为每个代码快照重做 23 项控制认证（零调用；快照 a 的第一次认证因冷启动的首个容器出错被拒，第二次 `/data/coevo5-20261017-sheet-q23-b` 通过），这一技术偏离写进下一版登记。负责人 10/17 新要求（相似 bench 迁移、DeepResearch 收窄为出题与写规则）已写成[登记第 6 版](handoff/coevo5-registration-v6-20261017.md)（19:50，第 5 版原样保留；Codex 设计审查一轮）：负责人确认的相似关系表（SearchQA–OfficeQA、OfficeQA–LiveMath、OfficeQA–SpreadsheetBench，ALFWorld 不与谁相似）；取消共享部分，规则放本 bench 位置或相似位置（同一原文同时接在相似目标的分区）；分析模型可为规则附待查证问题，新增查证改写一步；相似位置要求在每个相似目标的检验面板上不比父 Skill 差（后向目标用回归面板，前向目标用查证素材出的 8–12 道同类题），复核没过的退回本 bench 位置；查证不再服务细则修订；新增迁移读数 Q1–Q3（自身提高、相似提高、其余不降超过 2 个百分点，单侧 95% 下界），与 P1–P4 分开；预算重算（E 链 4.8 亿、I 链 7.45 亿，总上限 14.4 亿不变）。第 6 版的设计审查只审一轮（10/17 20:03，NOT ACCEPTABLE，11 条，[原文](handoff/coevo5-design-review-v6-20261017.md)），已在本版内改完、不复审（登记 §21）：同一步的相似位置固定为本步全部可检验相似目标，否则只按本 bench 位置测；OfficeQA 适用条件改为"文档文字或数表（例如财政部公报页面）"；查证改写只一次、失败保留原文、改写后重新去重；长度按位置分两次检查；每次查证 ≤8 次调用、前向题每个（规则，目标）≤5 轮；前向题按规范化"材料＋问题"去重、题号按规则与目标区分；查证前做机械泄漏检查；迁移读数称"登记的合并迁移判据"（类别平均，不代表每个 bench）。代码已同步（`protocol.py` 的适用条件与调用上限、`skill.Rule` 的"全部或没有"），离线测试 278 项通过。**第二批（方法与编排）已写完、离线测试通过，Codex 代码审查一轮（不复审）**：`roles.py`（方法角色的调用：GLM-5.3、推理强度低、温度 0、每次最多 16384 tokens、读超时 900 秒；回答必须是一个 JSON 对象；不合法按登记回退，预算停止、账本故障、配置错误一律暂停）；`examiner.py`（细则校验；判定先跑程序检查、模型只判文字项且不看参考答案；修订按选择面板的平衡准确率 +0.05 且多对 2 个才收下；诊断依次用回答分类表的类别、固定格式检查、细则检查，最后模型看参考答案选文字项）；`analyst.py`（只看提案半；最多 5 条规则、相似位置最多 2 条且须本步有可检验相似目标；两次不合法 → 本步无规则）；`research.py`（维基百科固定接口与预先存档的资料；每次请求 ≤8 次调用、≤3 页、引文须逐字；查证改写一次）；`leakage.py`（§9 的机械检查与裁定，查证发出前也先查）；`forward.py`（OfficeQA 式算数题与 LiveMath 式五选一题，程序精确计算答案、一致性检查、按规范化材料＋问题去重，8–12 道成面板）；`units.py`、`step.py`（一步的六个学习单元：训练执行、准备、初筛、复核、组合、合入；单元记录只写一次、绑定运行与输入，暂停后要负责人的决定才重做）；`chain.py`（链：第 0 阶段评测、五步学习与评测，每个评测单元在子进程里运行、输出从第一字节起进封存文件；共享第 0 阶段只跑一次）；`texts.py`（五张公开任务卡——SpreadsheetBench、ALFWorld 两张新卡逐句对照冻结代码——与指令、初始细则的生成提示）；`manifest.py`（读开跑清单、核对固定文件的哈希）；`scripts/run_coevo5.py`（运行、评测单元子进程、监控（不报分）、负责人的重做／终止／恢复账本决定）。离线测试含两步端到端编排（相似位置、退回本 bench 位置、组合轮、暂停与重做、方法失败）。实现中定下的技术选择写在登记 §22。第二批代码审查（10/17，唯一一轮，[原文](handoff/coevo5-code-review-b2-20261017.md)）17 条（2 条 BLOCKER、13 条 MAJOR、2 条 MINOR），已逐条改完、不复审（登记 §23）：一条链只有一个运行进程，终止只在链空闲时进行；单元记录在封存输出写盘成功之后才写；第 0 阶段之前先做 SpreadsheetBench 测试侧资格检查；评测子进程在尝试开始前失败也要负责人的决定；运行中代码与启动清单不一致 → 已开始的链终止；完成／终止标记核对运行身份；按偏离提高的上限在重启后有效；泄漏检查也比对给做题模型的材料（SearchQA 检索片段、OfficeQA 文档页），数字按绝对值精确比较、识别各种写法；C3 把没有可用输出的回答算格式违规；前向题第一次出现即记身份，独立检查公式的数也须出自单元格；细则修订用判分器自己的结果，诊断与分析用完成度口径；分析输入的截断标记算在长度上限内；启动清单覆盖 `skillopt/` 与 `scripts/` 的全部 Python 文件并绑定研究资料库索引的哈希。第三批代码（10/17，技术选择写在登记 §24）：`readout.py`（§12 的读数：同题配对重抽、OfficeQA 按源文件成组重抽、三种缺失处理且共用记录只取一个值、P1–P4 固定顺序、Q 组迁移读数）；`baseline.py`（§11 的两个基线：冻结的 SkillOpt 与 GEPA 用学习 v9 学本 bench 的历史训练部分、挑选用历史 val，第 k 步种子 ＝ 基础种子 ＋ k；每步整笔预留、学完按冻结账本逐条结算，读不出或超出上界 → 停发、暂停；学习器按自己的规则停下 → 沿用上一步的 Skill，其他没完成 → 暂停等负责人；一步学习占着本 bench 的全部本地槽和 8 个 GLM-5.3 槽；命令 `check-baselines` 零调用检查十个学习步）；`report.py`（命令 `report`：只读已结束的链的封存记录、零调用，五个 bench 都有记录才出读数；主表、P1–P4、Q 组与逐格迁移、次要读数、考官与研究记录；写明当前代码是否与启动清单一致）；`prelaunch.py`（开跑前准备，命令 `qualify-train-sheet`、`build-archive`、`prepare-texts`、`make-manifest`、`consent`：SpreadsheetBench 训练侧资格检查；研究资料库——Python 3.11 文档六页、openpyxl 3.1.3 文档十页、五张任务卡，只经显式网关下载、逐份记 sha256；两份新指令与六份初始细则，已有的三份指令须是同一提示的完整生成；回归面板与容差；启动清单绑定数据、引擎认证、资格检查、文字、资料库、客户端、基线设置、全部代码文件与来源记录；负责人同意读测试集的原话）。按登记自己的取整规则更正两处上限：基线每步评测 2,000 万 → 5,000 万（基线 Skill 上限 32,000 字节），两个基线链合计 5.65 亿 → 7.15 亿；总上限 14.4 亿不变，开跑前文字与冒烟已用的 GLM tokens 记进清单、从运行的总上限里扣除。第三批代码审查（10/17，唯一一轮，[原文](handoff/coevo5-code-review-b3-20261017.md)）19 条（1 条 BLOCKER、14 条 MAJOR、4 条 MINOR），已逐条改完、不复审（登记 §25）：基线学习器每次发送前查账本，本次尝试开始后停发过就不再发送；冻结账本列不出、读不出或调用意图少于实际发出次数 → 按整笔预留结算并停发；清理证据读不出 → 清理暂停；开跑前的全部 GLM-5.3 调用（文字与冒烟）记在开跑前目录的一本持久账本上（开跑前总上限 3,000 万，文字 500 万），生成清单时须结清、未停发；文字第一份写不出就停；清单生成器重核文字出处（每份文字是它记录的那次调用的回复、提示与当前代码一致）、资料库恰好是登记的 16 页与 5 张卡且地址一致、基线协议是研究 F 的那一份且学习模型设置与做题模型一致、每个 bench 的基线学习面板建得出、I 链起点 Skill 装得下；清单绑定 Python 与 openpyxl 版本，加载时不一致就拒绝；`check-baselines` 通过后写标记，没有标记 `run` 拒绝；报告不能写进运行目录，新增测试面板与分母、未知类别、花费、偏离与尝试几节，E-glm 合入记录不全时方法更新相关读数为"无法评估"，P3/P4 补全列顺序更正；下载器不跟随跳转。新增冒烟命令（`smoke.py`；`smoke-make`、`smoke`、`smoke-summary`）：链 E-ds（deepseek 做题，GLM-5.3 方法角色记在开跑前账本），只用训练数据、不评测；一个 SearchQA 学习步（登记的种子顺序前 60 题）与一个 ALFWorld 训练执行（前 6 题）；没走到查证或前向题时，合入后单独补跑一次；摘要零调用；清单生成器只接受同一开跑前目录里已完成的冒烟。coevo5 离线测试 630 项（629 项通过，1 项只在 Linux 上跑）。下一步在 Linux 上依次做：开跑快照上的判分引擎认证、训练侧资格检查、资料库、开跑前文字、冒烟、清单、基线零调用检查、负责人同意书、开跑。10/18 的两处改动（登记 §25）：冒烟的链写进冒烟规格（`smoke-make --chain`，E-ds 或 E-glm；deepseek 路由额度用完后负责人选 E-glm），摘要另记做题的计费 tokens；考官细则修订的验证器对某种操作用不到的键（新增的 `id`，删除的 `text`、`check`）接受并丢弃、不检查——GLM 冒烟的修订回复因"新增"带了 `id` 被整份作废——必需的键与其他多余键的规则不变。coevo5 离线测试现为 634 项（本机 633 项通过，1 项只在 Linux 上跑）。

**10/19：五 bench 协同进化第 2 版（协议 `fivebench-coevolution-v2`；代码与登记定稿、设计与代码各审一轮，开跑前准备中，还没有付费运行）**。第 1 版四条 GLM 链跑完后只从训练侧分析（第 2 版设计时测试分数未开；10/19 10:52 经负责人同意打开，结果见账本 10/19 10:52 条）：两条链 50 条提案只收下 2 条。负责人"都改一下启动试试"，第 2 版只改"怎么找该学的、怎么判学到了没有"，目标与判分不变（[改动登记](handoff/coevo5-registration-v2-delta-20261019.md)；第 1 版的代码快照、运行与清单原样保留）。各环节现在是：**起点**——E-glm 从固定空架子出发（五个分区的标题与适用句，593 字节，`Skill(scaffold=True)`），I-glm 从五份指令出发，新增参照 NoSkill-glm（空字符串）只做第 0 步评测；不重跑基线、不共用第 0 步。**诊断**——每个 bench 一张冻结的错误类型表（`protocol.TAXONOMY`，由对第 1 版训练失败的零调用审核写成），顺序为回答分类表 → 固定格式检查 → LiveMath 按字母查表（"还能证明更强结论"这一选项的漏选/误选）→ 模型在错误类型、细则文字项与"其他"里选一个，错误类型优先；细则的代码检查不再抢在模型前面；OfficeQA 诊断视图放宽到 30,000 字符。**提案**——每条规则引用 2–8 个展示过的提案半失败题号，且每个针对的代码都有证据，不合格的规则留记录、不测、不重问；写明父 Skill 已覆盖什么与新增什么；另看最多 4 个做对的回答；有可检验相似目标的步必须指定迁移候选或写明理由。**门**——触发题上规则、父 Skill 与对照每题每轮做 4 次（SearchQA、OfficeQA、LiveMath）或 2 次（SpreadsheetBench、ALFWorld），回归题上父 Skill 做 2 次、规则 1 次，格式违规按逐题平均，回归容差按同一规则重算（5、6、8；SpreadsheetBench 60 题时 6）。**考官**——修订逐条校验，不合格或针对已删项的修改单独丢弃并记录，整份细则不合法就不修订；文字上限 450 字符。**泄漏**——所有机械检查先跑完；只有单词型参考答案这一项命中时，不发查证、改由裁定模型带最多 3 道撞上的训练题否决与否；每条送裁定的规则都检查"按答案分布作答"。**查证**——存档带入第 1 版 16 页（逐字节）并加 LibreOffice 25.2 帮助 50 页，检索按命中不同词数排序。**读法**——报告代码已改：主要读数是 E-glm 的学习增益（固定架子之上的增量变化，L > 0）与 Q1–Q3；次要读数是 I-glm 超过指令、从只有架子到指令的水平、架子对比（只描述）、I 链 Q1–Q3（只描述）与 deepseek；第 1 版的 P1–P4 与两条主张取消；另报每步门的漏斗与检验半各代码的失败题数。**开跑前**——新快照上重做判分引擎认证与训练侧资格检查；`build-archive --previous`（强制）；`import-texts` 原样导入第 1 版的指令与细则（版本化导入、原处按第 1 版规则复核）；冒烟为 E-glm 的 SearchQA（前 60 题）与 OfficeQA（前 50 题）两步，补跑的查证与前向题同样受泄漏检查约束。coevo5 离线测试 668 项通过（2 项按环境跳过）。**10/19 11:45 暂停开跑**：冒烟查出 E 链空架子与做题提示的排版缺陷——通用格式句落在 ALFWorld 分区下，OfficeQA 训练回答 79/100 没写答案标签（[管线排查](handoff/coevo5-pipeline-audit-20261019.md) §4.1）；负责人要求先排查、不急开跑。第 2 版快照与冒烟记录原样保留，修正将作为新版本。

**10/19：五 bench 协同进化第 3 版（协议 `fivebench-coevolution-v3`；代码与离线测试完成，设计与代码审查各一轮已处理，还没有付费运行）**。负责人 11:50 选定修 bug＋让模型看得见失败原因＋提案半自测、I 链为主；12:0x 要求“用弱一点的模型评测，用 deepseek 模型”。[改动登记](handoff/coevo5-registration-v3-delta-20261019.md)（设计审查[原文](handoff/coevo5-design-review-v3-20261019.md)、代码审查[原文](handoff/coevo5-code-review-v3-20261019.md)，处理见登记 §12、§13）；第 1、2 版的快照、运行与记录原样保留。相对第 2 版，各环节现在是：**链**——做题模型 deepseek-v4-flash，方法角色仍是 GLM-5.3：I-ds（五份指令出发，主结果）、E-ds（空架子出发，次要）、NoSkill-ds（空 Skill，只做第 0 步评测）；GLM 链定义保留、本次不跑；没有基线。**做题提示**——运行时选项 `prompt_layout = "contract-first-v2"`（SearchQA、OfficeQA、LiveMath、SpreadsheetBench）：通用句＋格式句＋`Frozen skill guidance (use only where applicable):`＋Skill；SpreadsheetBench 的格式句（10/19 格式检查没过后负责人选定，所有组含空 Skill 一起加）还写明要交一个读 input.xlsx、存 output.xlsx 的 Python 程序，代码块开头单独占一行，只给公式不算答案；另外三个 bench 的提示与 v1 相同，空 Skill 在那里与旧的逐字相同；运行中给分析模型和自测修改看的说明卡按此改写引文（登记的卡不变）；不带选项或用 v1 的调用方行为不变；ALFWorld 与不认识的选项值记 `invalid_prompt_layout`。**诊断与分析看得见失败原因**——SpreadsheetBench 题目视图加做题模型看到的工作簿预览（4,000 字符），参考视图加答案区最多 12 格的应写值、写入内容与重算值（`sheetview.py`：按最后一次判分的回执哈希找重算工作簿，对不上就退回参考缓存并写明来源）；OfficeQA 分析页面放宽到 20,000 字符；分析、自测修改、考官修订的输入不超过 220,000 字节（`roles.fit`，超出从后面去掉例子并写明，可去到一个不剩；固定字段本身超出就不发送）。**提案**——分析提示写明全部字段上限；外层结构不对整份不合格，单条规则不合格只丢这一条；规则只能以做题时看得见的信息为条件，泄漏裁定加对应的否决标准，SpreadsheetBench 规则的裁定另看提案半错题的应写值（最多 60 个，只用于否决）；考官修订看到检查的参数表。**自测（新单元 `selftest`，在准备与初筛之间）**——支持足够的规则在自己的证据题上、父 Skill 在证据题并集上各做 1–2 次（`SELFTEST_RUNS`），Σ 规则（未知算错）> Σ 父（未知算对）且规则未知 ≤10% 才过；没过的一起交给分析模型改一次（≤2 次调用），改后的文字重查去重、泄漏与长度，再测一轮（第 2 轮没有父 Skill 臂，不做暂停检查，改后规则的未知只决定它自己）；进门的规则用自测单元记录里的最终文字，前向面板也挪到自测之后；之后的初筛、复核、组合、合入、冒烟与报告都读这份记录（`step.plan_path`）。**门**——一轮里所有排了某道池题的臂都没拿到回答（按回执判，`step.shared_unanswered`）就把它从这一轮的全部判据剔除，暂停规则仍按全部格算；剔除后触发题少于 4 道的规则（组合轮里任一成员）记无法判定；C2 不计规则自己的证据题，但证据题仍计入规则臂的未知比例。判据与门槛不变。**deepseek 接入与账本**——客户端显式后端 `pjlab_token`（`https://token.pjlab.org.cn/v1/chat/completions`，回答模型名白名单只有 `deepseek-v4-flash`，每次请求写明 `thinking: disabled`（不推理）——接口背后混着带推理与不带推理两种服务，只有“不推理”被每次遵守；回复仍带推理文字的记 `thinking_mismatch`，按没送达重发、再不对记基础设施未知；密钥文件路径写进冒烟与清单的客户端配置）；deepseek 的 token 先预留后结算，记在自己的范围里（合计 4.3 亿、I-ds/E-ds 各 2 亿、NoSkill-ds 0.3 亿，按步计数），不计入 GLM 总上限；账本上的 deepseek 用量是下限（客户端内部重试只留最后一次的用量）。**冒烟**——链 I-ds（可选 E-ds），第 0 步是格式检查：E 架子、I 指令、空 Skill × 四个 bench × 20 道训练题各一次，按 C3 的固定格式检查，E、I 每种 ≥90%（10/19 负责人在两次检查后定：空 Skill 照实报告、不卡）且不低于空 Skill 5 点以上才往下跑；`smoke-make` 要带 `--deepseek-env`、`--engine-qualification`、`--sheet-qualification`。**报告**——读法按族（`readout.FAMILIES`）：ds 族 I-ds 超过指令为主、Q1–Q3 按 I-ds，E-ds 学习增益等为次要；ALFWorld 提案全部支持不足时写“可检验的触发题不足，无法检验”；新增自测漏斗与 deepseek 花费两列。coevo5 与客户端离线测试 723 项通过（1 项只在 Linux 上跑）。

**10/16：两条架构——条款池（X）与特征感知生成器（A）（负责人10/16上午决定；设计与事先登记见[两条架构设计](handoff/two-architectures-design-20261016.md)；`continual_learning`、`feedback_study`、生成器v1/v2与运行器v1一行未改；已实现、过Codex审查/审查中，尚未付费运行）**。(1) **共用的零调用特征层**`skillopt/skill_features/`：`tagger.py`给题目打结构标签（运算族`op:*`、答案形式`ans:*`、舍入`round:*`、题形`q:*`、上下文形状`ctx:*`），也给Skill文本打"指导标签"，`matches()`决定一条edit的trigger子集；`profile.py`把一批题的标签聚合成档案并算TV距离。`scripts/build_training_profile.py`只收训练侧或声明为生成集的题（任何验证/测试/留出/校准标签一律拒绝，标签按空白与分隔符归一后比较），每题记public摘要。(2) **架构X：条款池**`skillopt/clause_pool/`＋`scripts/clause_pool.py`：`decompose`把候选拆成相对父Skill的逐条edit（按块对齐、改写配对、只改空白的edit标`no_effect`不送测，`apply(p, decompose(p,c))==c`精确往返）；`noise`用父Skill的两次独立探针登记噪声v＝逐题差的二阶矩（精确有理数）；`screen`/`confirm`在**训练真题G（48道）里该edit的trigger子集**上用新探针测量，按第6节登记规则判（全部精确有理数，Δ≥max(下限,√(v·n))判为Δ≥下限且Δ²≥v·n；覆盖率按计数判，不足90%为pending）；每个探针都核对Skill文本哈希、逐题题面与评分输入（评分器读取的私有字段，OfficeQA为参考答案）、求解配置、登记的运行次数（噪声每半2次、初筛/复核各2次、父基线每题≥4次）以及时间与身份（初筛/复核探针晚于登记、不重用）；`compose`按复核轮强度合成`bzero＋通过的edits`（或整份候选A_whole）。所有输出封存、只写一次（临时文件链接到位）。Codex五轮审查（第4轮ACCEPTABLE，第5轮审评分输入字段的收窄）。(3) **架构A：生成器v3**`scripts/generate_officeqa_feature_tasks.py`（`generated-officeqa-tasks-v3-feature-aware`）：在v1文法上加sqrt/ln/exp/pow与序列统计（mean/median/sum/stdev/geomean/corr，最多24个数字，Decimal 60位，近平局拒绝），多部分答案≤3；学习侧按源题自身题型出题，留出侧只看页面、题型从L32档案抽样；`fidelity`对生成时封存的训练档案算TV（主运算≤0.25、答案形式≤0.20、舍入≤0.25）。**运行器v2**`scripts/run_generalization_feedback_study_v2.py`：两侧v3生成→池（学习侧只收单部分题，派生转成冻结研究读的v1形状；统计类表达式在代码层走既有的`derivation_unavailable`分支，提示里仍给期望答案、表达式与引文，泄露检查照常）→登记的go/no-go（两侧保真度通过；父Skill至少错一次的D题≥20；D、T通过率减G通过率≤0.10，G取同一求解设置的GLM-5.3 low探针）→冻结研究`run_study`。Codex审查中。(4) **已演练的**：10/16 11:43–14:30架构X对旧候选（oq_s1、oq_s2）在deepseek上跑完（噪声登记v＝1/88；初筛17个过3个→复核全过→合成pool_old＝bzero＋2条、A_whole＝oq_s2；账本10/16 14:30条）；14:37最终评测启动（设计§10：E val 24＋T 26，每格3次；SearchQA伤害描述），15:01 OfficeQA部分完成：pool_old、oq_s2相对bzero在E上都未建立，逐题差异几乎全是答案格式翻转；15:14 SearchQA伤害（描述）完成：与SearchQA自己的指令持平（账本10/16 15:01条）；12:15–12:37架构A第一轮在GLM-5.3上跑到go/no-go，**按登记规则no-go**（两侧保真度超限、两池比真题容易约15点；见账本10/16 12:37条），研究块未运行。**还没有发生的**：新候选；最终评测的结果。

## 10/3工程更新与实际运行边界

**E已按冻结的序列v3／learning v5终止；新实现为显式v6，未部署到E。** [18:13终态](results/skillopt-generalization-e-final-20261003.json)完整学习4/5、五域矩阵闭合5/5：S1产生非空Skill，S2/S3/S5超长候选被拒而无更新，S4 Pending携父。只有一次内容更新，后20格复用同一Skill观测，详见[E报告](skillopt-generalization-e-20261003.md)。不能把四个完成阶段写成四次成功更新。

v6的输入仍是冻结开发面板、父Skill、预算、运行环境和显式`POLICY_V6`，不读取五域最终分数反向修改Skill。执行链为：冻结service→按最多HTTP尝试预留未知成本→调用模型→过滤响应终止该题但不误判连接失败→执行产物→检查清理证据→仅对安全闭合的结果做原反馈／选择。清理未确认即保存回执并Pending，禁止后续题、评分和反思；Spreadsheet同题后续case也标记未执行。输出仍为候选或原父、阶段状态、成本和证据，不新增授权。

实现入口为[recovery.py](../skillopt/continual_learning/recovery.py)、[API](../skillopt/validator_pilot/api.py)、[执行Adapter](../skillopt/continual_learning/gepa.py)、[ledger](../skillopt/continual_learning/ledger.py)。v6终态回放只读已绑定的`model_service.json`，不创建API、不重抽结果。真实入口仍为[单阶段CLI](../scripts/run_continual_learning.py)；新版本需新manifest与输出目录，现有E启动脚本没有自动升级。[修复报告与离线smoke](learning-v6-engineering-repairs-20261003.md)记录已复现缺陷和验证范围。

**范围限制：v6不改变v5的净unknown偏移／共同已知选择策略。** 此规则可能因缺失位置变化掩盖退化，已存在人工反例；不能将工程可靠性修复称为安全泛化算法完成。后续修改选择策略、Skill长度或自动压缩必须另冻研究协议。下述C/D与v5记录保留历史边界。

**10/3终态：新D五阶段全部结束、完整学习0/5、最终Skill为空，25格全部复用旧No-Skill；旧C的SkillOpt与GEPA也各为0/5。** Pending原因逐例核实为：Coding反思HTTP200流未结束且v4不重试；Sheet生成程序自行`SystemExit`未交付工作簿（模型程序行为，不是评分器缺陷）；QA内容过滤；KOR原生合并候选6,172字节超6,000字节接口；ALF的v4网络重试成功后，失败尝试的未知usage被v4账本当作阻断。[D终态](results/skillopt-generalization-final-20261003.json) · [C终态](results/fivebench-sequence-c-final-20261003.json)

**learning v5历史设计（E冻结于此版本，实际进度见[E报告](skillopt-generalization-e-20261003.md)）。** 输入与v4相同。[recovery.py](../skillopt/continual_learning/recovery.py)新增`POLICY_V5`：客户端`closed_delivery_error_v2`在v1基础上把HTTP200未结束流纳入同一有限重试；[ledger.py](../skillopt/continual_learning/ledger.py)对失败尝试的未知usage如实计为`unknown_cost_attempts`，不阻断后续调用，配置停止阈值64（旧实现按调用边界检查，内部重试可越界），已交付回复缺usage或未闭合调用仍阻断；[skillopt.py](../skillopt/continual_learning/skillopt.py)把超出6,000字节的完整原生候选记为`reject_inadmissible_over_budget`，保留父Skill与被拒文本供审计，继续下一轮，不截断、不评测。unknown分数**从不记0**：v5把它从训练反馈和选择比较中成对排除，并预先冻结三道保护——训练集与父选择的已知比例须≥50%，否则阶段Pending；候选在父已知位置新增的unknown扣除其恢复的unknown后超过max(2, ⌈5%·n⌉)，或双方均已知位置不足50%，则该候选判为`reject_unknown_shift_or_coverage`、保留父Skill；门控只比较双方均已知的位置。设计要求内容过滤记unknown且不重试；review复现过滤后断流会误重试，v6另行修复，未回写E。每次更新重新执行训练集（评测键含rollout）。账本/预算拦截仍Pending并保留真实原因（如`max_api_calls`）；上游合并/排序的静默回退记为`native_fallbacks`；v5仅限SkillOpt。评测端仍用原No-Skill服务、源码、评分器与全分母，unknown照常计入分母。v1–v4行为与记录哈希不变，专测见[测试](../tests/test_continual_learning_delivery_v5.py)。序列v3（[配置](../configs/continual_learning/fivebench_sequence_v3.pjlab.json)、[启动脚本](../scripts/run_skillopt_generalization_e_linux.sh)）只运行SkillOpt，seed与D相同，因而训练/选择划分相同。

只读链路审查发现的其余问题已修复：[报告器](../scripts/report_fivebench_generalization.py)保留评测端实际使用的`reported_tokens`（此前首个非空Skill评测的token会被漏报）；v3的`policy_key`额外绑定目标域与冻结报告哈希，复用评测格前核对领域；v1/v2的键与记录不变。成对排除是v5新协议，不回溯改写C/D。

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
| [continual_eval](../skillopt/continual_eval/cli.py) | 外部冻结S0–S5→五域评测矩阵与跨方法配对 | 无新部署授权；No-Skill五域1,419题×2已完成。C/D为空策略复用；10/3 E的S1已有非空Skill五域结果，S2–S4携父复用，不算新增独立观测 |

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

外部训练已增加独立`skillopt/continual_learning/`及`scripts/run_continual_learning.py`。输入为仅development的互斥训练/选择任务族、共同空父、模型和预算；输出为调用账本、候选、选择轨迹和冻结阶段状态。GEPA使用固定官方Pareto/反思引擎；SkillOpt调用原生反思→合并→排序→补丁→来源选择门。共享`Ledger`绑定请求、产物、task/role、源码和环境；unknown/中断进入Pending，不自动重采样或把unknown当0。训练暴露明确授权的开发标量反馈，不暴露隐藏测试正文（10/4起仅v7 BCB SkillOpt消融可显式改用脱敏执行证据档案，见[试点报告](feedback-ablation-pilot-20261004.md)）；评测侧`score_feedback_allowed=False`不变。最终数据不进入学习，当前不含五域自动训练、路由或部署。首个自然先导预设64训练族＋64选择族、两次更新、相同预算上限；GEPA小批与SkillOpt全量反思不等实际算力。离线测试已通过，真实效果尚未产生。[适配说明](continual-baseline-adapters-20260928.md)

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
