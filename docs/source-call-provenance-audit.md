# C/E 调用溯源：独立事后完整性核验

[审计脚本](../scripts/audit_source_call_provenance.py) 只读取已存在的结果和调用缓存，不修改原冻结实现或评估协议，不发 API、不补跑、不删除失败缓存。

在仓库根目录、相应 split 完整结束后执行：

```bash
conda run --no-capture-output -n skill python scripts/audit_source_call_provenance.py \
  --run-dir outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix \
  --split calibration
```

C holdout 完整结束后，将 split 改为 `holdout`。E 两个新增 arm 完整结束后：

```bash
conda run --no-capture-output -n skill python scripts/audit_source_call_provenance.py \
  --run-dir outputs/scope_evolution_v2/source_attribution_gpt55_20260908 \
  --split holdout
```

C 审计其全部预注册 arm（本轮 base/full/extractive）；E 只审计两个新增 lesion 的调用缓存，不要求 E 再拥有借用的 C Base/full 调用。E 的借用文件哈希仍会核对；如需审计这些原始调用，另运行 C 命令。

脚本从来源 manifest 对应的冻结本地 Arrow 缓存读取指定 split，核对保存的数据和 Skill 快照，再使用原 SearchQA system/user builders 重构每个请求。逐条核对：

- 行内 ID、arm、split、问题/gold、Skill 与问题哈希。
- `request_hash` 对应的 `calls/<hash>.json`，保存请求与重构请求的完整 digest。
- system/user、模型、service、任务 key 和请求 completion 上限。
- API 状态、响应正文和 usage 是否与 JSONL 完全相符。
- 原 evaluator 重算的 EM/F1、提取答案和 hard 分；API 错误必须无模型分数。

输出只包含状态、计数、错误代码和相关文件路径等非内容元信息，不打印问题、答案、完整请求、凭据或 session。CLI 禁止产生导入字节码文件，也没有写报告的参数。

| 状态 | 退出码 | 含义 |
|---|---:|---|
| `complete` | 0 | 要求的本地文件完整，所有已实现一致性检查通过 |
| `failed` | 1 | 检测到不一致、损坏或不支持的配置 |
| `incomplete` | 2 | 缺少要求文件或结果行；不能当作审计通过 |

如果同时缺文件并存在不一致，总状态为 `incomplete`，具体不一致仍列在 `error_counts` / `errors` 中。不要在目标批次仍运行时把不完整状态误判为数据造假；等待批次完成后再核验。

这项核验补充了现有 rollout 的行内 provenance 检查，但**不是服务端执行真实性签名，也不是所有依赖均受到密码学冻结的证明**。自洽的本地记录不等于第三方认证；它也不改变模型得分、API 成功分母、统计假设或研究结论。
