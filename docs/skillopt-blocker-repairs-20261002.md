# SkillOpt 未完成问题：修复与 smoke（10/2 晚）

本轮修复学习的可完成性，不改变原生 SkillOpt 的反思、合并、排序、编辑算法及严格改进 gate。旧五阶段运行、No-Skill 分数、原始回答和 Pending 均保留。新行为使用 `continual-learning-v4` 和独立输出。[实际回执摘要](results/skillopt-blocker-repairs-20261002.json)

## 逐项修复

| 阻塞 | 新行为 | 实际验证与边界 |
| --- | --- | --- |
| Coding 反思 JSON 非法转义 | v4严格完整对象解析；仅将非法转义保留为字面反斜线，记录插入位置和回执绑定；拒绝重复键、截断、非有限数值和结构猜补 | 原22条反思：21严格合法、1窄修；第二轮为8严格＋1窄修，零新API。旧Pending不解除 |
| Spreadsheet 重算误读数字为日期 | 显式`qualified_lo_recalc_v7_v1`，复用资格化数值读取视图；不改输出、公式、数值或参考答案 | 独立23/23控制通过；原SkillOpt首个同产物由unknown变为明确fail，2容器、9.445秒、0API，回放一致 |
| ALFWorld 初始化 ValueError | 启动器从冻结runtime绑定`ALFWORLD_DATA`，拒绝冲突，退出恢复环境；不在并发episode中改全局环境 | Linux真实reset、合法一步、won信号、清理全通过；0API、0遗留进程 |
| HTTP200、finish_reason=network_error | 新服务身份显式启用有限重试，最多3次HTTP；每次usage保留并纳入账本 | MockTransport覆盖恢复、耗尽、旧策略不变；没有人为制造一次真实网络故障 |
| 完整闭合的length | 首次65536，只有确认同模型/HTTP200/完整流/length才能额外一次131072；原回执不变，新请求绑定父意图 | 工程测试覆盖一次恢复、重复仍截断、不完整流拒绝及成本；不能声称提高上限必然有效 |
| sensitive/content_filter | 单独标明服务过滤，不重试绕过，不当语义失败 | 仍Pending；它不是可以靠改评分器“修好”的错误 |

解析不再依赖是否偶然安装可选`json_repair`。两个API恢复规则只作用于评分前的交付失败，不因答案错、候选被拒而重采样。unknown仍不作为0分输入优化器；调用或逐次HTTP usage不完整仍如实记录并阻止伪造完整预算结果。

独立review另外发现并修复：协议将`True`/浮点数误收为整数；新重试遗漏前次已报告token成本；旧只读成本检查没有version字段时的兼容问题。未通过放宽正确性标准解决任何阻塞。

## 真实小闭环：3/3完成

入口：[smoke_skillopt_recovery.py](../scripts/smoke_skillopt_recovery.py)。从旧开发角色中按固定哈希选择2个训练族、2个选择族，每族1题；不读取旧成绩，不按通过情况挑题。每域一轮原生SkillOpt更新；GLM-5.3 low，初始65536、反思4096，新流式wall3600和有限恢复策略。

| 域 | 训练/选择 | 一轮流程 | Solver / 反思调用 | 报告tokens | 选择集：父→候选 | gate |
| --- | ---: | --- | ---: | ---: | --- | --- |
| BigCodeBench | 2 / 2 | completed | 6 / 3 | 8,228 | 2/2 → 1/2 | 拒绝，保留父 |
| SearchQA | 2 / 2 | completed | 6 / 2 | 12,813 | 2/2 → 2/2 | 拒绝持平候选 |
| KOR-Bench | 2 / 2 | completed | 6 / 1 | 15,061 | 2/2 → 2/2 | 拒绝持平候选 |

共12个独立任务条目、18份任务执行评分、24模型调用/HTTP、36,102报告tokens；0unknown、0缺usage、0开放调用，未发生真实HTTP或length重试。三个候选均未被接受。再次完整回放得到相同结果，零新增调用，所有JSON字节未变。

**这是4题/域的工程smoke，不用于估计准确率、稳定学习收益或跨域泛化。** 它证明真实模型能走完“原任务执行→反思/合并/编辑→候选选择→gate”，不是证明SkillOpt变好了。ALF只测初始化，Sheet只测同产物评分；不能合称五域完整学习。

Linux源码：`/root/continual-learning-recovery-20261002-b-source`；输出：`/root/continual-learning-recovery-20261002-b-smoke`。旧`continual-sequential-20261002-c-study`不改。

```bash
# Linux；proxy_on须与启动在同一shell；客户端仍使用冻结的显式代理。
proxy_on
python -m scripts.smoke_skillopt_recovery \
  --study /root/continual-sequential-20261002-c-study \
  --output /root/NEW_RECOVERY_SMOKE \
  --repo /root/continual-noskill-bcb-20260928-a
```

初始化和资格有独立入口：[ALF](../scripts/smoke_alfworld_launch.py)、[工作簿](../scripts/smoke_sheet_learning_numeric.py)。工作簿资格绑定源码路径，新整合目录必须重新资格，不能借用旧目录授权。真实工作簿输出在`/root/continual-sheet-learning-fix-20261002-smoke`，ALF在`/root/continual-alf-launch-smoke-20261002-output`。原JSON窄修位置1909，原回复SHA `6e144ae5cb52d0ddbc36254b0e441ef056bcb62905fc75656850d6f06cb60e26`，新解析正文SHA `af66192702f3da6ff5b4f74538c6412045351f6c0c7563c4fcfc28ac6d327eff`；未公布正文，也未改原缓存。

## 代码检查

- 最终本地相关回归：**1,410 passed / 15 skipped**，95.85秒；跳过为可选GEPA/环境相关条件，不能算通过。
- Linux恢复、解析、启动、域适配和原生SkillOpt相关测试：**181 passed / 6 skipped**。此处GEPA六项是显式开关未启用，本轮目标是SkillOpt。
- Ruff、diff空白检查通过；三个分工独立检查了环境启动、数值读取、解析器、重试身份与成本。
- 早期回归暴露并修复一项旧成本检查兼容错误；另一轮因源码在测试中途修改而触发身份拒绝，稳定源码后全套相关回归通过。不是略过失败重写成全绿。

## 下一次正式实验如何启用

[v4配置模板](../configs/continual_learning/recovery_v4.example.json)是未封存模板，不是可直接执行的manifest。填入实际任务族、模型代理与runtime后，通过`continual_learning.contracts.manifest()`生成新sealed manifest，再使用现有`run_continual_learning --execute`入口；旧manifest不可改版本后覆盖续写。

新工作簿runtime必须显式选择v7 profile并绑定新23项资格；旧v5默认不变。ALF两个启动器已绑定环境。v1五域序列配置仍默认生成历史v3协议，**不会自动继承v4或新评分器**；正式五阶段重跑前必须冻结新编排配置并做全域启动检查。模板将反思上限预留为64，实际smoke只1轮；增加预算不是已有结果改善。

仍有两类问题不能宣称消除：服务过滤/更大预算仍截断；任务自身不支持或真实生成程序未交付（例如GEPA工作簿AttributeError）。本轮不将它们强改成fail、跳过样本或宣布完整五域学习成功。下一步应先在新配置下恢复原规模域内学习，再做选中非空Skill的五域比较。
