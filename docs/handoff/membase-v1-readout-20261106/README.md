# membase-v1 读数（2026-11-06）

记忆基线：每个 bench 单独建一份记忆，只在这个 bench 的测试集上读，不跨 bench，没有 5x5（负责人 11/04 的决定）。
负责人 11/05 约 01:33：“基线跑完后的测试数字可以链末直接打开记录”。两条链 12:47 前都 chain_complete；`shared/owner-continuation.json`
按这句话代写（decision `stop`），12:50 起用登记的 `run_execskill.py report` 解封并读数，13:34 结束，读数标签 `read_after_stop_decision`。

- 代码快照 `/data/execskill-code-20261106-membase-v1`（提交 `e988197`），运行根 `/data/execskill-20261106-membase-v1`（dl）。
- G 链 GLM-5.3；D 链 deepseek-v4-flash（northgate，请求同时写 `reasoning_effort: none` 与 `thinking: disabled`，读数在 11/06 00:11 的服务变化之后）。
- 组：C 指令卡；B 空白；M_expel 指令卡 + ExpeL 式记忆（练习里总结的要点 + 检索到的相似例题）；M_knn 指令卡 + 只检索相似例题；T_dc 指令卡 + 冻结的 Dynamic Cheatsheet。T_awm 这次没有启用。
- 记忆在 11/04 与 11/05 两个快照上建，读数在 11/06 的第三个快照上做。
- 未知格的计分口径：C、B 算对，记忆组算错（只在表格题上出现），对记忆组偏保守。
- 同文本噪声还没测（要等 v2.24 的重读）；ALFWorld 的区间按房间算，很宽。
- 账本：读数共结算 71,910,495 token（G 35,143,323，D 36,767,172，冒烟 1,731,652）；建记忆的花费记在 11/04、11/05 的旧账本里。

文件：`readout*.json` 是 `report` 的原始输出（只有计数、哈希和标签）；其余是 `docs/paper/scripts/baseline_results.py`（sha256 `4c6b66d0…`）
生成的表，734 项检查全过，退出码 3 只因为 v2.24 文字 Skill 基线还没有输入。
