# 2026-09-29 恢复检查

**最新状态（9/29 16:48核查）：没有运行中的实验。** 五域No-Skill已完成；下午SkillOpt于14:50:45因第二轮输出截断进入Pending，队列停止，GEPA未启动。第一轮候选28/64低于空父39/64、被gate拒绝；第二轮60/64结果保留。本次仅核查及整理，未重跑。[全部结果总表](experiment-results-20260929.md)。

13:45恢复事实：SSH已连接；五域No-Skill均已于上午10:51前完成，原队列和容器已退出，没有重复运行。核验独立学习环境后，于13:44:49启动SkillOpt Coding单阶段学习，GEPA仅在前者成功完成后接续；首5调用HTTP200且完整。[完整基线报告](noskill-baseline-results-20260929.md)。

11:01的暂停请求当时因SSH重置未能发送；[暂停交接记录](baseline-pause-20260929.md)保留，不追认暂停成功，也不据旧快照重抽样。

**上午恢复事实**：已通过原样SSH别名成功连接并恢复实验。下文前半保留早先的新建连接失败诊断，不能据此否认上午恢复成功。BigCodeBench恢复评分、ALF B恢复剩余18个位置；已有完成记录不重跑。上午接续未自动启动原生SkillOpt/GEPA付费学习。

## 当前阻塞

SSH在认证前返回 `kex_exchange_identification: read: Connection reset by peer`。默认别名、禁用SSH复用/ProxyCommand、IPv4直连及IPv6检查均未连通。已有PJLAB域名直连配置未改变；未关闭、重启或修改Clash。

本机到PJLAB地址走现有SANGFOR隧道，aTrust进程存在，但这不能证明登录与资源授权仍有效。需确认aTrust/PJLAB登录状态以及开发机是否运行、资源授权是否有效；也可能为网关或服务端问题，现有证据不能进一步确定原因。

尚未进入Linux，所以本次**没有执行`proxy_on`，也没有测试模型API**。SSH握手失败不是API密钥失效的证据。远端实时进度无法核实，最近可靠状态仍以[9/28暂停交接](baseline-pause-20260928.md)为准。

### 后续重试：发现TUN与VPN重叠线索

用户反馈关闭Clash后似乎可以连接。本次保持Clash运行再试，SSH仍在认证前reset；指定VPN接口及经本地SOCKS的命令级对照也未成功。现有PJLAB域名DIRECT规则确实存在，但9/29 01:15–01:16的Clash日志显示aTrust隧道连接仍经过TUN；实时系统路由也显示已确认的VPN公网入口落在`utun1500`。这支持Clash与VPN路由交互的可能性，不能仅凭DIRECT规则排除Clash影响，也尚未证明具体因果。

未关闭/重启Clash或aTrust、未改变系统路由、未改任何代理规则。下一步可对已确认VPN公网入口尝试单个主机级路由绕行；需要macOS管理员授权，且应记录原路由与回滚步骤，不修改全局默认路由或整段私网。新实验仍未启动。

## 已完成的本地恢复复核

- 启动与恢复保护测试21 passed；BCB中断评分恢复测试12 passed。均为离线工程测试，0模型调用。
- BCB恢复工具只为精确绑定的单个开放评分意图补unknown，不重采样800份已有回答、不覆盖旧评分。连接恢复后仍需确认已退出故障容器实际清理，再提交恢复。
- ALF B的10个开放位置需重新核对；不假设仍有可恢复内存状态，也不直接重新采样。已有50份终态保留。
- 学习独立环境安装openai后的兼容性尚未验证；旧manifest的环境指纹不覆盖全部新依赖，dry validation通过不能替代Linux测试。需保存依赖清单，重跑三套测试并确认无skip，再做Docker控制。
- 原生执行成本只能报已知小计与缺失部分；BCB恢复回执需另行保留，现有私有备份白名单未包含`operator_recoveries`。

## 连通后的顺序

1. 核实进程、封存源与回执；处理ALF开放位置及BCB唯一开放评分意图。
2. 完成BCB剩余原生评分，同时恢复ALF未启动位置；不叠加十并发模型池。
3. 运行已冻结的Spreadsheet B（80题×2，并发2，注意容器内存总量）。
4. 独立环境验收通过后，再启动已准备的SkillOpt/GEPA开发训练先导。

[已有结果汇总](noskill-baseline-summary-20260928.md)。此次没有新增实验效果结论，也没有向GitHub或飞书发布。

## 已恢复：连接差异与实际操作

原样执行`ssh PJ-CL4MIND-DULIN`成功进入Linux；`ssh -O check`确认存在可用ControlMaster。此前诊断显式关闭了连接复用，失败的是新建连接，不能等价为用户的默认命令失败。现在沿用可用主连接，未修改Clash、VPN或系统路由。该操作注意已写入AGENTS.md。

- **BCB，10:04恢复评分**：先确认没有旧评分进程，检查并删除唯一已退出的无网络、只读临时容器；原始输入、预测、日志及回执保留。唯一开放评分位置已按精确plan/task/intent/prediction绑定记为`native_cleanup_interrupted` unknown，0重采样；其余未执行评分使用原冻结源码继续。恢复回执hash `fd5a37e5e63b2c557cd390db10c23704dbdb36e51a31d1d657f4003d8ee01053`。快照：633/800位置已评分，167待评，不报告最终准确率。
- **ALF B，10:11恢复生成**：10个因暂停失去环境的开放位置以原生`close_interrupted`闭合为unknown；已有50终态及全部正式调用记录字节不变，恢复操作0模型调用。随后只运行18个未启动位置，不重新抽样中断位置。快照：58 available、11 unknown、9运行中，总78，尚未评分。
- **额外原子写入残留**：一个`.pending-*.json`尚未发布为正式意图，初次dry-run正确拒绝。核验sealed内容、正式意图及对应回执均不存在后，精确改名为`.json.interrupted`，原始字节与SHA256不变、可恢复，不将它误计成一次正式调用。其原文仍是私有证据。
- **网络**：在Linux同一shell执行`proxy_on`，Python HTTP客户端经冻结网关返回401（不带密钥的连通性检查），只证明TLS/HTTP可达；ALF实际新生成回执另用于确认模型鉴权，不把401认作密钥失效。系统`curl`存在动态库符号不兼容，未改变环境，改用已有Python客户端检查。
- **实际模型健康**：10:14快照中新位置已有300份真实模型回执，300份HTTP200、299份`ok`，确认并发实际运行；`ok`不是任务正确率，该快照也不是最终API失败率。
- **接续**：有限调度等待ALF和BCB完成，再做0模型学习环境资格检查，再启动Sheet B（80题×2、并发2）。资格失败则学习保持Pending，不阻止独立Sheet基线。没有自动启动付费训练或修改协议。
- **自动报告**：Linux `/root/continual-resume-20260929/results/latest.md` 每60秒汇总，最多4小时；完整面板才显示分数，ALF A仍排除。新版成本汇总显式保留缺失执行成本，私有备份另保留operator恢复回执，不覆盖旧报告。

恢复相关离线测试：启动/回放21 passed，BCB恢复12 passed，ALF批量闭合与临时文件6 passed；成本汇总v2及既有工具联合52 passed，集合有重叠不累加。均为工程验收，不是新增方法效果。

## 下午接续：完整基线与真实开发学习

13:40恢复连接后，核查无旧tmux会话、实验进程或运行容器。上午有限队列实际已完成：ALF 78、BCB800、Sheet160均有终态；五域总1419题×2。去敏完整报告已复制本地，见[最新基线结果](noskill-baseline-results-20260929.md)；既有失败、中断、ALF A隔离记录不变，0重复No-Skill调用。

学习资格独立复核：382个冻结源码成员与archive一致，官方GEPA固定提交及111个安装源码文件一致；47项测试通过、0跳过，依赖检查及Docker正负控制正常。训练65题/64族、选择64题/64族互斥，均为development；选题在读取No-Skill结果前已冻结。实际源码与模型配置不改。

13:44:49在Linux启动有限SkillOpt→GEPA队列，模型GLM-5.3 low，输出4096；共同空父，每方法最多2更新、512 metric calls、32 reflection calls、600 API calls及200万已报告tokens停止阈值。实际成本不保证相等，token阈值不等完整账单硬上限。固定学习器单并发，不能将此前No-Skill并发10套到当前已冻结协议。

- 队列：`/root/continual-learning-launch-20260929-a/launch_learning.sh`；tmux `continual-learning-20260929-a`。
- 两运行：`/root/continual-learning-bcb-20260928-a/{skillopt,gepa}-run-20260929-a`。只有前一方法成功退出才进入下一方法；Pending/其他失败立即停，不自动补抽。
- `PAUSE`文件只在方法边界检查，不是当前优化器的无损暂停；当前优化器不支持中断精确续训。
- 只读有限监测：同launch目录`latest.md`、`status.json`，tmux `continual-learning-monitor-20260929-a`；每60秒刷新，最长4小时或队列终止后结束。它不启动或停止实验，不读取后续final，不输出Skill/提示词/密钥。
- 首17份模型回执HTTP200且完整，尚在初始selection采集；这是运行健康，不是训练改善。
- 监测器12个离线fixture通过，启动脚本语法检查和8份更新文档相对文件链接检查通过。未修改冻结学习器、未推送Git。

Spreadsheet的62个unknown已做[只读原因核查](spreadsheet-baseline-diagnostic-20260929.md)，未在当前队列中执行公式重算或改写旧评分。后续不得把该域可评子集准确率直接当完整基线。
