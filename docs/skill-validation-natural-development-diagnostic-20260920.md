# 自然开发阶段诊断：不完整运行与参考答案审计

发布说明（2026-09-21）：下文分析的是初期 96 个开发位置；原始 `outputs/` 不随 Git 发布，路径仅用于持有原材料者追溯。最新断点与公开聚合结果见[发布汇总](research-progress-20260921.md)，不能将本页分数外推到后续已保存位置。

日期：2026-09-20。对象是 `natural_20260920_b` 的开发集，不涉及确认集或最终集的模型产物。本文不是效果报告，以下分数只称为**执行器原始评分**，不能解释为真实准确率或 Skill / Research 收益。

## 诊断边界与证据绑定

统计快照为 2026-09-20 08:40:47 UTC（北京时间 16:40:47）：已完成 96 个开发位置，即清单前 48 个任务的 No-Skill / Current 各一次（repeat 0）。原计划开发阶段为 64 × 2 条件 × 2 repeat = 256 个位置，尚未完成第一遍任务，也未开始第二遍。运行因再次出现模型服务故障暂停；另有 1 个未形成完整结果的 API intent，不算作第 97 个完成观测，也不重试不确定请求。

本次首先只读重建已保存的 artifact、公开检查及 host-only audit；按清单确认 development 身份，核对任务、原始源行、产物代码、模型回执、reference / candidate 执行请求的内容哈希绑定。核对执行回执证明“这些代码在这些输入上被执行”，**不能证明 canonical reference 的答案符合公开契约**。不以 public pass 代替语义正确，也不以加强测试 H 代替真值。

冻结身份：

- 数据清单（本地未发布：`outputs/skill_validation/natural_20260920_b/data_manifest.json`）：`267526ae729122242a0cdc83677708b9ac1e325fa2a00f97a714a7d5d2f56e30`。
- 协议（本地未发布：`outputs/skill_validation/natural_20260920_b/protocol.json`）：`2e6bd7529864a59d4ebc99f606afae832f39f1893915f844b097125364511e5e`。
- HumanEval+ v0.1.10 源压缩包 SHA-256：`272720b90ac375502c8ed23cd791c2a93dfb22a911641a494da74a426c09f101`。

随后仅为本次人工开发诊断，另行执行从公开契约推导的 141 / 76 最小案例；使用原有远端 Docker 执行器与已保存代码，不调用模型。这些新增工程回执单独存放在 诊断目录（本地未发布：`outputs/skill_validation/natural_development_diagnostic_20260920/`），不改原 H 标签、任务、答案或模型产物，不进入 updater，不归功于 Research。没有读取未来 final 模型结果。

## 尚不完整的执行器原始评分

每行分母均为 48 个已完成的位置，包含失败 API / 解析 / 执行不可用导致的 unknown；不是删去 unknown 后的成功率。

| 条件 | 公开检查 pass / fail / unknown | 原始 base 检查 pass / fail / unknown | base + plus（H）pass / fail / unknown |
| --- | --- | --- | --- |
| No-Skill | 35 / 1 / 12 | 33 / 2 / 13 | 31 / 4 / 13 |
| Current | 40 / 0 / 8 | 38 / 1 / 9 | 37 / 2 / 9 |

按相同 task / repeat 配对，Current 相对 No-Skill 的原始 H 结果为 **1 win / 0 loss / 32 tie / 15 unknown**。32 个 tie 包含 30 个共同 pass 与 2 个共同 fail。任一侧 unknown 的配对不推断输赢。

这里的唯一 win 为 `/76`；共同 fail 为 `/141`、`/145`。但 `/141` 存在已确认的 canonical reference 与公开字符范围冲突。因此，上表连“所有 fail 都是真实语义错误”这一前提也不满足，不能把 31/48 与 37/48 的差距解释为模型能力或 Skill 增益。本次不事后删题重算一个更好看的准确率。

### unknown 与服务问题单列

| 可用性 | No-Skill | Current |
| --- | --- | --- |
| 可解析代码产物 | 36 | 40 |
| API failure | 10 | 6 |
| JSON parse failure | 2 | 2 |

全部 22 个 H unknown 来自 16 个 API failure、4 个 JSON parse failure，以及 `/130` 两个条件的参考 H 超时。API failure 的最终事件为 9 个 HTTP 503、6 个 HTTP 200 但 upstream stream error、1 个在 503 重试后 HTTP 200 读取超时。最初观察到的 6 个 503 不是本快照的完整故障分母；完整快照必须使用上述 16 个 API failure。它们均不归因于 Skill 或语义错误。

`/130` 的参考 H 在冻结的 10 秒执行预算内超时，仍为 unknown。该题 No-Skill 的公开检查 fail、Current pass，是另一层可见执行事实；不能借此把参考不可用的 H 改成已证实 fail。公开检查表中 No-Skill 唯一 fail 即为 `/130`，不是 `/145`。

## 具体轨迹

### `/145 order_by_points`：已确认的共同算法错误，且公开检查漏测

公开题面给出排序例：`[1, 11, -1, -11, -12] -> [-1, -11, 1, -12, 11]`。两份已保存实现都使用 `sum(int(c) for c in str(abs(n)))` 作为键，忽略负数首位的符号；例如这会把 `1` 与 `-1` 当作相同键并保留 `1` 在前，直接违背公开示例。参考实现只对负数的首位数码取负。

两臂原始回执均为 base 3/6 mismatch、plus 963/1000 mismatch，无 reference / candidate 执行异常或不支持输出。更关键的是，两臂**公开检查都是 pass**：冻结的公开 wrapper 只提取到 `[] -> []`，没有覆盖上述题面中的非空负数例。这是公开例提取/覆盖的盲区，不是模型真的满足了所有已公开例。

两臂均使用返回新列表的 `sorted`，未见输入修改；因此没有证据把此共同错误归因于父 Skill 的输入保持规则。本诊断不修改冻结 wrapper，也不把人工发现补给本轮 updater。

证据：No-Skill 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/903938db2874ef793d07d8cddda3d88f6aa6455bf7446c09d9a9e2cdc556dd55.json`）、Current 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/a567e0f0266ae9bb82ff23780e1bfd3315c75dd8162419ff16d5fe6cb1393aa4.json`）、No-Skill H 回执（本地未发布：`outputs/skill_validation/natural_20260920_b/host_only/audits/39fd7e69885bca76a8821c48a14b7bb761ab26f9e18f700ff2470ac79214917f.json`）、Current H 回执（本地未发布：`outputs/skill_validation/natural_20260920_b/host_only/audits/427578b5b6dde6c766d057434e8ac21274b6acf7f62e253b67c3978b85e3b923.json`）。

### `/141 file_name_check`：参考答案与公开 ASCII 范围冲突

公开题面明确首字符范围为 `('a'-'z' and 'A'-'Z')`。两臂都同时要求 `.isalpha()` 和 `.isascii()`；canonical reference 只要求 `.isalpha()`，会接受某些超出该明确范围的 Unicode 字母。

原始结果为两臂公开 pass、base 26/26 pass、plus 各 4/1000 mismatch。源 plus 输入确实包含 `éxample.exe`、`éxaemple.exe`、`éxxample.exe`、`éxaemplee.exe`，其类型差异与代码分歧一致。不过原 H 回执只存聚合数量，不能假称已有逐例 actual 对照。

为给出不依赖隐藏答案的可读确认案例，本次人工诊断在执行前单独记录两个公开推导：`é.txt -> 'No'`（首字母不在所列范围）与 `a.txt -> 'Yes'`（满足每一条约束）。这两个案例不是模型提出的探针，也不是 Research 的发现；其参考、No-Skill、Current 各自实际输出和执行哈希见独立诊断回执。

证据：No-Skill 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/443726350e881b4a9a6d678dce48977ef576590e02029e17f06026ad38b9fe9f.json`）、Current 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/ae046ad22f2e284c295f5a04fd0de27e50dadbbf48a27e22fa6e7ebeb5b57593.json`）、原 No-Skill H 回执（本地未发布：`outputs/skill_validation/natural_20260920_b/host_only/audits/babed34a3c5d7bc28184257d76bc6e2faf165cbc75ac65b86bfd850dde6716f5.json`）、独立公开案例计划（本地未发布：`outputs/skill_validation/natural_development_diagnostic_20260920/plan.json`）。

### `/76 is_simple_power`：零底数边界，不见同类 oracle 域冲突

公开定义是存在整数指数使 `n**int = x`，未声明 `n > 0`。源输入契约也只要求两个参数均为整数。对 `(x, n) = (0, 0)`，使用指数 1 即有 `0**1 == 0`，无需争论 `0**0`。

No-Skill 在 `n == 0` 时跳过乘法循环，最终以 `1 == 0` 返回 False；Current 的循环可在下一次迭代识别零。原始 H 为 No-Skill base 10/10 pass、plus 1/897 mismatch，Current 全 pass。plus 确有 `[0, 0]` 输入。这里未发现 `/141` 式题面明确范围与参考实现相冲突的问题；零底数漏判具有公开语义依据。单个边界胜例仍不能说明 Skill 因果作用，Current 的固定 200 次循环上限也不构成一般正确性保证。

本次另执行 `(0, 0)` 的参考与两份保存代码，以把静态分析和实际输出分开记录；此人工案例不增加本轮 H 或 updater 证据。

证据：No-Skill 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/ba728f9a9ddbacfb33a1456d222dfb181960a8f08665b9f122cbd97dc6011eae.json`）、Current 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/797b87ffe4f8276c60a95b06adb1ded61b52eb3bcdee59c35eca84668fd455ce.json`）、No-Skill H 回执（本地未发布：`outputs/skill_validation/natural_20260920_b/host_only/audits/02349bff3b3f507198283e3687af46ce05a9e2bbe5d736678d7d82e5aeea7c94.json`）。

### `/132 is_nested`：No-Skill 提前接受未闭合括号；Current 无可执行 JSON 产物

No-Skill 只要扫描深度达到 2 就返回 True，不检查足够的闭合括号；如 `[[]` 或 `[[[[[[[[` 并不形成所要求的完整嵌套括号结构。这与原 H 的 base 2/14、plus 44/1000 mismatch 一致。公开 wrapper 的单个 `[[]]` 例通过，不能覆盖缺失闭合符号的情形。

Current 的响应无法通过 JSON 解析，未进入函数执行。不能把它算作另一个已确认算法错误，也不能把这对任务计作 Skill 的语义收益或退化。

证据：No-Skill 产物（本地未发布：`outputs/skill_validation/natural_20260920_b/artifacts/f8124e4b565f2f332d4c7a6ee11a11bbfc3c4b93297443da8597848557bdc400.json`）、其 H 回执（本地未发布：`outputs/skill_validation/natural_20260920_b/host_only/audits/855fa867cc9df2c351b18f50f2996f60cf6da5733a99e447775d8c5779823a3a.json`）。

### 独立最小案例的实际输出

| 任务与输入 | 由公开契约推导的预期 | canonical reference 实际 | No-Skill 实际 | Current 实际 |
| --- | --- | --- | --- | --- |
| `/141`：`é.txt` | `No` | `Yes` | `No` | `No` |
| `/141`：`a.txt` | `Yes` | `Yes` | `Yes` | `Yes` |
| `/76`：`(0, 0)` | `True` | `True` | `False` | `True` |

九次独立 Docker 调用均为 observed、无异常且 cleanup confirmed。调用前已保存公共案例计划及预期来源，回执逐一绑定精确源代码、参数和执行器；原清单、协议及四个所用模型 artifact 的文件哈希在诊断前后保持一致。见 封存汇总（本地未发布：`outputs/skill_validation/natural_development_diagnostic_20260920/summary.json`） 与 逐调用回执（本地未发布：`outputs/skill_validation/natural_development_diagnostic_20260920/receipts/`）。这些结果证明特定输入上的契约冲突或实现错误，不是新的正式评测轮次。

## 格式与父 Skill 归因边界

父 Skill 确有旧任务中的文件分段交付、不要 JSON、固定结果字段与输入保持等规则；本轮 solver 的更高优先级输出契约明确要求 JSON `solution.py`。这是合理的冲突审计方向，但不能仅凭父文本断言本轮失败由旧 Skill 导致。

四个 JSON parse failure 分别是：

- No-Skill `/73`：JSON 字符串中未转义的控制字符。
- No-Skill `/102`：非法反斜杠转义。
- Current `/110`：JSON 字符串后附 `.replace(...)` 表达式，不是合法 JSON。
- Current `/132`：非法反斜杠转义；即使剥去代码围栏仍无法解析，不能把围栏单独说成根因。

它们的 API 回执均为正常结束，不是服务中断。两臂各有两个格式未知；Current 也尝试了 JSON，没有观察到这些失败直接使用了旧文件分段协议。所检查的真实语义错误中，未发现 Current 独有的输入副作用、强制旧结果字段或固守旧任务约束轨迹。这里既不能证实父 Skill 无害，也不能把已知共同算法错误硬归因于它。

## 可以与不可以得出的结论

现在有依据说：`/145` 是两臂共同的真实语义错误，公开执行反馈对它存在覆盖盲区；`/141` 的 canonical reference 对公开首字母范围存在冲突；`/76` 可由公开数学定义确认一个 No-Skill 零底数边界错误；服务和格式不可用会显著改变可见分母。

现在没有依据说：Current 提升了真实准确率、Research 找到了这些问题、条件化更新有效、任何候选通过了独立校准或 Skill 准入。独立校准、更新、确认和最终阶段尚未形成完整比较。后续应先审计数据、参考答案与公开提取的正确性，再在显式版本化的协议中预声明如何处理冲突及敏感性分析；不能把本次后验诊断偷偷改为原实验的有效样本筛选规则。

本报告保留原始执行评分，未重写 b 的 H 标签或 truth，未修改冻结源码、清单、原产物或原回执。`/47`、`/148` 的公开参考适配问题已由预检单独处理为 unknown，与本次仅开发集诊断不同；它们不是借本次观察新增剔除的题目。

相关：[协议与能力边界](skill-validation-natural-pilot-20260920.md)、[主报告](skill-validation-natural-results-20260920.md)。
