# Skill／执行式验证器协同进化运行说明

本轮是可运行的两轮闭环，协议见 [运行前协议](coevolution-protocol-20260909.md)。只新增 `skillopt/coevolution/` 和独立 CLI，不覆盖早期结果、不更换凭据／代理、不提交 Git。

修正版正式目录：`outputs/coevolution/glm53_loop_20260909_v2`。第一版 `glm53_loop_20260909_v1` 已完整结束，仅保留为执行环境问题记录，见 [唯一工程修正](coevolution-runtime-correction-20260909.md)。当前代码不能混用第一版缓存；第一版旧代码保存在它的 `source_snapshot.json`。

两版均已完成；修正版于2026-09-09北京时间11:08:57完成全部两轮和720条留出记录。结果与局限见 [完整实验报告](coevolution-results-20260909.md)。不需要为查看结果再次调用模型。

```bash
conda run --no-capture-output -n skill python scripts/coevolution.py \
  --output outputs/coevolution/glm53_loop_20260909_v2 --execute
```

省略 `--execute` 仅进行48题／240个控制实现的本地自检和协议冻结，不调用模型。`--execute` 在冻结完整性通过后运行全部两轮和最终720个回答；已有精确缓存会被检查并重用，不重抽模型回答。仅允许一个进程使用同一目录。

程序输出每个阶段、请求进度和每轮决定。不会打印凭据或完整模型上下文。主要产物：

- `protocol.json`、`source_snapshot.json`、`tasks_private.json`：调用前冻结的协议、代码和任务；私有任务文件不能当作模型输入。
- `api/calls/`、`api/budget_reservations/`：逐请求原始响应、配置、耗时／token与预算保留，不含认证头。
- `targets/`、`claims/`：目标回答、真实执行的反例和引用依据。
- `decisions/r0.json`、`decisions/r1.json`：完整私有gate审计之前封存的决定。
- `histories/`、`states/`：两轮候选、选择与验证经验变化。
- `final_frozen.json`：所有分支完成后、留出回答生成前的冻结。
- `final_rows.json`、`results.json`：全部五条件留出回答及按任务族聚类的统计。只有 `results.json` 的 `status=complete` 才表示计划完整结束。

恢复只接受代码和任务完全匹配的已冻结运行。若请求已保留预算但未落盘响应（例如进程在网络调用中被强制终止），无法确定远端是否已执行，程序会停止，不静默重新收费。此时保留原目录，人工确认原因；不能删缓存重抽到成功。

最终分支可能保留空Skill并回退Base；最后候选诊断仍执行。零提交或同分是有效观察，不因此增加轮数或修改gate。未经最终报告，不把实时少量回答解释为方法效果。

独立汇总只读已完成产物，在独立目录保存审计结果，不加载凭据或调用API：

```bash
conda run --no-capture-output -n skill python scripts/summarize_coevolution.py \
  --run outputs/coevolution/glm53_loop_20260909_v2 \
  --output-dir outputs/coevolution/glm53_loop_20260909_v2_summary
```

输出已存在且输入完整性一致时可核验复用；不要覆盖原运行文件来调整成绩。若继续开发新的运行时代码，旧目录会因冻结哈希不匹配而拒绝恢复，应创建新的协议和输出目录，保留本轮产物。
