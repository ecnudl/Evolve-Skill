# 长输出预算和统一配置基线实验

2026年10月1日，继续处理预算截断、工作簿兼容性及学习端配置。本轮把“端点接受更高预算”“真实难例能否完成”“统一配置下baseline成绩”分开验证；旧结果、失败启动和原始分母不改写。

## 截断应怎样处理

此前3次65,536-token响应正文为空，几乎全预算用于推理。继续提高预算可能帮助交付，但不保证终止或正确。[官方GLM-5.3说明](https://docs.z.ai/guides/llm/glm-5.3)列出128K输出、始终启用思考及low/high/max选项；不同服务端点仍需实际确认。本仓库已经显式发送low，不能再通过“关闭思考”解决。

本次BigModel端点短参数测试：`max_tokens=131072`、HTTP200、完整流、stop、返回OK，1次HTTP、28报告tokens、1.237秒。它只证明参数被接受，不证明服务端不会内部限长。[探测回执](results/bigmodel-131072-parameter-probe-20261001.json)不含密钥或推理正文。

正式比较应在运行前为各方法固定相同输出、时间、重试和工具预算。预算耗尽仍保留`unknown/model_response_truncated`原始状态：没有完整可评答案，不把它认定为已证语义错误；端到端成功率的全任务分母不能删除这些位置。同步报告：

- 完整面板的`pass/N`，表示预算内任务成功，所有截断仍在分母。
- `pass/(pass+fail)`及可判定覆盖率，不能只报前者。
- 预算截断、API/执行环境未知、操作中断分别计数，成本不遗漏。
- 若同时存在审计未知，额外报告保守区间`[pass/N, (pass+unknown)/N]`；不是给截断虚构半分。

残缺文本若没有合法答案，不用LLM-judge猜答案，也不从隐藏推理中抽取。以后若引入继续生成或预算自适应，需对所有方法用同一预设规则，并报告累计预算；不能只对待比较方法失败的位置反复抽样到正确。

## 一次有限的128K诊断

新增`truncation_recovery prepare-ceiling`，只接受完整冻结v4父运行中的HTTP200/length且流已正常结束的调用。新v5保留原prompt、任务、Skill、重复身份及原评分器；不选已完整答错的回答、不选开放调用。API仅在BigModel GLM-5.3、显式stream/wall3600时允许大于65536、最高131072；普通eval-v2和learning-v2仍限65536。

| 分层 | 父层与位置 | 本次上限 | 读取空闲 / 每HTTP整次时限 | 最大并发 |
| --- | --- | ---: | --- | ---: |
| G | E的3个65,536截断 | 131,072 | 300 / 3600秒 | 2 |
| H | F的4个32,768截断 | 131,072 | 300 / 3600秒 | 1 |

两组均于00:55:00在Linux后台开始，首个真实请求完成后才释放各自并发。首次00:54启动因shell未加载`proxy_on`在请求提交前失败；旧`launch.log`保留，实际运行用`launch2.log`。3600秒是单次HTTP尝试上限，既有最多3次尝试可达约3小时/逻辑调用；仍保留32MB流数据和最终正文限额，131072不保证交付。v5不能再自动加长或跨目录重抽，结果单列，不混成全benchmark的新成绩。

G协议hash：`0860c05d38b25157af3e9883c92613e5d9b57ea678b948545bfa928c685595b1`；H协议hash：`7909b1ef430998da6c8fee2700223b43653e2d99e8e7a4314713f9312a38b460`。源码与原父证据已绑定，Linux API/恢复/探测专项248通过，独立review无阻断。

**G已完成**：3位置＝3题/2任务族，均HTTP200/stop/流完整，原评分为1 pass/2 fail/0 unknown，3逻辑调用/3HTTP、119,371报告tokens，无开放调用。三次实际completion分别18,780、34,349、65,079，全部低于旧65536上限；既无等预算重采样对照，也未观察到真正超65536的响应，因此不能将恢复归因于增加上限或证明端点实际放行到128K。它支持交付恢复，不支持两份错误答案被“修好”。不再补抽完整fail。[G终态与逐位置成本](results/truncation-recovery-131072-g-final-20261001.json)。

H于01:25:29结束：4位置＝4题/3族，2 pass/2 fail/0 unknown，4调用/4HTTP、152,632报告tokens；最大completion58,377，全部低于65536，0开放调用。[H终态](results/truncation-recovery-131072-h-final-20261001.json)。G/H共7次均交付、3 pass/4 fail、272,003 tokens；完整错误不重抽，不再自动加长。01:11:54的[运行快照](results/long-response-baseline-launch-20261001.json)原样保留。KOR原160截断位置沿事后恢复链累计76 pass/73 fail/11未解决，11项为操作中断及通信未知，不能把这条多预算链当新统一预算分数。

## 学习与评测共同配置

`continual-learning-v2`已实现，SkillOpt/GEPA使用与eval-v2相同的stream/read300/wall1800以及明确low；solver预算不超过65536、reflection不超过16000。默认v1和历史结果不变，未知仍Pending，旧优化器不能通过重新执行来无损续训。独立review与含官方GEPA的专项测试通过。

新组已于01:03:18在Linux后台启动，使用原BigCodeBench开发面板完整400题×2次No-Skill；两个学习适配器仍使用共同空父、相同65训练题/64族与64选择题/64族、两轮预设预算。Solver上限统一65536、反思保持4096，不临时缩小任务集。数据已在旧开发实验曝光，不能称新holdout或独立final。SkillOpt完整训练轨迹反思与GEPA小批反思的算法调用模式不同，等预算上限不等于等实际消耗。

学习和No-Skill评分都需要原生容器，16GB机器上使用共享执行锁串行，避免两个8GB评分容器叠加；No-Skill模型采集6并发，连同最多3个恢复位置及1个学习调用不超过10。SkillOpt完成后才轮到GEPA；非零/Pending会停学习队列，No-Skill另行保留采集和评分。没有自动五阶段训练、S1评测或Skill准入。新学习器仍不支持随意杀进程后恢复，Linux tmux后台任务不依赖Mac保持联网。

准备回执hash：`04ba994e72bb595896b23c0fbfe49ed038d72acdb9b2ac4c3ed1344dd0bc31ea`。执行器资格为真实Docker readiness通过＋正确/错误/语法错误控制3/3，4容器共16.685146秒、0API；相关Linux测试625 passed（已显式指定固定官方GEPA源码，0跳过），准备/启动脚本另有独立review。只保证工程检查通过，不保证最终成绩。

可回放核验：

```bash
cd /root/continual-baselines-long-20261001-source
/root/continual-learning-env-20260928/bin/python -m scripts.prepare_long_baselines \
  --check --output /root/continual-baselines-long-20261001-study
```

私有产物在study下`no_skill/`与`learning/skillopt/`、后续`learning/gepa/`；公开报告只保存汇总及证据哈希，不上传凭据、原题/隐藏测试或原始API缓存。

01:04:45首次真实回执核验：No-Skill 143/800已闭合调用、6在途、143份available，尚未评分；SkillOpt空父selection已9份评分（3 pass/6 fail），第10份在评分，还没有候选。两端真实请求均65536/low/stream/read300/wall1800，已知报告tokens分别59,104和4,262，0响应unknown、0重试。GEPA未启动。此处是运行健康抽查，不是最终准确率或方法结论。

**01:14:30采集终态核查**：No-Skill全部800调用/800预测已保存，800 HTTP均stop，0截断，324,867报告tokens；正在等待学习释放共享native锁后评分，目前没有新65536准确率。SkillOpt仍运行，GEPA尚未启动。01:15:48汇总再次确认800份available、流完整，最大实际completion 6,925。[完整采集摘要](results/noskill-long-generation-20261001.json)。大输出上限不代表每次消耗上限，不应按800×65536估计已用token。

**随后终态与接续**：SkillOpt以`native_reflection_parse_incomplete`停止，空父选择33/64、训练36/65、0任务unknown；9次反思中2份JSON不合法，均未截断（952/566 completion）。共138调用/138HTTP、103,424报告tokens，尚无候选或gate。No-Skill已经取得共享锁并开始评分。GEPA原队列随Pending停止后，01:38:58由新运维入口按原manifest独立排队，不改旧日志；一次有限反思重提分支正在review，不称无损续训。[夜间监控、修复及后续结果](overnight-baselines-20261001.md) · [SkillOpt终态摘要](results/skillopt-long-pending-20261001.json)。

## 已完成基线数据（旧4096预算，不是本轮65536成绩）

| No-Skill开发面板 | 独立任务 × 重复 | Pass / Fail / Unknown | Pass / 全部位置 |
| --- | ---: | ---: | ---: |
| SearchQA | 400 × 2 | 552 / 242 / 6 | 69.00% |
| BigCodeBench | 400 × 2 | 416 / 382 / 2 | 52.00% |
| KOR-Bench | 500 × 2 | 639 / 201 / 160 | 63.90% |
| ALFWorld train | 39 × 2 | 60 / 6 / 12 | 76.92% |
| SpreadsheetBench原缓存评分 | 80 × 2 | 59 / 39 / 62 | 36.88% |

均为BigModel GLM-5.3 low；unknown包含预算、基础设施和操作中断，不是全部语义错误。重复位置不能算独立题；ALF不是valid_unseen；BCB使用8GiB评分资源而非上游30GiB设置。全2838位置的已知报告tokens为3,764,309，部分调用/重试成本未知。[来源、逐重复与成本JSON](results/noskill-fivebench-20260929.json)。事后多档预算恢复与工作簿新评分单列，不混入此表。

旧SkillOpt第一候选28/64，空父39/64，2胜13负49平而拒绝；第二候选60/64完成（26 pass/33 fail/1截断），4未提交，优化器Pending。即使未知和未提交的5位置全成功，最多31/64，仍低于该父39/64；这只是上界检查，不替代旧gate或为第二候选补成绩。新运行是重新冻结的开发配置基线，不以修复一个截断来声称旧候选可接受。GEPA旧轮未启动。

## 工作簿兼容性修复范围

[上一轮完整160重评](evaluation-environment-recovery-20261001.md)为54 pass/40 fail/66 unknown；恢复32旧unknown却失去36旧已知结果。新v3只修可证明的数值导出表示：原工作簿的非公式、非数组派生数值与UNO在计算前后的binary64值须精确一致（含signed zero），才能恢复导出XML中的原literal表示。不是两位小数容差，不改模型输入、不修公式或缓存、不填预测答案；无法证明时仍unknown。

代码经独立review及数值阈值负控；真实LibreOffice q3 9/9通过，9容器18.811530秒、0API、0清理失败，资格hash `e67294a67d5a7cce88dbcd5e63e92768853ea65c0a63a77de84aeef63c80b881`。新增控制证明精确导出恢复可行，并保留错误公式的错误结果，不是自然数据方法效果。

全160位置于01:00:01在新C目录启动，01:09:01完成，协议hash `6b669f246f31d25d548c7502979a47070d9d577c68da28328d5059d180eaf4eb`。仍只有150份旧产物可交付，其他10位置保留原原因；单工作簿120秒限制未变。

| 同一80题×2位置 | Pass | Fail | Unknown | 可判定覆盖 |
| --- | ---: | ---: | ---: | ---: |
| 原缓存评分 | 59 | 39 | 62 | 98/160 |
| v2独立重算 | 54 | 40 | 66 | 94/160 |
| v3数值导出保真 | 59 | 41 | 60 | 100/160 |

相对v2，3道独立题的6位置恢复为5 pass/1 fail；其余54 pass、40 fail、60 unknown全部保持。相对原始评分，32 unknown恢复、30已可判定转unknown，两方向都保留。因此有明确的局部兼容修复，但没有模型提分，也没有完整Excel等价环境。

成本为165容器、累计486.822秒、0清理失败、0API；564项旧证据和v2源码均未改变。26份工作簿回执恢复795个数值literal文本，44,018个输入数值通过前后精确检查，不改公式缓存。剩余60 unknown包含16个扩展函数不支持、其他外部/易变引用与工作簿结构、语义保留失败、参考漂移，以及10个原未交付位置。不能通过放宽容差统一消除。[完整转移、原因与资格JSON](results/spreadsheet-recalculation-v3-final-20261001.json)。

**后续v4已完成**：限定公式语法位置的布尔literal/零参数函数等价拼写，13/13真实控制后完整重评为61 pass/42 fail/57 unknown，较v3恢复2题3位置（2 pass/1 fail），其他结果不变。167容器累计541.098秒、0API、564项旧证据未变；不改答案容差、不修改公式缓存，也不宣称完整Excel等价。[v4完整证据](results/spreadsheet-recalculation-v4-final-20261001.json) · [夜间后续记录](overnight-baselines-20261001.md)。

[当前完整流程](current-workflow.md) · [结果与经验](results-and-lessons.md)
