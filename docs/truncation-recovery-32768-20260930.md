# 截断恢复结果与更高生成预算实验

**终态补记**：D已于9月30日17:20:54完成105位置：KOR41 pass/40 fail/16 length/7 timeout，Sheet1 pass；0开放调用。105逻辑调用/145 HTTP，已知报告tokens 1,840,287，7个超时及重试完整计费仍未知。[终态JSON](results/truncation-recovery-32768-final-20260930.json)另存，下面启动快照和冻结协议不追改。后续新授权环境修复见[新报告](evaluation-environment-recovery-20260930.md)。

2026年9月30日核验。昨晚8192预算的恢复C已于9月29日20:02:44完成148个位置，早于20:16的暂停请求；本机断网未中断这批后台任务，没有新增开放调用。仍有105个HTTP200/length截断，正文全部为空。下一轮仅对这105个位置使用32768预算，不重跑已交付结果或基础设施unknown。

本文记录的是交付恢复诊断，不是完整benchmark重评、Skill进化或泛化收益。历史协议和成绩保持不变。[脱敏聚合数据](results/truncation-recovery-8192-20260930.json)记录分母、成本及来源边界，原始提示词、答案和API缓存继续保存在私有运行目录。

## 已完成的8192预算实验

BigModel GLM-5.3，low推理、temperature=0、非流式，最多10并发；模型提示词和原生评分不变。相对最初4096实验，C同时延长read等待120→300秒，因此不能解释为单变量token消融。

| 冻结恢复C中的来源 | 位置数 | 可交付响应 | 原生通过 | 原生失败 | unknown或不支持整局评分 |
| --- | ---: | ---: | ---: | ---: | ---: |
| KOR No-Skill | 144 | 40 | 24 | 16 | 104截断 |
| Spreadsheet No-Skill | 1 | 0 | 0 | 0 | 1截断 |
| BigCodeBench 原第二轮SkillOpt候选 | 1 | 1 | 1 | 0 | 0 |
| ALFWorld 原动作调用 | 2 | 2 | — | — | 2，不恢复episode |
| 合计 | 148 | 43 | 25 | 16 | 107 |

原164个位置仍完整计数：A完成5（KOR 2通过、3失败）＋A操作中断10＋B通信timeout 1＋C完成148。合计原生27通过、19失败、118个unknown或不支持整局评分；这里混合了No-Skill、一个候选和动作级诊断，不能当作一个总体准确率。

C的148次逻辑调用对应154次HTTP，142个调用一次HTTP、6个调用两次HTTP；终态报告1,124,047 tokens，0未闭调用，重试全过程实际计费仍不完整。加A已知5,741 tokens后，任务恢复已知报告量为1,129,788；A十个中断及B timeout用量未知，另有24 tokens短健康检查单列，不得称为完整总成本。

105次截断共860,160个completion tokens，其中859,464为reasoning；105份答案正文全部为空。下一轮来源为KOR104（puzzle88、cipher16）及Spreadsheet1，按benchmark与任务/家族ID联合去重为68题、15家族。只在失败子集上重复调用，不能将105视为105个独立题目，也不能把恢复通过归因于预算变化而排除随机性。

BCB候选这一题恢复通过，不代表原优化器恢复：原选择面板仍有4个未提交位置，旧阶段保持Pending；不把新回执写回旧学习记录。ALF仅恢复两条动作输出，旧环境未重建，不能据动作文本算成功。

## 下一轮冻结边界

使用独立Linux目录`/root/continual-truncation-recovery-20260930-d`。测试及独立review通过后封存代码与协议，9月30日15:11:36后台启动；首模型响应已确认HTTP200/stop，已释放最多10并发。

- 只接受已完整结束的C为父运行，核验协议、源码、任务、产物与请求回执；选择条件为确证HTTP200/length，不依据答案对错选题。
- 全部105个合格位置纳入，一位置一次新逻辑调用，不因模型再次截断而无限续写、补抽或自动升档。
- 保持GLM-5.3 low、temperature、原system/user、原Skill、任务及原评分器；预算8192→32768，同时read300→600，保持非流式及原最多3次HTTP尝试。600是读取等待，不是整个请求总墙钟限制。
- 原客户端默认和PJLAB上限不变，只开放BigModel GLM-5.3至32768；每个请求的budget与service、缓存和回执绑定，不能只改运行命令而沿用旧身份。
- 同一Linux shell启用`proxy_on`，客户端显式绑定原PJLAB网关。首个真实请求确认模型HTTP响应后才释放最多10并发。
- 使用原有有界调度与协作PAUSE，等待在途写盘；不使用SIGSTOP，不修改Clash。
- 不恢复SkillOpt/GEPA，不补原来未提交的学习题，不改变五域基线，不授予Skill准入。

这些限制让新结果可追溯，但不构成因果实验：预算和通信等待都变化，且缺少相同8192预算的再采样对照。后续正式方法比较仍须共同固定预算/重试规则及独立数据。

## 实施状态

新增`prepare-budget`已完成，使用v3协议；默认`prepare`和v1/v2仍为8192，既有历史目录源码不变。运行中持有祖先只读锁并校验来源文件及证据清单；只有父运行完整结束、API缓存与位置回执一致才允许冻结升档。报告将本轮、所选父调用、完整父面板及A/B遗留成本分开列出，不能将嵌套数据重复求和。

本机相关回归312 passed、0 failed/skipped；其中API 126和恢复52项在Linux再次合测178 passed。Ruff、shell语法及diff空白检查通过，独立代码review无启动阻断。测试验证旧默认身份、真实请求预算、仅length选择、同目录回放不重复调用、暂停和父证据错配；这些是工程验收，不是方法效果。

额外CLI、数据及指标回归89 passed、1 skipped；跳过原因是本机未安装可选固定版GEPA，不属于本次恢复依赖，不能将该项算通过。

实际冻结清单105＝KOR104＋Sheet1，排除C的43个已交付位置。协议hash为`143ad3d567a6ca02977139ad1c304f24b2bea412782d516b1d3b287762346ec9`。恢复源码SHA256为`a8288ebf4b457eb07958d1176f403386d865746992028a6540205860e6dbd67d`，API源码为`d1e29687e90ae7368076f61968e2bf2c1b188d8ae0878c7780e903468bc2b302`，本机与Linux一致。

15:15:57快照：首个真实请求已完整返回，1次HTTP、239.945秒，343输入＋11,328输出＝11,671报告tokens，输出中11,259为reasoning；HTTP200/stop，正文可提取，原生KOR评分fail。已完成1/105，另10调用在途，其余94未提交。这只证实新预算能实际调用且本题恢复交付，不是准确率改善；当前全批成本仍不完整，不将首调用用量当全批成本。tmux独立于本机网络运行，日志为D的`launch.log`。[启动摘要](results/truncation-recovery-32768-20260930.json)。

在D快照目录的实际命令如下。准备和启动已执行，不要重复创建或并行启动。

```bash
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery prepare-budget \
  --parent /root/continual-truncation-recovery-20260929-c/run \
  --output run --max-tokens 32768 --read-timeout 600

# 已在 tmux continual-truncation-32768-20260930-d 内启动
bash -ic 'source scripts/run_truncation_recovery_linux.sh /root/continual-truncation-recovery-20260930-d'

# 后续安全暂停及只读报告
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery pause --output run
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery report --output run
```

[当前流程](current-workflow.md) · [结果账本](results-and-lessons.md) · [上一轮恢复与暂停记录](truncation-recovery-resume-20260929.md)
