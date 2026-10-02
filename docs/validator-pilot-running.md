# Coding 验证器先导：运行与恢复

2026-09-08 的 v3 已完成，见 [结果与下一步](validator-pilot-results-20260908.md)。两条 Rubric 修订臂均未产生有效提案；流程完成不代表协同进化成功。以下同目录命令用于缓存恢复，不应把恢复当作独立复现样本。

这是独立、可选的先导程序；不替换 SkillOpt 默认 trainer，也不覆盖旧 SearchQA/跨域实验。只复用 SkillOpt 的 patch 应用器，短程候选生成不等同于完整 SkillOpt 训练算法。

目前执行器依赖 macOS `sandbox-exec`，其他系统会拒绝无隔离执行；移植 Linux 时需要先接入独立容器执行器。依赖见 `pyproject.toml` 的 `validator-pilot` extra。本机使用已有 `skill` Conda 环境。

模型服务只读取仓库 `.env` 的 `PJLAB_BASE_URL`、`PJLAB_API_KEY`、`PJLAB_MODEL`，要求 `glm-5.3`。不回退到其他供应商，不修改 Clash 路由，不向生成代码继承凭据环境。

```bash
conda activate skill
python -m pytest tests/test_validator_pilot*.py -q
python scripts/validator_pilot.py \
  --output outputs/validator_pilot/glm53_scope_calibration_20260908_v3 \
  --workers 4 --repeats 2 --rounds 3 --reasoning-effort low --prepare-only
python scripts/validator_pilot.py \
  --output outputs/validator_pilot/glm53_scope_calibration_20260908_v3 \
  --workers 4 --repeats 2 --rounds 3 --reasoning-effort low
```

同一命令可以恢复已成功缓存的步骤；不会重新发出相同的成功模型请求。遇到已缓存的终止失败，会保留并再次报告，不会悄悄重抽直到成功。修改协议、模型传输参数或源码后必须建立新目录，并记录修订原因；不要删除旧失败缓存。

主要产物：

- `protocol.json`、`source_snapshot.json`：冻结配置与实现。
- `tasks_private.json`、`oracle_selftest.json`：本地任务和硬验证自测，不能输入最终评委。
- `api/calls/`：不含凭据的模型请求、结果、耗时、用量与每次 HTTP 尝试。
- `headroom.json`、`evolution/`、`skills_frozen.json`：来源满分停止与实际 Skill 更新。
- `development_revision_cases.json`、`research/`、`revisions/`：开发审计、官方文档快照与两个修订提案。
- `rubrics_frozen.json`、`holdout/`、`results.json`：冻结验证器后的相同产物配对审计。

最终留出集不得用于本轮选择或修改 Skill/Rubric。后续看过留出结果再修复时，原留出集只能作为开发资料，确认性验证须另取新任务。

## 独立的工程诊断

以下分析不改原运行结果。封装提取只读取冻结产物、重新运行本地硬验证，不调用模型；输出放在主运行目录之外：

```bash
python scripts/validator_artifact_sensitivity.py \
  --run outputs/validator_pilot/glm53_scope_calibration_20260908_v3 \
  --output outputs/validator_pilot/glm53_v3_posthoc_sensitivity.json
```

官方文档回归只获取原研究计划的官方 URL，不调用模型，不重判 Rubric。要求系统现有 HTTPS 代理恰为 `http://127.0.0.1:7890`；不匹配即停止，不修改代理设置：

```bash
python scripts/validator_document_probe.py \
  --plan outputs/validator_pilot/glm53_scope_calibration_20260908_v3/research/plan.json \
  --output outputs/validator_pilot/docs_proxy_probe_20260908
```

`scripts/validator_json_mode_probe.py` 是选定 train 提示的 fresh default/JSON 配对回归。默认不执行付费请求，`--execute` 才会调用模型。此次结果已保存在 `outputs/validator_pilot/json_mode_regression_20260908/summary.json`：第七次请求传输失败后停止，不删除失败记录来补出完整或更好成绩。新试验应使用新输出目录、说明修改及预算，不覆盖这次诊断。

新增代理传输和后验公共 Guard 尚未改接冻结的主实验流程；若接入，必须作为新版本冻结，不要直接修改 v3 缓存对应的源码。

公开源任务经过单模块和运行权限适配，结果不能标成官方 SkillEvolBench 成绩。上游未发现根许可证，复制的研究素材在公开推送前须单独审查许可；本轮不执行 Git 提交或推送。
