# 10/1 unknown 修复暂停交接

用户要求盒盖休息，等明确 resume 后再继续。已停止开发和新实验提交；不是后台自主继续扩展实验的授权。

## 远程当前状态

- KOR length 新独立诊断 `/root/continual-unknown-repair-20261001-kor-length`：暂停快照为 10 个指定位置中 1 个完成（pass、2,826 tokens、1容器/2.230644秒），1 个模型请求在途，8 个未提交。发送协作 SIGTERM 给已核实进程 2655172，并调用冻结 `request_pause()` 持久化 `PAUSE`；在途请求保存并评分后停止，不再派发下一题。Linux tmux 不依赖 Mac 保持唤醒。不能把暂停请求等同于在途已经终止。
- KOR network 新诊断已完成：1 fail、1调用/1HTTP/1,403 tokens；BCB原生零API重放已完成：1 SDK fail，存在 Pool/guard 超时兼容风险；Sheet 固定代码7位置诊断已完成；SearchQA6过滤位置只归档。
- 工作簿 v6a 资格为 18/20、rejected。没有启动160位置重评；无相关运行容器。失败资格及源码原样保留。
- 旧基线全部不变；私有日志/回执在本地 `outputs/continual_unknown_repair_20261001/`，公开摘要见[本轮报告](unknown-recovery-20261001.md)。

## 恢复前必查

1. 先试原 `ssh PJ-CL4MIND-DULIN`；本机换网后不要复用旧网关。精确路由及撤销说明在忽略的 `pjlab-network-20261001.local.md`，不要关闭或重启 Clash。
2. 核对上述进程是否退出、PAUSE是否存在、在途是否形成closed回执、容器是否清理。读恢复器 `report`，不得把未知在途自动重抽。
3. 用户明确resume且状态一致后，才移走单个PAUSE标志、使用同脚本/同目录继续未提交位置；不得更改原协议或替换旧评分。Linux API前同shell执行proxy_on，客户端保留已冻结显式代理。

## 未完成代码工作

- 新显式代码围栏解析器及 backend profile 已实现并独审；默认历史行为未变，95项联合fixture通过。独立 `scripts/replay_fenced_delivery.py` 与测试已写，32解析＋9回放测试通过，**独立review与真实重测尚未完成，也未部署**。恢复后先review，再对完整160原回复审计提取变化，只有预定义符合条件的旧unknown进行同回复重执行。
- 已确认旧SyntaxError来自围栏提取器错取解释文字；原回复有Python块。其余6个Sheet位置有明确生成代码交付/运行问题，不改写答案获得通过。
- v6a真实失败原因之一是Calc导出使用自定义`formatCode="General"`而非builtin0。仓库模块已保存v6b/view-v2修补及41项通过的单测，但**未部署、未进行新真实资格**。此外资格样例B1被Calc自动设为日期格式仍未解决；不要放宽预期或转换公式缓存来让它过门。旧v6a远端快照不改，恢复后先独审及离线分析，再决定新版本控制设计。
- 本轮全量回归测试在暂停收尾时结束：**3750 passed、6 failed、9 skipped**。6项均在 `test_continual_eval_frozen_rescore.py` 报 `Qualification execution source changed`；测试期间模块发生并发编辑，尚未在静止源码下复跑核实，不能直接归为已解决，也不能写全通过。恢复后先固定源码重跑这6项及相关完整性测试。此前相关新旧317 passed、代码profile相关95 passed、v6旧51 passed分别保留其实际范围。文档构建尝试因上轮临时docs虚拟环境路径不存在而未执行，不记通过。

没有commit/push，没有清理旧结果、API缓存或来源数据。
