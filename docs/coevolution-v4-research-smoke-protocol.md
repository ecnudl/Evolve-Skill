# V4 研究链路独立工程 Smoke 协议

本实验是主 V4 三臂研究之外的功能检查，不修改、续训或重跑主实验，也不作为研究方法有效性的证据。选择依据是在 V3 报告中已经观察到的自然开发集错误；不根据主 V4 最终评测结果选择任务。

## 固定来源

仅读取原 V3 run `outputs/coevolution_v3/glm53_multifile_20260909_v1` 中三个已固定文件：

- `claims/2cff374d25c86c2184d9a2d009d31237eef5a3e5512ec69d0c1249b14e57a45d.json`
- `targets/a1a0986ee572574403e84f60cf879e01db04043dd4728cdd8209d00098ed280c.json`
- `api/calls/b0791e8e57f65d9f65cf7b2c9f8a6e31a2e09a62a5b0fb0a837875cf0a776df3.json`

任务为 `repo-v3-incremental_build_graph-local-update`，来源阶段必须是 `learn1`、history 0、round 1、repeat 0。Receipt 固定为 `8a34daa82f35bf46e706fcf9cf00d6f5e6df308297e4953bea7f926ee7f3b933`；候选代码哈希固定为 `b958e9664e64eb43a08eddd34c2faec6f8e5e143db61e39ccc682846a6b2b4b9`。

观察：菱形依赖 `a→{b,c}, b→d, c→d` 中，`d` 变更时，约定的结果为 `[d,b,c,a]`，实际为 `[d,b,a]`。已访问节点返回 `None`，导致共享依赖的 dirty 状态没有传给后续分支。

加载时验证原记录校验和、receipt 校验和、任务阶段、调用请求校验和、合同哈希、完整实际文件哈希及精确代码/合同引用。完整 public task 从原模型调用中取得；不读取 `tasks_private.json`、reference implementation、主 V4 calibration 或任何 final 数据。原 reference 结果仅作为已记录的有限行为差异，不宣称形式化正确性。

## 预算、两臂与冻结

在创建 API client 之前冻结脚本、本文、导入的 validator／research／transport／API／budget 源码、development packet 和 V0 哈希。

两个臂从相同 V0 和同一个 development packet 出发，依次运行：

1. Feedback：问题规划 → 仅内部证据分析 → Rubric 修改提案。
2. Research：问题及官方资料规划 → 获取官方页面、带精确引用的分析 → Rubric 修改提案。

每臂恰好 3 个逻辑调用，每调用最多 6000 token；合计上限 6 个逻辑调用。使用现有 PJLAB `glm-5.3` 配置，传输 worker 上限 4，但两臂顺序执行，且必须在主实验退出后由父任务启动。只复用既有的最多 3 次 HTTP 传输尝试策略；格式失败、截断、无效引用不重新采样、不加调用、不调整协议。总 HTTP 尝试上限 18。

资料仅允许现有组件规定的官方 HTTPS 文档主机、最多 3 页。沿用明确受信任的既有本地代理配置，不修改 `.env`、Clash、DNS 或全局代理；获取失败如实保留。任务合同优先于通用文档。精确引用只证明来源一致性，不证明语义蕴含或验证器正确性。

## 输出与判读

新输出只能放在 `outputs/coevolution_v4_research_smoke/<new-run>/`，不得写入主 V3／V4 run。

报告各阶段 API／schema 状态、实际获取页面、通过来源校验的 findings/quotes、Rubric 提案结构是否有效、真实调用与 token/HTTP 账本。

不执行新的候选代码，不运行 calibration，不晋级验证器，不更新 Skill，不改变任何主实验分数。成功仅表明固定预算内该研究链可以实际运行；失败用于定位具体工程环节。两臂一次性 smoke 不估计 DeepResearch 的收益、泛化性或安全性。

若流程失败或资料不支持修改，保留原样结果并结束；不得为得到成功演示而改动已冻结来源或再次采样。

## 启动

`prepare` 只冻结本次工程检查，不读取 API 凭证或访问网络。`run` 首先验证冻结信息，再执行预算内调用；`report` 仅校验读取已完成结果。

```bash
conda run --no-capture-output -n skill python scripts/smoke_coevolution_v4_research.py prepare --root outputs/coevolution_v4_research_smoke/glm53_natural_dev_v1
conda run --no-capture-output -n skill python scripts/smoke_coevolution_v4_research.py run --root outputs/coevolution_v4_research_smoke/glm53_natural_dev_v1
```
