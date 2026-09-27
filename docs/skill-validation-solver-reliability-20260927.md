# 9/27 求解可靠性修复与验收

本次只处理输出截断/格式、一次公开修订、公开回归保护；**没有改变任务判分、评测体系、Skill更新算法、Research或准入门槛，也没有重算历史成绩。**

## 改了什么

新增显式`reliable_v1`配置，接入`rule_solver`以及`mechanism_study`、`curriculum_study`的全部开发/确认条件。

| 方向 | 修改 | 保留的边界 |
| --- | --- | --- |
| 输出预算与格式 | 初稿/修订默认各4096 tokens，提示紧凑完整JSON | 严格解析、不修补截断文本、不失败重抽；Updater仍2048，课程生成仍6144 |
| 一次公开检查修订 | 干净、隔离和清理已确认的公开执行超时也有一次修订机会 | 超时不是已确认语义失败；SSH断连、环境故障不触发此机会；不读取H |
| 修订回归保护 | 初稿pass、修订fail/unknown时保留初稿 | 被拒修订及成本继续保存并能进入反馈，公开pass不等于完整正确 |

API健康策略与两阶段预算在调用前核对；配置、提示词和预算绑定到协议及回执，反馈导入时重新验证。旧默认`legacy`不变，新配置只能在新目录显式启用。两组学习策略和No-Skill待遇一致，不把协议改进包装成学到的Skill。

代码：[配置](../skillopt/skill_validation/solver_profile.py)、[公开修订](../skillopt/skill_validation/public_revision.py)、[规则调用](../skillopt/skill_validation/rule_solver.py)、[预算](../skillopt/skill_validation/single_round.py)、[反馈回放](../skillopt/skill_validation/public_repair_feedback.py)。

Review还修正了三个集成问题：实际API策略与声明不符时应在付费前拒绝；smoke预算不能依赖Current/Candidate恰好缓存命中；源码哈希必须绑定实际加载代码，而非任意`--repo`目录。新增smoke预登记上限为18次，实际只消费12次。

## 真实Linux验收

本机调度，PJLAB Linux Docker隔离执行；模型BigModel `glm-5.3`、temperature=0、reasoning_effort=low、并发1。不上传密钥至服务器，不裸跑模型代码。镜像固定为`sha256:b8fe4ce3655e95f7f22c2a87d8e03a2f1f0cedc488a8e9adf18cc5a18cfdf401`。

| 检查 | 来源与分母 | 实际结果 | 新模型调用 / 报告tokens |
| --- | --- | --- | ---: |
| 新配置完整smoke | 1个手工选定DSL家族、3个契约变体×3条件＝9位置 | 初稿9/9、最终9/9公开pass；5次KEEP、4次合法修订；0unknown、0交付失败 | 12 / 10,273 |
| 超时后的单次修订 | 1份历史真实不终止初稿；初稿原预算2048，新修订4096＋compact | 隔离超时unknown → 修订公开pass；只调用1次，不再次修订 | 1 / 1,152 |
| 修订回归保护 | 1份历史真实正确初稿及其错误修订，原响应/请求不变 | draft pass、attempt fail → retained原稿pass；保留被拒尝试 | 0 / 0 |

合计新增**13次逻辑请求、13次HTTP尝试、11,425报告tokens，0终态API失败**；17份公开代码执行回执（13＋2＋2），健康ping另计。没有H执行、Research调用或Skill更新。

完整smoke中的Current/Candidate故意使用同一份手写工程控制规则，相同请求共享缓存；不是两个独立学习分支。三任务为同一家族的保留输入、原地修改、无状态限制变体；不是三个独立任务族。初稿本来全部通过，不能从9/9推断总体通过率提高。两个历史案例为事后选择的工程控制，不是新独立效果证据。回归重放仍保留原2048和原提示词，未伪装成新的4096响应。

## 回放、测试与已知限制

- 真实完整smoke再次运行，结果字节不变。额外审计将新的API传输和所有非ping执行设置为立即报错，仍成功回放9位置：**0新模型调用、0重复候选执行，只有1次环境ping**。
- 两个针对性案例各自在同进程立即重放：均0新增模型、0重复公开执行。
- 独立review及专项回归覆盖三条件公平性、预算隔离、初稿/修订绑定、拒绝尝试保存、unknown语义、同目录变更拒绝、两学习入口完整流程与旧回放兼容性。历史F的3份details和6份请求重建一致。
- 首轮全量测试中12项旧macOS sandbox测试被外层沙箱阻止启动（return71）；没有绕过代码隔离或修改旧测试，同一模块原样复跑60/60通过。初次失败日志保留，不能隐去。
- 最终同一进程全量复跑：**2,600 passed，0 failed、0 skipped，用时183.31秒**；最终smoke入口8项也通过。复跑不重复累计测试数。机器可读验收见[结果JSON](results/skill-validation-solver-reliability-20260927.json)。Ruff及`git diff --check`通过；没有证据能保证不存在所有bug。

局限：4096仍可能截断；公开回归保护不能发现未被公开检查覆盖的损害；初稿交付失败仍保持unknown，不自动重抽。旧学习入口不会自动切换配置；`curriculum_study`在协议检查前做环境ping，所以配置冲突保证0新模型调用，不保证0环境检查。新profile无权继承任何旧Skill/Verifier授权。

### GitHub 发布前检查

从仅含 Git 暂存文件的独立副本验证，不依赖未跟踪源码或私有运行目录：主线、分析脚本、demo和API健康策略测试 **2,348 passed、0 failed、2 skipped，196.58秒**。两项跳过分别需要未公开的历史产物/闭合缓存，沿用原测试的可选条件；没有复制私有缓存来伪装公开可复现。这与上文2,600项本地回归是不同测试范围，不能相加或互相替代。

公开demo的14项文件哈希与96个历史评分位置重算通过；第一阶段离线smoke及规则学习fixture smoke通过，均0模型调用，不是新效果实验。41个本次发布生产Python文件的Ruff `F` 检查通过；扩展到测试文件有12条导入/名称提示（9条为跨文件pytest fixture的导入/参数同名，3条为未使用导入），不宣称全仓库lint通过。文档链接、依赖闭包、JSON和凭证扫描通过。macOS上的`/tmp`是符号链接，离线smoke最初按安全约束拒绝该输出路径，改用其真实`/private/tmp`路径后通过，未放松路径检查。

### 发布后的 CI 兼容性修正

提交`c8137ed`的[GitHub CI](https://github.com/ecnudl/Evolve-Skill/actions/runs/36319170325)为7项成功、2项失败，不能把前述本地验收称为跨版本CI全部通过：

- 文档严格构建产生46条站内链接警告。两份新主文档包含正常的GitHub源码/示例链接，但未列入既有的研究文档排除清单。修正为与其他研究报告一致、在GitHub阅读，并增加站点外部导航；保留`--strict`和文档正文链接。
- Python 3.12研究测试为2,418 passed、2 failed、2 skipped。两项失败均为深层JSON已返回`invalid`，但测试将异常类型写死为`RecursionError`，该环境实际经严格字段校验返回`ValueError`。测试改为核实安全不变量，并新增两阶段×两异常的4个定向测试；生产解析器、限制、缓存规则和历史结果均不变。

修正后本地相关模块在Python 3.10.20与3.13.12均62/62通过；仅含提交文件的副本通过`mkdocs build --strict`（MkDocs 1.6.1、Material 9.7.7）。这些不是Python 3.12的本地实测；其结果须看修复提交对应的[GitHub CI](https://github.com/ecnudl/Evolve-Skill/actions/workflows/ci.yml)。本次0模型调用，不改变实验结论或进化流程。

## 使用与存档

```bash
# 激活skill环境，在新输出目录执行；需已有.env和Linux源码快照
python -m scripts.smoke_solver_reliability \
  --output outputs/skill_validation/reliability_new_run \
  --remote-repo /absolute/linux/source/snapshot

# 若复用已有本机代理，可显式加 --proxy http://127.0.0.1:7890
# 新机制/课程实验在原命令与新输出目录上加 --solver-profile reliable_v1
```

私有原始目录：`outputs/skill_validation/solver_reliability_20260927/`。

- `real_smoke_a/`：冻结协议、9位置产物/公开回执、12条真实模型回执、summary。
- `real_smoke_replay_audit.json`与`audit_replay.py`：禁止新请求/代码执行的回放审计。
- `targeted_timeout_a/`、`targeted_nonregression_a/`：两个控制案例、原始公开输入哈希和回放结果。
- `targeted_checks/run_acceptance.py`：控制案例执行脚本；曾因受限环境无法SSH而在preflight停止，未消费模型调用或修改案例。
- `tests_regression_Ik5QW3/`保留首次全量、权限复核和最终smoke分项日志/XML；`tests_final.log/xml`为最终全量复跑。

`outputs/`和API缓存不公开；公开报告只保留审核后的摘要与哈希。本次不启动新的正式效果实验；评测体系另行确定。
