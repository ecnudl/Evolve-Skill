# 8192截断恢复：只继续未提交位置

日期：2026-09-29，终态于2026-09-30复核。**C已于9月29日20:02:44完成148/148，0开放调用**，早于20:16暂停请求；原A的5个完成、10个中断和B的1个timeout不变。C共43个可交付响应、105个截断，原生25通过/16失败/107 unknown或不支持episode评分。下一轮只对105个截断使用更高预算，另建协议，不在本目录派发。详见[完整终态与下一轮](truncation-recovery-32768-20260930.md)。以下保留B/C实施、启动及暂停发送失败的历史记录。

**20:16暂停请求未送达**：用户要求断网前暂停。两次使用正常`ssh PJ-CL4MIND-DULIN`发送C的`pause --output run`命令均在SSH握手阶段被重置（exit255），`ssh -O check`确认原复用socket已不存在。没有证据表明远端PAUSE已建立，不能报告实验已停止；不改Clash、不强杀、不重启实验。最后成功只读快照为19:48:44：C完成90/148（11 pass、12 fail、67 unknown），10调用在途，48尚未提交；这是历史快照而非20:16状态。已落盘文件保留，远端后台可能继续或已完成。当前不再启动新实验或更高预算重跑。网络恢复后先核对C进程、终态回执及PAUSE，再按用户新的resume指令处理；不得依据旧快照重复提交。

19:01通过用户配置的`ssh PJ-CL4MIND-DULIN`重新连接Linux，确认无旧求解进程或运行容器。`proxy_on`在Linux同一shell执行，网关仍为原协议的无凭据PJLAB代理；未改Clash、VPN或历史实验。

## 暂停点复核

| 原恢复A状态 | 位置数 | 本次处理 |
| --- | ---: | --- |
| 完成并原生评分 | 5 | KOR 2 pass、3 fail；原样保留，不调用模型 |
| 已有意图但没有终态 | 10 | 均无位置call回执，亦无对应API终态缓存；保留操作中断，不重新抽样 |
| 从未开始 | 149 | 纳入新恢复B：KOR145、Sheet1、原SkillOpt候选1、ALF动作2 |
| 原清单 | 164 | 汇总仍保留所有位置，不把新149当完整面板 |

旧5份API回执均HTTP200/stop，已知用量合计5741 tokens；另10个在途请求实际计费未知，不能报告为完整成本。5个先完成任务不是代表性样本；其恢复也不能排除再次调用的随机性，不能由此断言增加token导致准确率提高。

## 新旧隔离与暂停修复

- A：`/root/continual-truncation-recovery-20260929-a`，原源码、协议及所有结果不变。
- B：`/root/continual-truncation-recovery-20260929-b`，只对未开始的149个位置采用原模型、提示词、评分与8192上限，最多10并发。
- 不重启SkillOpt/GEPA、不运行原来4个未提交选择任务；ALF仅动作响应诊断，仍不产生episode成绩。
- 修复方向：通过`PAUSE`标志或正常停止信号停止派发新请求，等待已派发调用与评分落盘后退出；使用有界在途队列，不把整个清单提前放入线程池。
- 启动交互Bash只用于加载`proxy_on`，之后关闭shell job control。以后不用`SIGSTOP`作为安全断点；上次STOP导致外层退出及10个开放意图的事实仍保留。

## B版实施与验收（历史）

- [恢复入口](../skillopt/continual_eval/truncation_recovery.py)新增v2协议、`prepare-resume`和`pause`。父v1按其封存绝对源码哈希验证，不与新版源码混比；父写锁仍活跃时拒绝准备子运行。父证据内容或清单发生变化也拒绝继续。
- 新入口同时排除旧位置意图、目录残留和孤立API缓存；已完成及有在途痕迹的请求不会再次提交。子报告单独列`inherited`，保留父164分母、5个完成及10个操作中断。
- 有界调度最多保留10个在途任务，`PAUSE`、SIGTERM或SIGINT停止补充派发；已经预留的调用及评分完成后落盘。PAUSE标志不自动删除；正常恢复重放不调用已完成位置。
- 专门测试本机和Linux均**24 passed、0 skipped**，包含暂停前零调用、在途收敛、恢复不重抽、父源码/证据更改拒绝、父写锁冲突、孤立缓存排除与信号处理。相关本地合测**248 passed、7 skipped**，7项为未安装的可选GEPA；不能算通过。Ruff与shell语法检查通过。
- 独立review未发现此次启动阻断问题。以上为工程验收，0模型效果结论。

新冻结协议hash：`7345300019a253bb41014bab6fc1003eefc36e25fff9227a7ec5f6fd276b472b`。tmux：`continual-truncation-8192-20260929-b`。B目录的`launch.log`保存启动/终态，`run/positions`和`run/api`保存私有证据。

## 首请求终态与下一步通信修复

B首请求耗时366.361秒、3次HTTP尝试，`error_type=timeout`，没有HTTP状态、返回模型、finish reason或usage。它不是HTTP200/length，不当作答错。当前客户端将不同TimeoutException统一记录，不能仅凭回执严格证明是ReadTimeout；但固定read120及2/4秒退避与耗时一致，长生成触及读取等待是需要验证的解释。

独立健康检查：同一BigModel GLM-5.3 low、仅128上限的短请求HTTP200/stop，1次HTTP，耗时1.190秒，21输入＋3输出＝24 tokens。无凭据TLS检查也在0.09秒收到401。它们说明短请求、基本连接和授权可用，不能证明8192复杂生成可在120秒内交付。健康检查成本另计，不并入任务准确率。

在首请求尚未返回时设置了协作PAUSE，不再派发其他位置；该请求的终态回执最终正常保存，之后因初始健康检查失败退出，无新增开放调用。不是重演A的强制停止。

新C协议仅继续148个未提交位置，将明确声明的读取等待上限改为300秒，同时绑定实际HTTP客户端与service身份；原提示词、模型、8192生成上限、非流式与重试策略不变。A/B源码、结果和缓存不改，B的已超时位置不再次抽样。**因此C不再是只改变token上限，还包含一次通信等待修复**；仍是工程恢复诊断，不是新方法效果。

C快照：`/root/continual-truncation-recovery-20260929-c`；协议hash：`8d1b27551163b103c38ecab6c4ec99eb9c48099db655d0b69387fc73e5c8a593`；tmux：`continual-truncation-8192-20260929-c`。其中KOR144、Sheet1、原候选1、ALF动作2。API及恢复专测在Linux **134 passed、0 skipped**，本机扩展回归217通过，独立review无启动阻断。最初远程测试因少同步一个测试依赖脚本而收集失败，补齐后重跑通过；未将失败计为通过，也没有触发模型请求。

默认API read120保持缓存身份不变；显式read300仅用于新C。父B先按原read120校验，再排除其终态失败；C以新service绑定请求与回执。启动器在Linux同一交互shell加载`proxy_on`，客户端也显式使用协议中的无凭据PJLAB网关，避免`trust_env=False`忽略环境代理。首个真实任务收到符合既定连接健康规则的HTTP200模型响应后才释放最多10并发；连接健康不要求任务答对，也不把length改判为可评分。

C首回执：1次HTTP、142.506秒，343输入＋8192输出＝8535报告tokens，输出中8183为reasoning tokens；`finish_reason=length`，`error_type=truncated_content`。它说明本次真实生成耗时超过原read120，并且8192仍不足以交付这道题；不能把B不同任务的timeout严格归因为同一原因，也不能据单题推断全体截断率。19:27核查时该位置终态已保存，另10调用在途，未重试这个新的截断结果。

下列为C的已执行准备/启动命令及后续维护命令。**A/B已封存，不再移除B的PAUSE或在B重新派发**，否则会与C清单重叠。

```bash
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery prepare-resume \
  --parent /root/continual-truncation-recovery-20260929-b/run --output run --read-timeout 300

# 真实启动已在tmux内执行；不要重复启动。
bash -ic 'source scripts/run_truncation_recovery_linux.sh /root/continual-truncation-recovery-20260929-c'

# 后续安全暂停：只停止新派发，等待在途收敛；不能再用SIGSTOP。
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery pause --output run

# 只读进度；pending/paused时退出码3不表示报告损坏。
/root/miniconda3/envs/skill_validation/bin/python -m skillopt.continual_eval.truncation_recovery report --output run
```

后续在C执行PAUSE后等待求解进程退出、检查开放回执，再由用户明确resume授权移除该标志，使用同一C目录重放；不创建新抽样替代已完成或不明确的调用。300秒是单次HTTP的读取等待，并非整个逻辑请求的总墙钟上限；仍可能发生最多3次HTTP尝试，暂停也需等待在途重试及评分，不能承诺300秒内退出。即使C的148/148全部产生终态，也不能称原164个位置全部恢复：A仍有10个操作中断，B有1个通信unknown，ALF2也只诊断动作请求、不恢复episode评分。

[原恢复协议](truncation-recovery-8192-20260929.md) · [暂停记录](truncation-recovery-pause-20260929.md) · [当前流程](current-workflow.md)
