# 新E：SkillOpt五域补跑（序列v3 / 学习v5，2026-10-03）

## 当前状态

**10/3 18:13终态快照：五阶段尝试全部结束，完整学习4/5、全域矩阵闭合5/5；只有S1更新，S2/S3/S5无更新，S4 Pending携父。** [机器可读终态](results/skillopt-generalization-e-final-20261003.json)从Linux只读观察器原样导出并验证seal，保留实际成本、分母与复用标记；[17:53旧快照](results/skillopt-generalization-e-progress-20261003.json)保留。这是原生SkillOpt的受预算适配baseline，不是Research/Rubric双门主线或独立final。E全程使用冻结v5；本地新[v6工程修复](learning-v6-engineering-repairs-20261003.md)没有覆盖该源码、修改该实验或追改成绩。

最终状态为`attempts_finished_with_pending`，运行器final记录哈希`7b5e8c1dac5fb0e0d10a71903b976158e40223266f89ffb3ec5ced96bfe8d84e`。S1–S5的Skill哈希相同，故后20个评测格复用S1，不是额外20场独立实验。全部学习1,928逻辑调用／1,928 HTTP、4,897,627已知tokens、2缺usage；五域新评测4,144逻辑调用、9,733,346已知tokens、6缺usage。未知费用不补零。

- 协议：`fivebench-sequential-attempts-v3` → `continual-learning-v5`，协议哈希`5073b95dfb9db675179289816542cb882f8bbc05fda21e2733e0c3f7890883b6`。只运行SkillOpt。
- 启动核验：新源码下Sheet学习评分器23/23资格通过（0模型调用）；prepare/check通过；09:23首批真实回执为HTTP200、`stop`、`glm-5.3`、流完整、usage齐全，客户端策略`closed_delivery_error_v2`。
- 代码与配置：[配置](../configs/continual_learning/fivebench_sequence_v3.pjlab.json) · [启动脚本](../scripts/run_skillopt_generalization_e_linux.sh) · [v5专测](../tests/test_continual_learning_delivery_v5.py)。部署前本地相关回归1,519项通过/15跳过，Linux冻结源码175项通过/6跳过；均为工程验证。

## 进行中快照：S1（Coding来源）五域评测（10/3 14:05，非终态）

Coding来源学习完成：step0候选37/65低于父40/65被拒；step1候选41/65严格高于父40/65被原生gate接受（选择集仅+1位置，噪声量级；0 unknown、无原生回退）。选中Skill 5,831字节。学习349调用、已知389,370 tokens、usage完整。

| 评测域 | No-Skill | S1 | S1对No-Skill：改善/退化/持平/未知 | 名义符号检验p | 学习族外子集 |
|---|---:|---:|---:|---:|---:|
| BigCodeBench | 400/800（U1） | 421/800（U1） | 60 / 39 / 700 / 1 | 0.044 | 274→288 /542 |
| Spreadsheet | 63/160（U53） | 67/160（U63） | 14 / 6 / 72 / 68 | 0.115 | 无留出 |
| SearchQA | 560/800（U6） | 571/800（U6） | 55 / 44 / 695 / 6 | 0.315 | 379→385 /544 |
| KOR | 746/1000（U11） | 721/1000（U12） | 73 / 97 / 810 / 20 | 0.077 | 488→463 /600 |
| ALFWorld | 65/78（U0） | 67/78（U0） | 4 / 2 / 72 / 0 | 0.688 | 无留出 |

解读边界：单一学习历史；全部为已曝光开发数据，非独立final；位置含2次重复且同族相关，符号检验把位置当独立、未做多重比较校正，p值偏乐观；No-Skill两次重复本身相差约8/400。可以记录的方向是：来源域Coding与其学习族外子集有正向信号，KOR出现可见退化（净−25，族外−25），QA/ALF小幅正向但不显著；Sheet确认正确+4但unknown从53增至63，覆盖下降，不能判为改善。新评测4,144逻辑调用、已知9,733,346 tokens（SearchQA 6条过滤无usage，token记为未知而非0；KOR 1,002 HTTP含2次重试）。

## 进行中快照：S2（Spreadsheet来源，10/3 15:07）

在v5成对排除下学习正常闭合（父选择已知位置正确率0.769），但两次原生候选分别为9,212与8,582字节，均超过6,000字节接口，判`reject_inadmissible_over_budget`；阶段`completed_no_update`，S2=S1，五格复用S1评测、0新调用。学习131调用、已知457,284 tokens、usage完整。结构性含义：S1已占5,831字节，原生补丁以追加为主，后续来源阶段的候选很可能持续超限，学习链在S1后实际冻结；这是冻结接口的约束，不是来源域无可学内容的证据。

S3（SearchQA，10/3 15:17）同样闭合但无更新：内容过滤的unknown被成对排除、不再阻断；两次候选8,420与8,009字节均超限被拒，S3=S1，0新评测调用。学习216调用、已知779,326 tokens，2条过滤回复缺usage计为非阻断的未知成本尝试。

S4（KOR，17:53快照）为`native_optimizer_incomplete` Pending；第一轮候选12,281字节超限，最终携S1父Skill，五格再次复用。学习332调用、已知1,425,440 tokens、usage完整。前三个完成阶段不等于三次有效更新：迄今只有S1产生了新Skill。S5当时仍在学习，不能填入零成本或零分。

S5（ALFWorld，18:13终态）正常闭合但无更新：父选择18/20，两轮候选8,884与8,989字节超限；900调用、1,846,207已知tokens、usage完整。最终Skill仍为5,831字节的S1，最终五域成绩与上表完全相同。超长候选造成后续来源学习没有更新，不等于这些领域没有可学习知识。

本次工程review对E的只读检查未发现清理未确认；S1–S4分别349/131/216/332次学习调用与HTTP数相同，S3两次过滤均单次终止。S1的65个选择位置全部已知，未触发unknown共同分母风险。这个检查不是独立重跑，更不证明v5所有边界安全；新发现的边界错误已另立v6修复。

S4（KOR，10/3 17:38）Pending携父：step0候选12,281字节超限被拒；step1的第14次原生合并回复整体不是合法JSON（严格解析`invalid_json_document`，不属于可窄修的非法转义），桥接层按设计不让上游回退冒充候选，阶段记`native_optimizer_incomplete`。32次反思调用均HTTP完整、`stop`；学习332调用、已知1,425,440 tokens、usage完整。S4=S1，0新评测调用。

## 与D相同的部分

模型BigModel GLM-5.3 low，学习solver 65536 / reflection 4096；每阶段最多2次原生更新，metric 512、反思64、API 12,000、报告token停止阈值600万。seed与D相同，因此训练/选择划分相同：

| 来源域 | 训练题 / 族 | 选择题 / 族 |
|---|---:|---:|
| BigCodeBench | 64 / 64 | 65 / 64 |
| SpreadsheetBench | 40 / 40 | 40 / 40 |
| SearchQA | 64 / 64 | 64 / 64 |
| KOR-Bench | 100 / 10 | 100 / 10 |
| ALFWorld | 19 / 19 | 20 / 20 |

每阶段选中的Skill在全部五域、全部2,838个位置上评测，评测仍用原No-Skill的服务、源码、评分器与全分母；同策略引用既有观测、不算新独立样本。学习与评测任务重叠，Sheet与ALF没有学习外留出题，全部是已曝光开发数据，不是独立final。

## 与D不同的部分（v5，预先冻结）

- 交付：HTTP200但未结束的流纳入同一有限重试；失败尝试的未知usage如实报告、不阻断，配置停止阈值64次；旧v5仅调用前检查，内部重试可能越界，不能将它描述为已实现的硬上限。已交付回复缺usage仍阻断。
- 接口：超过6,000字节的完整原生候选判为不可接受，保留父Skill并继续下一轮，不截断、不评测。
- unknown：从不记0。训练反馈与选择比较中成对排除；训练与父选择已知比例须≥50%，否则Pending；候选在父已知位置净新增unknown超过max(2, ⌈5%·n⌉)或双方均已知不足50%则拒绝该候选；门控只比较双方均已知位置。设计要求内容过滤不重试，但review已复现过滤后断流会误重试，E所查回执未触发；净unknown保护也不保证不掩盖退化，限制见v6修复报告。
- 每次更新重新执行训练集；账本/预算拦截保留真实原因；上游合并/排序回退记为`native_fallbacks`。

这些是新协议，不回溯改写C/D，也不能把E与D的差异解释为SkillOpt方法本身的收益。

## 运行与接手

Linux源码`/root/continual-skillopt-generalization-20261003-e-source`；研究输出`/root/continual-skillopt-generalization-20261003-e-study`；tmux`skillopt-generalization-20261003-e`，启动日志`/root/continual-skillopt-generalization-20261003-e-launch.log`。只读报告观察器tmux`skillopt-generalization-report-e`，输出`/root/continual-skillopt-generalization-20261003-e-reports/`（`latest.json`指向最新快照，最长24小时）。不要重复执行启动脚本或写入该研究目录；断开后先核对tmux、闭合回执与终态。

连接开发机遵循[AGENTS.md](../AGENTS.md)：先测试原SSH别名与ControlMaster，不关闭或重启Clash；VPN、物理网关及代理路由要按当前环境核实，不能把某次连通经验视为通用前提。
