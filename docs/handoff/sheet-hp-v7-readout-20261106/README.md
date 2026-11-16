# sheet-hp-v7 读数（2026-11-06）

负责人 11/05 批准：“可以，读 D 链被拒的表格题候选”，包括打开数字。这是事后挑选的上界，不是方法效果证据。

- 配置 `sheet-hp-v7`（路线 B v2.27），代码快照 `/data/execskill-code-20261106-sheet-hp-v7`（提交 `9f5b753`），运行根 `/data/execskill-20261106-sheet-hp-v7`，旧机器。
- 只有 D 链：deepseek-v4-flash，northgate，请求同时写 `reasoning_effort: none` 和 `thinking: disabled`。
- 五组，每组 204 道合格的表格题测试题：B 空白、C 指令卡、F_r3 / F_r4 / F_r6 = `main-v7` D 链表格题那一步第 3、4、6 轮被拒的候选程序包加指令卡。
- 06:42 启动，08:54 链结束，共结算 2,461,544 token。
- `sheet-hp-v7-readout.json`：预登记读数脚本的输出。`sheet-history-6rows.json`：六次旧读数的汇总计数，来自 `../main-v7-readout-20261105/sheet-d-recount.txt`。

读数脚本缺陷与处理：快照里的 `scripts/execskill_v227_readout.py` 第 81 行要求单元记录里的格子编号是 64 位十六进制，生产代码的格子编号是 32 位（`coevo5/cells.cell_id` 取摘要前 32 位），所以第一次运行报 `Invalid cell hash`、没有输出。
处理方法：把这个脚本复制到 `/data/execskill-20261106-sheet7-ops/readout-fix1/`，只把 64 改成 32，其余代码仍用冻结快照（PYTHONPATH 指向快照），只读运行。快照、运行根都没有改动。
原脚本 sha256 前缀 `586e4ca331c8cc4c`，改后 `6c2267f4ce734415`。
