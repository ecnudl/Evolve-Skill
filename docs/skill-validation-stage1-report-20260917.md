# 阶段一交付报告｜2026-09-17

## 结论

**阶段一已经跑通：固定产物可以在公开验证证据与隐藏审计分离的条件下回放。** 本轮没有运行 Research、更新 Skill、执行新模型实验，也没有产生新的泛化收益结论。

按最新明确边界，本次只实施阶段一；没有提前实现阶段二、三。后续方法与接口约束已记录在[主线说明](skill-validation-mainline.md)。

## 完成了什么

新增 `skillopt/skill_validation/`，通过薄适配连接早期 Rubric 语义与历史执行回执，不改写冻结实验。

1. 区分可复用 Rubric 管线与单题检查实例；管线身份包含生成、执行、适用性、聚合及源码指纹。两个准入门暂时只能返回 `pending`。
2. 显式构建模型可见白名单，隐藏条件、Skill 身份、任务族、机制标签及私有审计；Research 开发摘要另设接口且注明 H 来源。
3. 按五类用途分区，阻止原任务／近重复任务族跨分区；fixture、mutant、来源不全和已暴露历史记录不能充当新的正式自然样本。
4. 固定检查回放已有公开行为结果、输入前后指纹和明确保护的文件；缺失证据保留为 unknown，不退回宿主执行代码。
5. 按共同任务义务统计，而不是按每个验证器的检查数量统计。unknown、覆盖率与成本分别报告。
6. 新增 CLI、测试和 CI 覆盖，更新 README 与研究索引。密钥、原始调用缓存及私有审计未提交 Git。

## 实际回放

### 工程 fixture：四个案例，不是方法效果实验

| 案例 | 回放结果 | 验证了什么 |
| --- | --- | --- |
| 返回正确、要求保持的输入未改变 | pass | 公开行为和状态证据分别可回放 |
| 返回正确，但违反“不修改输入” | fail | 行为正确与副作用失败分开归因 |
| 执行环境不可用 | unknown | 不把基础设施问题写成语义错误；两项义务均保留未知 |
| 任务明确要求原地修改 | 该任务义务 pass；输入保持检查 not_applicable | 不把不适用的保持要求强加给任务 |

上述观察全部标记为人工 fixture；没有把模拟记录称为模型实际执行结果。

### 真实历史记录：兼容性验收，不是新增正向效果

导入 V16 clean-resume 中的 `stable-top-k-indices` 开发任务，来源 solve ID：

`11abc4a5491a01588134af3faa138f9c0d0a3d9ecdc3f86002f423cef9ba33aa`

| 核验对象 | 结果 |
| --- | --- |
| 来源 | 真实历史 No-Skill，development，不能重新用作正式校准／确认／最终集 |
| 闭合依赖 | 106 个源码快照、任务清单、两阶段调用回执、三个执行引用完成核对 |
| 实际产物 | 两个实际代码文件，未用 starter 冒充产物 |
| 公开证据 | 两个已有公开 case；分别映射为行为正确和输入保持观察 |
| 有限证据结果 | 两项任务义务在已有公开观察范围内 pass；不代表完整正确性 |
| 私有结果 | 另存 `host_only/audit.json`，不进入验证器视图 |
| 本轮新成本 | 模型调用 0、资料检索 0、候选代码新执行 0 |

四个 fixture 加一条真实回放共生成 26 份 JSON 文件；全部重复回放后文件哈希保持一致。

本地输出目录：`outputs/skill_validation/stage1_20260917/`，其中 `smoke/` 为工程样例，`legacy/` 为真实历史兼容性回放。它们没有上传 GitHub。

## 测试与额外核查

| 验证 | 结果 |
| --- | --- |
| 新主线测试 | 135 passed |
| Linux 干净克隆的新主线测试 | 133 passed、2 skipped；跳过的是未公开的两项历史缓存集成测试 |
| V15/V16 runtime、validator、study 与 evidence_view | 212 passed |
| 早期 Rubric、Research、V5 core/evaluation | 160 passed |
| V18 离线回归 | 140 passed |
| 上述联合运行 | **647 passed，0 skipped，0 failed** |
| 新代码静态检查 | Ruff 通过 |
| 已提交源码干净导出的文档构建 | `mkdocs build --strict` 通过 |
| 历史源码保持 | 核对 94 个相关历史源码快照，均未变化 |

这些是软件测试数量，不是独立自然任务样本量。检查过程中修复了：相同代码跨条件互换执行回执、把旧组合分数误归因为返回错误、导入后嵌套字段被修改、缺失公开观察被静默丢弃等边界问题。

## Linux 准备情况

用户提供的 Linux 开发机可以连接，执行 `proxy_on` 后 GitHub/PyPI 可访问。设备约 7 核、15 GiB RAM，Docker 服务可用；配置后可用磁盘约 57 GiB。

新增独立环境 `/root/miniconda3/envs/skill_validation`，Python 3.11.16，安装了离线验收依赖，`pip check` 通过；原 base 环境未修改。默认 Anaconda channel 的条款未代签，环境创建使用单次 conda-forge 配置。

代码已通过 Git 同步到 `/root/Evolve-Skill-validation`，测试使用源码提交 `452d9a409f93be015e294dff55eb577f7275f696`。远端没有 `.env`，也没有复制历史原始缓存；两个跳过项不是通过。

Linux 的四个 smoke 案例及重复回放均成功。20 份 JSON 与本机逐字节一致，文件集合聚合哈希为 `2cb84a0f636fead27cfebf2a88dbf52dfbb9a10cdb2f0bbd868b362f10d98d52`。远端输出为 `outputs/skill_validation/stage1_20260917/`，没有遗留后台任务。

提交分支为 `research/skill-validation-stage1`，位于 `ecnudl/Evolve-Skill`。没有改写 GitHub 的 `main`，也没有为本次交付改写历史实验源码。

尚未拉取 benchmark 镜像，也未配置真实候选执行容器或上传 API Key。Docker 可用不等于正式沙箱和完整 SWE-bench 运行环境已验证。磁盘空间需要按后续小批任务镜像预算管理。

## 已知限制与下一步

- 新执行器、Research 和准入算法尚未实现；真实历史导入当前仅支持 V15/V16 Coding development 格式。
- 当前 H 是历史原生审计，不假定其绝对正确；第二阶段仍需自然产物和必要的盲审。
- 哈希只核对内部一致性，不认证执行来源；fixture 和历史回放都不能证明 Research 的独立增量。
- 真实三条件产物池、可迁移验证器校准、目标域验证和 Skill 内容更新仍没有新的效果结论。

下一步应进入阶段二：冻结同一批真实三条件产物，比较固定验证器、等预算无 Research 自适应验证器与 Research 驱动 Rubric。先回答“Research 是否补出合法有效的新检查、是否减少 Skill 相关漏检与误拒”，再接入 3A 准入比较与 3B 反馈驱动的真实 Skill 更新。
