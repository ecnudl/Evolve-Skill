# 扩样与重复运行：执行、恢复和分析

本轮使用 [冻结协议](validator-scale-protocol-20260908.md)，不改变默认 SkillOpt trainer 或旧实验。依赖原有 `skill` 环境和 `validator-pilot` optional extra，只调用 `.env` 的 PJLAB `glm-5.3` 配置，不修改凭据或 Clash 设置。

```bash
conda activate skill
python -m pytest tests/test_validator_scale_*.py -q

# 不调用模型：冻结任务、执行96个控制自检，并获取3个官方页面。
python scripts/validator_scale.py \
  --output outputs/validator_scale/glm53_repeated_20260908_v2

# 显式执行模型请求，计划840次、硬逻辑上限900次。
python scripts/validator_scale.py \
  --output outputs/validator_scale/glm53_repeated_20260908_v2 --execute
```

同目录同代码可恢复不可变缓存。恢复不是独立复现样本；终止失败不会被反复重抽直到成功。协议、任务或源码不匹配会拒绝恢复，应另建新运行目录并说明变更，不删除旧缓存。

`v1` 已因任务 JSON 输出要求与系统原生代码要求冲突而中止；有单独 `abort_record.json` 和原源码快照，不与 v2 混算。不能用当前已修正源码直接继续 v1。

主要产物：

- `protocol.json`、`source_snapshot.json`、`schedule.json`：任务/实现/参数与固定交错调用计划。
- `tasks_private.json`、`oracle_selftest.json`：任务与参考/缺陷硬自检；不交给 solver/judge。
- `api/calls/`：不含凭据的真实调用、HTTP 尝试、用量和响应。
- `targets/`：逐 task/arm/repeat 的原始代码、提取信息、公开/私有执行结果和完整性校验。
- `development_revision_cases.json`、`development_shared_transmitted.json`：所选开发案例与两个修订臂真正共享的输入。
- `research/sources/`、`revisions/`、`rubrics_frozen.json`：官方资料快照、单次修订提案、留出前冻结的规则。
- `judgments/`、`dev_judgments.json`、`holdout_judgments.json`：原始 judge、确定性 Guard、两个独立评分重复。
- `results.json`：只有全部计划步骤结束才生成，包含效应、逐题/逐族/逐轮分析、缺失性、探索性区间和预算账本。

运行完成后才允许执行额外只读审计：

```bash
python scripts/audit_completed_scale.py \
  --run outputs/validator_scale/glm53_repeated_20260908_v2
```

同一代码两次评价不是两个独立代码样本，四次目标生成也不是四个训练种子。尤其要同时检查任务族数量、自然行为失败数量、区间是否退化、各轮方向是否一致，而不是仅看总体通过率或 bootstrap 区间。

补充完整开发证据实验必须分两阶段。准备阶段不读取源实验留出结果；评价阶段要求自己的 Rubric 已冻结且源实验完整结束。两阶段均不生成新的目标代码，输出目录必须是源实验的独立兄弟目录：

```bash
python scripts/validator_full_context.py --prepare-rubrics \
  --source outputs/validator_scale/glm53_repeated_20260908_v2 \
  --output outputs/validator_scale/glm53_full_context_repair_20260908

python scripts/validator_full_context.py --evaluate \
  --source outputs/validator_scale/glm53_repeated_20260908_v2 \
  --output outputs/validator_scale/glm53_full_context_repair_20260908

python scripts/audit_scale_judge_whitespace.py \
  --run outputs/validator_scale/glm53_repeated_20260908_v2 \
  --output outputs/validator_scale/glm53_repeated_v2_judge_whitespace.json
```

补充协议及脚本另行冻结。相同目录的恢复复用缓存，不代表新的独立实验；要重新采样须使用新目录，并事先说明验证器生成、任务选择和评价重复的设计。

完成后契约审计不调用模型，仅在现有隔离执行器中检查已有引号解析产物。输出文件必须不存在；重跑应另选名称，不覆盖第一次审计：

```bash
python scripts/audit_scale_quote_contract.py \
  --source outputs/validator_scale/glm53_repeated_20260908_v2 \
  --output outputs/validator_scale/quote_contract_posthoc_20260908.json
```

它是发现 oracle 盲点后登记的有限范围诊断，不更新主实验分数，不是独立测试集；枚举字母表不含空格，不能取代原有空格保护测试。

本轮没有 Git 提交/推送；自建任务不是公开 benchmark 复现。看过本次 holdout 后，后续确认性修订须使用新的任务/项目，不把同一批数据继续称作未见测试。
