# V11：冻结 SearchQA Skill 的 Coding 迁移与适用范围门控

预登记日期：2026-09-14。本协议在首次 V11 模型调用前固定；不修改 V9/V10。

V10 smoke 的 24 次请求和原评分全部保留。该工程试验发现原生真假断言的对象输出兼容缺口，以及 9 次代码交付失败；因此未启动 V10 正式 64+128 题。V11 只修正通用真假值观察与所有臂相同的输出载体，不以修正后的规则重算 V10，不重复使用其 6 道题。新输出要求为一个 Python fenced code block，不再要求 JSON 包装；旧产物解析器保持不变，仍不做字符修复、代码修改或模型重采样。

公开运行契约同步说明精确值比较与真假谓词的不同返回要求，但不透露任务私有检查类型或参数实例。V10/V11 同时存在通用观察修正、载体/契约改变和独立题目差异，不能将其成绩差解释为单一格式改变的因果效果。

## 研究问题与边界

检验真实在 SearchQA 学习并选出的 Skill 直接进入 Coding 后是否仍有效，以及一次独立目标域验证能否阻止无证据的使用。V9 的三条学习历史全部保留：h0 未学得获准新规则，h1/h2 为两个真正学得的版本。不是三次独立 Coding 训练，也不重新挑选来源最优 Skill。

这一轮不生成新 Skill，不更新 Rubric，不激活 DeepResearch，不证明完整协同进化优于 SkillOpt。直接注入是迁移诊断臂，不代表原版 SkillOpt 曾声明 QA Skill 可直接适用于 Coding。若全部回退 No-Skill，只能说明门控限制了使用，不能宣称学到了跨域泛化能力。

## 数据与执行

固定 Google Research MBPP-sanitized 427 题快照，commit `08a8d6736475776f42ffac23b2c13111a28e5795`，数据 SHA256 `ca95deaa9a01ef0a6f439f88bcf0dd3db3563d22f22aad6cae04ebb9a8d8c8e9`。数据按官方数据卡 CC-BY-4.0；来源和许可证快照保存在 `data/coevolution_v10/mbpp_sanitized_08a8d673/`。

只保留预先声明的静态兼容子集：唯一公共 Python 函数入口、受限纯函数运行环境、全部原始测试均可被封闭断言解释器精确表示。任一测试不支持则整题 unsupported，不能删测试。历史曝光、已预留题、规范化题意重复均排除；静态 eligibility 清单不是整池曝光，只有实际 selected manifest 消耗后续池。

确认池来自原 train + validation；最终池来自原 test。每道题对所有历史/条件共享。模型仅看官方题述与入口名、位置参数数量及关键字名称；看不到测试实例、预期值或参考代码。与官方含示例测试的提示不同。每个 case 重新创建候选 globals；不支持完整共享状态、类或无限制标准库。因此是 **MBPP-derived pure-function compatibility pilot，不是 canonical MBPP 排行榜复现**。

宿主只静态解析断言和比较 typed 值；代码执行仅在 macOS OS sandbox。子进程不接收私有 expected。保留 tuple/list/set/dict/bool/int/float/None 类型和 Python 精确比较；无浮点宽松容差。返回 re.Match 等非内置对象时，真假断言可由统一真值观察精确检查；等值/身份断言若无可传递的 typed 值则不可评。CPU 5s、墙钟 12s、RSS 384MiB 采样看门狗、无写文件/网络/凭据。资源失败（含 MemoryError）、非法执行回执为 unknown，不伪装成语义错误。所有返回值另由受信 child 统一计算 truthiness；原始真假谓词只使用该布尔观察。只有需要精确值而 typed 编码不可表示时才 unknown。child payload 仍不包含检查谓词或 expected；不存在针对某题/某结果的特判。

每个已登记任务的参考代码先在同一沙箱校准一次。失败不替换、不补抽，整题所有条件保留计划调用但 oracle unknown。候选无法提取、语法错误或违反已公开运行契约记失败；可执行代码按全部原断言评分。原始候选不修复、无反馈修订、无语义重采样。所有实际执行回执不可变缓存；resume 与 completed replay 不重跑已执行候选。

## 设计与预算

| 设计 | 共享确认题 | 独立最终题 | 来源历史 | 最多逻辑模型调用 |
| --- | ---: | ---: | ---: | ---: |
| smoke，seed 202609143 | 2 | 4 | 3 | 24 |
| formal，seed 202609144 | 64 | 128 | 3 | 768 |

只使用 PJLAB `glm-5.3`，temperature=0、stream=true、reasoning_effort=low、生成上限 4096 tokens。最多 4 workers，HTTP attempt 间隔至少 10s，429 后共享冷却 30s；每逻辑请求最多 3 次既有传输重试，所有终止失败保留。温度为 0 不意味着模型完全确定。

正式启动的工程前提是独立 smoke 的完整账本及离线重放通过、参考题可校准且无执行器资源/传输 unknown。候选语义成绩不作为是否启动正式试验的依据；若工程检查失败，保留 smoke 证据，修订后需新版本与新题，不能覆盖旧记录。

每题运行至多 4 个不同 Skill 文本：空 No-Skill、原 initial placeholder、h1/h2 来源 Skill。完全相同的任务/Skill/阶段必须复用同一实际请求；h0 的 raw 等于 initial，回退等于空 No-Skill。随机化请求顺序以缓解时间混杂，不把三个 history 的共享题看作三倍样本量。

最终四个策略：`no_skill`、`initial`（辅助）、`raw_transfer`、`scope_gated`。即使 raw 被 gate 拒绝，也按预登记执行其最终诊断臂，不能因成绩不佳撤销。

## Cross-Domain Validation Gate

全部确认执行完成后，一次性对所有真正学得的不同 Skill 共同门控；不向 optimizer 回传逐题标签。允许 Coding 子集使用同时需要：

1. 至少 64 个独立问题；smoke 不降低门槛。
2. 相对 No-Skill 的 all-attempt 完整测试通过率差值严格为正。
3. 配对 discordant 胜负的单侧精确二项 p，经两个不同 learned Skill 的 Holm 校正后不超过 0.10。
4. 观测损失位置比例不超过 2%（64 题最多 1 个）。此项包含 candidate unknown 导致的 all-attempt 损失，同时另外报告确实执行且失败的损失。
5. Candidate unknown 数不多于 Base。

h0 placeholder 永不标记 learned。通过是局限于本兼容 Coding 总体的 scope commit，不是 unrestricted Cross-Domain Commit；否则 Restrict 并使用空 No-Skill。上述小样本观测筛查不是统计安全保证或非劣性证明。

## 冻结、统计与报告

来源 run/Skill、数据 reservation、驱动/执行器/评分器/协议源码全部 SHA 绑定。确认门控及完整 deployment 写入 `final_freeze.json` 后才能 materialize 最终题。最终结果不得回流 Skill、Rubric、兼容筛选或阈值修改。修改需新版本与未曝光数据。

主指标为所有受支持原始断言全部通过，辅指标为断言通过比例。unknown 保留 None 并单报覆盖率；只在 all-attempt 汇总中贡献 0。报告条件间损失/获益、原始问题簇 bootstrap 95% 区间与 paired sign-flip 诊断；主要比较 scope_gated−No-Skill 和 scope_gated−raw_transfer 的双侧 p 做 Holm（0.05）。学习历史条件化推断，不声称覆盖训练随机性；单次响应/题不完全排除服务端随机性。

必须单报真正 learned Skill 使用量和 No-Skill 回退量；不能把空 Skill 与 initial 文本不同误算为“发生学习”。参考失效/运行契约失败/资源 unknown/上游 API unknown 分开，不能把兼容性限制归因于算法。

同时给出仅 h1/h2 真正学得 Skill 的描述性均值，区分实际学习迁移与 h0 的初始占位文本效应；它不是新增确认性检验，不据此挑选有利结论或改主要比较。

旧 V9 SearchQA 仅作为来源成效锚点，不与新 Coding 合并成预登记、多域独立最终评测。下一版本若依据本轮诊断学习机制化 Skill，必须使用新的开发/确认题，并预留新的 SearchQA retention 与其他 domain 测试，不能在本轮 final 上调好再报同一结果。

## 暂停与恢复

`--request-pause` 仅新增暂停意图；当前最多 4 个请求自然结束后写 drained checkpoint，退出 75。暂停请求、resume acknowledgement、API 账本均保留，不删除失败日志。再次 `--resume` 续用完全相同协议和缓存。这个机制不能阻止强制合盖断网造成在途传输失败；需看到 checkpoint 后再断网。不会修改系统持久电源设置或 Clash。

官方来源：[数据与 split 说明](https://github.com/google-research/google-research/blob/08a8d6736475776f42ffac23b2c13111a28e5795/mbpp/README.md)、[固定数据卡](https://huggingface.co/datasets/google-research-datasets/mbpp/blob/4bb6404fdc6cacfda99d4ac4205087b89d32030c/README.md)。
