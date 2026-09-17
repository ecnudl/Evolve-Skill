# V5：结构化证据验证与协同接口

本版本实现经讨论确定的“证据确认后门控、Coding 校准后接 QA、自动为主并导出人工盲审队列”。不覆盖 V4 或原版 SkillOpt trainer。

## 研究边界

默认 CLI 是两轮工程集成 smoke，单历史、单次任务重复，最多 512 次逻辑调用；不是验证泛化有效性的正式实验。Coding 使用已暴露的 V4 项目，QA 使用已参与历史研究的数据源中的固定训练题，均不可声称模型未见。学习、晋级、最终检查在本 run 中项目/题目分开，但工程最终检查不等于独立公开 benchmark。正式三基线、多历史/任务族实验需新的前瞻数据协议，原版 SkillOpt 不在此 smoke 中。

## 固定行为

- Rubric 四项义务：代码合同、可执行反例、QA 原生答案指标、QA 引用来源。义务、领域和硬证据权限固定，只进化检索/检查策略。描述性 when 不决定宿主的适用性。
- Coding 一次生成与一次公开测试修订。文件结束可由精确 END、下一个 FILE 头或 EOF 表示，规则在请求前固定；不补 Python 内容、JSON 或 Markdown fence。仍使用原 OS 沙箱。
- QA 保留 SearchQA EM/F1，solver 只见题目/上下文和引用格式反馈，不见答案。引用匹配不代表蕴含正确，不授权批准。Research 的 QA 输入仅为机制级投影，不包含问题、上下文、答案或自由文本反馈。
- 对同题 Base/Current/Candidate 使用相同 Rubric，宿主绑定真实 solver Skill、调用和产物哈希。只有可核实硬证据允许门控；缺失核心义务返回 unknown，附加探针缺失不提供额外保证。单项已知伤害不得被平均分提升抵消。
- Working/Approved/Repair Parent 分离；Approved 仅在已有任务/项目覆盖内使用，未知范围或已撤销范围 fallback。记录当前有限范围，不声称跨域安全证书。
- 每个历史/策略的晋级片只用一次，调用前检查至少两个正确及两个错误代码哈希、两类均覆盖两个项目。每产物重复两次。各对照在查看校准结果前已冻结提案，可使用同一预选面板作配对比较；不跨轮重复调参。QA 检查项改变但没有 QA 晋级证据时不激活。
- 工程校准面板按源码哈希完整性筛选：排除 reference 与 equivalent 内容完全相同的历史项目，再取两个项目；不按模型得分选题。任何模型调用前，以私有可执行 oracle 复核冻结控制的真值，复核结果不进入反馈。
- 校准 oracle 真值由完整测试确定，验证器仅访问公开任务/测试与自己提出的合法输入，绝不直接用私有真值给自身打分。自然通过有限测试的代码不能直接当已知正确。
- Research 最多三阶段，每阶段 6000 tokens：竞争解释计划、证据分析、Rubric 补丁；最多三页官方资料。测试已通过的开发样本在执行前选定抽查，语义失败和持续 unknown 也可触发。资料只验证来源，不自认证修改有效。格式失败不语义重抽，旧 Rubric 保留。
- 先封存当轮 Skill 决策，再提出/校准验证器，晋级次轮生效。校准原始标签不进入优化输入。全部分支冻结后才执行最终任务，最终反馈不回流。

## 反馈质量与人工核验

反馈分别保存观察事实、配对差异、未确认机制假设、修改建议及必须保持的行为。对遇到的首个合法且有确认错误的开发产物，另做仅分数/结构化证据的一次修复对照，各一次等预算调用；这是选定案例诊断，不能证明反馈普遍有效。如无此样本则不虚构缺陷。

人工队列按领域各抽取两条随机反馈与两条剩余争议反馈，分层分别统计，隐藏结构化策略标签并保留私有映射。人工提交须绑定准确队列哈希；未提供真实人工评审之前状态为 pending，不能把软件校验或测试替身标为人工结论。自由文本可能含提示线索，盲化有明确限制。

## 使用

```bash
conda run --no-capture-output -n skill python scripts/coevolution_v5.py prepare --output outputs/coevolution_v5/glm53_integration_20260911_v1
conda run --no-capture-output -n skill python scripts/coevolution_v5.py run --output outputs/coevolution_v5/glm53_integration_20260911_v1
conda run --no-capture-output -n skill python scripts/coevolution_v5.py report --output outputs/coevolution_v5/glm53_integration_20260911_v1
```

首次请求前冻结源码/数据/协议。单目录一个进程，已有请求不可重抽，未解决预约阻止完成。不修改 PJLAB 配置或代理；继续 glm-5.3、全局最多四并发。报告实际返回模型、调用/HTTP/token、unknown、alias、覆盖与成本。工程测试通过不是研究假设成立。
