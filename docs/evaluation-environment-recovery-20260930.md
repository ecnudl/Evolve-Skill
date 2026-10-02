# 评测环境修复与失败位置恢复

后续终态核验及10/1工作簿环境验收见[新报告](evaluation-environment-recovery-20261001.md)。以下保留9/30暂停时快照，不把后来完成状态回填成当时已完成。

**17:54会话暂停交接**：用户即将盒盖，明确要求Linux已启动任务继续，本机会话暂停后续开发与新阶段启动。保留tmux `continual-env-length-20260930-e`、`continual-env-timeout-20260930-f`和`sheet-recalc-offline-build-20260930`，没有写模型运行PAUSE或终止后台作业。E已1/16完成（完整回答但fail）、4在途；F此前1/7完成（完整回答但fail），终态数量待resume复核。不会自动启动工作簿资格/正式重评。

工作簿代码通过独立review，本机相关347项测试通过；有限ArrayFormula支持已增加，真实七控制资格尚未运行。离线构建目录为`/root/continual-sheet-recalc-20260930-a/deb-cache-accelerated`，日志`build.log`，目标tag `evolve-skill-sheet-recalc:20260930-offline`。178个依赖包共142,533,736 bytes均经过SHA256核验、Linux传输已完成，构建不依赖Mac在线；同目录保留manifest/full-manifest/dependency-provenance。旧慢构建未清理。恢复后先核实E/F终态及镜像ID，再用最终冻结源码运行资格；资格通过后才统一重评150已交付产物并保留160分母。原记录和代码不要覆盖。

2026年9月30日。目标是改善长响应接收和工作簿评分覆盖，不是Skill泛化收益。旧结果原样保存，新协议使用独立目录。

## 已确认的问题

旧恢复D于17:20:54结束，105个位置为42 pass、40 fail、16 length、7 timeout，0开放调用。16个截断涉及14题/7家族，completion均32768，reasoning为32651至32767，答案正文为空。7个通信超时涉及6题/5家族，不能当作答案错误。105逻辑调用/145 HTTP（76单尝试、18双尝试、11三尝试）；已知终态报告tokens为1,840,287，超时及重试完整计费未知。82个完整回答均完成原生评分，不能把40个fail归为环境故障。[D终态JSON](results/truncation-recovery-32768-final-20260930.json)另存，不覆盖原启动快照。

原Spreadsheet B的160位置为59 pass、39 fail、62 unknown，其中52个位置缺公式计算缓存、8个执行异常、1个缺工作簿、1个截断。[工作簿诊断](spreadsheet-baseline-diagnostic-20260929.md)是重算输入依据。

## 修复协议

1. 长响应：新协议显式采用流式接收，300秒读取空闲时限、1800秒整次HTTP尝试时限，覆盖连接、响应头及正文；最多3次尝试，故1800不是整条逻辑调用的总上限。区分超时阶段，完整结束前不接受部分答案；不保存推理正文。长流式原始数据限32MB，最终答案仍有独立大小限制。历史默认服务身份不变。
2. 两个恢复分层：D中16个确证length使用65536；7个已闭合timeout保留32768以主要诊断传输。保持原GLM-5.3 low、任务、Skill、提示词、评分器及重复身份。首个实际响应后才并发，旧82个完整结果不重抽；开放调用和原生评分超时不纳入。
3. 工作簿：独立断网重算环境先做工程资格测试，再统一处理所有已交付工作簿，保留160总分母。不能只选择52个unknown，不能用参考答案补预测缓存；不兼容或有争议时保留unknown。

## 当前实施状态

长流式API及`truncation_recovery prepare-environment`已实现，使用v4协议。两层分别校验完整父记录、API缓存和原代码，保留D至更早各层来源，旧v1至v3不变。v4支持原目录协作暂停/恢复与无调用回放，不支持跨目录自动升档。本机317相关回归、Linux221 API/恢复专项通过；Ruff、shell语法、diff检查通过，独立review无阻断。

两个真实批次已于17:38:13在Linux tmux启动，每个批次先等待第一条实际响应再释放并发。length16位置/14题/7家族，上限65536、最多4并发；timeout7位置/6题/5家族，上限32768、最多3并发。两层都使用read300/单HTTP wall1800，显式绑定经核实的PJLAB代理，未修改Clash。

| 分层 | 独立目录 | 协议hash |
| --- | --- | --- |
| length | `/root/continual-environment-length-20260930-e` | `85cd07aafaefb47e39df2473c77ac05d68e762bd6faaedbd2b7731c851220fe0` |
| timeout | `/root/continual-environment-timeout-20260930-f` | `2247aa3d00ce68942cc729d0f91b698c8335f095ead8c757b2e3ca1236826836` |

API源码SHA256为`d6f729952d452681c99bd33677b3c93fdefc4e6fb1ac0631c7a184385fc56f2d`，恢复源码为`054504d8729cb9f076b8764915b9b0941d64cf495a19c6f734ca096602e7c67e`，本机与Linux一致。各目录用其自身封存代码执行`python -m skillopt.continual_eval.truncation_recovery report --output run`；不能跨目录导入另一份协议的源码身份。

额外流式健康smoke单列：GLM-5.3 low、128-token上限、相同长流式transport，HTTP200/stop且完整流结束，1次HTTP、4.297秒、106报告tokens（21输入/85输出）。缓存位于E的`health-stream`，不属于23个正式恢复位置，不能用短健康成功替代长任务健康屏障。另有123项CLI/数据/指标/兼容回归通过、1项可选GEPA依赖缺失而跳过。

17:49核验F首个真实长任务已完成：HTTP200/stop、完整流、525.909秒、仅1次HTTP、22,957报告tokens（355输入/22,602输出，其中22,417推理），原生评分fail。F为1/7完成、3在途、3未提交。该结果验证长响应交付和评分链可以工作，不能将原timeout变成fail称为能力提升，也不能用一次再采样证明流式传输的因果收益。E仍待首个终态。

工作簿重算镜像仍在构建/资格验证，正式重评尚未启动。review已要求加上公式语义保留检查，避免将转换器改写公式误报为模型正确。所有测试fixture单列，不代表方法效果。

[当前完整流程](current-workflow.md) · [结果与经验](results-and-lessons.md)
