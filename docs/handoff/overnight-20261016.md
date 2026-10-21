# 夜间工作交接（10/16 02:00 开写，部分数据凌晨跑完后补）

> 用户 10/16 01:58 睡觉，授权一个"长期的实验探索优化工作"。本文档是夜间执行结果的早晨入口。

## 0 TL;DR（早上 30 秒读完这段）

**四件新事（夜间 3 个付费探针 + 零调用审计全部完成，05:51 收尾）**：

1. **跨数据集互换 Skill 在 deepseek 上不害反可能略帮**（§9）：OfficeQA 学到的 Skill 应用到 SearchQA ≈ SearchQA 自己 learned；SearchQA 学到的 Skill 应用到 OfficeQA 真题 ≈ OfficeQA 自己 bzero/learned。10/14 GLM-5.3 上的"害 −3～−8pp"在 deepseek 上**没复现**——Skill 文本价值主要是"结构+格式"通用部分，不是领域规则。

2. **learned 加的 8 类 trick 条款中跨机只有 T9 (pop vs sample stddev) 带来可测真题收益**（§7）：T2 (multi-vintage) 跨机一致中性或负；其它 trick 在真题 trigger 子集上在噪声内。

3. **剪枝验证的关键发现**（§10，付费 1h）：手工剪枝版 `oq_s2_pruned`（bzero + T9 一段，4,476 B）→
   - **真题上 ≈ oq_s2**（3/2 p=1，剪掉的东西真题上没损失）✓
   - **生成题上 oq_s2 显著赢 pruned**（21/2 p=6.6e-5，−9.2 pp）
   - 推论：**oq_s2 加的条款不是"稀释"，而是"**只对生成题有用**"**。learning 产出的候选只能过**生成题门**，这些条款对真题没贡献。

4. **phase1 benchmark-feature-aware 生成器重新获得了合理性**（§10.3）：既然问题是"生成题偏差 → 条款只在生成题上有用"，让生成题分布更贴真题正是直接攻击这个链条。**原建议"条款级门先行"修订为**：先 phase1 生成器 → 门筛出的 edits 更可能对真题也有效。

**产出的实际工件**（可以直接拿用）：
- `/root/fivebench-g-20261015-probe-skills/oq_s2_pruned.md` 4,476 B
- `/root/fivebench-g-20261016-trick-tags-saved.json` —— 74 道真题的 trick trigger 标签
- 3 份 summary.json（cross-ds × 2 + pruning × 1）全部已读、已写入 §9、§10
- 本 memo

**没在跑**：所有探针都完工，tmux 空；router-deepseek.lock、native.lock 都空闲。

**早上第一步建议**：读 §0 → §10 关键推论 → §9.1-9.2 cross-ds → 决定 phase1 生成器方向。

---

## 1 跑了什么、还在跑什么

- **已完成（10/15 日间 + 本会话）**：弱模型探针 sweep 五格里的四格；按 label 拆的 OfficeQA 真题 vs 生成题 × 3 机数据；账本 10/16 00:50 条已归档；`docs/project-status.md` 已更新到 10/16 01:00。
- **夜间启动的新实验**（本会话 01:58，tmux `ae-cross-ds`，deepseek-v4-flash）：
  - **跨数据集伤害矩阵**：OfficeQA 学到的 `oq_s1/oq_s2` 在 SearchQA 168 题上评测（+ `empty` 作漂移锚）；SearchQA 学到的 `qa_s1/qa_v9` 在 OfficeQA 198 题上评测（+ `empty`）。
  - 目的：10/14 20:50 已经在 GLM-5.3 上测过（SearchQA 用别人的 Skill 普遍 −3～−8pp），这次看换一个模型族（deepseek）是否同样伤害。
  - 预计约 2 小时（~2200 格、几百万 tokens），事件型 Monitor 跟进。
  - 输出目录：`/root/fivebench-g-20261016-cross-ds-{searchqa-with-officeqa-skills,officeqa-with-searchqa-skills}/`

## 2 零调用深度审计：learned 到底加了什么？

**OfficeQA bzero（12 条，2,936 B）** = 读题/用 context/单位/对齐/show work/负号/相似系列/截断/格式/single-tag/concise。标准 Treasury Bulletin 通用指引。

**oq_s1（22 行，5,822 B）** 相对 bzero 新加 4 项，全部是**具体陷阱类**：
- 计算题"先列出抽取的 series（含 row/col/period 标签）再做算术"+ 二次验算
- **Multi-vintage 处理**：同一表格在多期 Bulletin 重印时，取最新一期（后期有修订）
- **Chart-only 页**：没有数据点就不要从标题/标签重建折线，优先引文显式值
- **Rounding 合规检查**：数字之后再核对 "nearest X" 的位数

**oq_s2（42 行，9,617 B）** = oq_s1 全部 + 又新加 6 项，全部**领域知识**：
- **32nds 分数记号**：债券价格 99.27 = 99+27/32，½ 加 1/64
- **日期短语翻译**："mid-March" / "third Thursday" / "week ending" 映射到具体行
- **措辞解码**："Poland" → "Polish zlotys"，question 常不逐字引用 label
- **多步算术二次验算**：geometric mean、compound growth、std dev 的交叉检验
- **population vs sample std dev** 约定（整枚举集用 population）
- **Multi-part answer** 的 bracketed 格式

**判断**：learned Skill **不是乱加东西**——每一条都是针对真实 OfficeQA 题型的具体 trick，训练集样本（如 UID0033 "March 3, 1977" 需要日期格式、UID0101 CAGR 多部分答案）恰恰命中其中几条新规。但 10/16 00:50 的测量说 learned−bzero 在真题 74 道上 = 0。

**我的解释（假设，不是结论）**：
1. 这些 trick 每条可能只命中真题里的 2–5 道（样本量在噪声带内）。要看到效果需要**按 trick 命中的题子集**单独测，不是整体 74 道平均。
2. 模型可能已经**隐式知道**这些规则（例如 32nds、CAGR 公式都是常识），显式写进 Skill 没改变行为。
3. 一些 trick 的 trigger（如 chart-only、32nds）在真题 74 道里**罕见**，根本没被激活。

**对 phase1 的直接含义**：**benchmark-feature-aware 生成器不能救学习流程**。learning 的产出已经相当针对 benchmark（具体到 32nds 这种细节），问题不在"candidate 不够贴 benchmark"，而在"candidate 的具体规则在真题平均里稀释了"。

**SearchQA**同理：qa_s1 相对 bzero 加了 Jeopardy/trivia 站点启发式、round-trip 验证、clue 的指代解析——都是**具体领域经验**，不是胡乱堆规则。

## 3 phase1 前置：训练真题特征档案（零调用）

OfficeQA 训练 50 道（`items.json` 的 `meta.part == train`）的实际样本：

| id | 问题类型 | 答案形式 | 关键陷阱 |
|---|---|---|---|
| UID0002 | 查表 1934 FY VA 支出（含 PWA 承担） | 507（纯数） | 单位 "millions of nominal dollars"、注脚需合并 |
| UID0033 | 1977-3 哪天 13w vs 26w T-bill rate 差最小 | "March 3, 1977"（exact 格式） | 日期格式 + 跨列相减 |
| UID0101 | FY2011-2019 Labor 部 outlays 的 CAGR + 多部分 | `[-0.150, 0.850, -1.146]`（bracketed） | multi-part + 符号 + 保留 3 位小数 |

**初步归纳**（我手动扫 3 道所得，不是全扫 50 道）：
- 问题类型分布预估：查表（直接查一个数）、计算（算一个 series 的统计）、匹配（找最早/最晚/最大/最小）、trend / growth（CAGR / 增长率）、多部分
- 答案形式：纯数、date（exact 格式）、bracketed list、单位 % 或 pp
- 共同陷阱：multi-period 修订、注脚 included-in-total、unit scaling、32nds、chart-only 页

**自动化**：如果 phase1 还要往下走，下一步是写一个零调用脚本把 50 道训练题按上述维度打标签，产出一个 YAML 特征档案给新 writer prompt。预估：100 行 Python + 1 小时时间。**没启动**——因为第 2 节的审计告诉我们"按 benchmark 特征生成"这条路可能救不了学习流程本身。

## 4 建议早上先决定什么

**核心悖论**：learned Skill 加的东西 **都是对的**（真·OfficeQA 领域知识），但在真题总平均上 **零增量**（跨 3 机复现）。两条路：

**路 A — 继续 phase1**：benchmark-feature-aware 生成器
- 风险：审计表明问题不在生成器，这条路可能是在"打磨不是瓶颈的那一环"。
- 若坚持做：下一步是训练题特征档案脚本（我已经预估了 1 小时，可以明天写）。

**路 B — 转向 "按 trick 命中率" 测量**（零调用+少量付费）
- 对每条 learned 加入的 trick（如 32nds、date 格式、multi-part）**人工打标签 50 道训练题**，看哪些 trick 的 trigger 在真题里出现几次
- 然后**按子集**测 learned−bzero：如果 32nds 的 8 道上 learned 显著强、其它 42 道上无差，那就是 "trick 对、但稀释" 的直接证据
- 零调用+可能一次小 bzero vs oq_s2 的子集重跑（已有数据，可以从封存记录直接切）
- 风险：确认但不解决——知道"稀释"后仍要决定 learning 流程怎么改

**路 C — 挑战假设："再多学一步"是不是方向错了**
- learning 流程产出一个"综合候选"替换 bzero；也许正确的流程是产出"**bzero 的增量条款**"，让 bzero 做核心、learning 只贡献边缘 trick
- 这是一个**流程层改动**，需要新的学习版本（v12），工作量大
- 不适合早上立即决定；但是零调用审计（第 2 节）已经给出了这条路的证据基础

**我的倾向**：先做路 B（1-2 小时零调用验证"稀释假说"），再回头判断 A 还是 C。但你是负责人，这是研究方向判断，不是我拍板。

## 5 跨数据集伤害结果（夜里补）

> **跑完我会把 summary 读完贴在这里**（Monitor 事件触发 → 本文件 §5 更新）。

- deepseek-v4-flash 上 OfficeQA Skill 应用到 SearchQA 的伤害（如果有）
- deepseek-v4-flash 上 SearchQA Skill 应用到 OfficeQA 的伤害（如果有）
- 与 10/14 20:50 的 GLM-5.3 条数据的跨模型复现 or 不复现

## 6 规则确认

- 没动 git（本次会话从 10/15 开始的所有改动都未 commit，包括本 memo）
- 没读 OfficeQA / SearchQA 测试集任何题
- 代码仍是 Codex 两轮 ACCEPTABLE 的 v3
- 封存记录都在新目录，没覆盖任何历史
- 若 cross-ds 探针报错或过慢，我在适当时机 kill 并记录到 §5

## 7 稀释假说验证（路 B 执行结果，02:10 完成）

**方法**：对 oq_s1 / oq_s2 相对 bzero 新加的 trick（T1 multistep、T2 multi-vintage、T3 chart、T4 rounding、T5 32nds、T6 indirect date、T9 pop vs sample、T10 multi-part）各写启发式 trigger 规则，对 74 道真题（50 train + 24 val）全部打标签，然后从**封存记录**里按 trick trigger 子集重算 learned−bzero（零调用，无新付费）。

**74 道真题 trick 命中频率**：T4 rounding 55、T2 multi-vintage 29、T1 multistep 16、T5 bond 9、T10 bracketed 7、T9 stddev 6、T6 date 3、T3 chart 3。

**稀释假说预测**：在 trick trigger 子集上 learned−bzero 显著正。

**实际数据**（跨 3 机 × 两份 learned × 8 个 trick slice，共 48 个 slice 对比）：

| trick | n | GLM-5.3 oq_s1 cell delta | glm-5.3-flash oq_s1 | deepseek oq_s1 | GLM-5.3 oq_s2 | flash oq_s2 | deepseek oq_s2 |
|---|---|---|---|---|---|---|---|
| **T9 pop vs sample stddev** | 6 | −1/12 | +1/9 | **+3/12** | +3/12 | +3/10 | **+2/11** |
| T1 multistep | 16 | −1/32 | −1/22 | +3/27 | +3/32 | +2/22 | +2/27 |
| T4 rounding | 55 | 0/110 | 0/87 | +5/101 | +5/110 | −2/88 | +1/98 |
| T10 bracketed | 7 | +3/14 | **−3/10** | +2/12 | +1/14 | **−5/9** | 0/12 |
| **T2 multi-vintage** | 29 | **−6/58** | 0/45 | 0/53 | −1/58 | −2/44 | −4/50 |
| T5 bond 32nds | 9 | +1/18 | 0/13 | −1/16 | −1/18 | −2/11 | −2/14 |
| T6 indirect date | 3 | 0/6 | 0/6 | 0/6 | −1/6 | 0/6 | 0/6 |
| T3 chart | 3 | 0/6 | 0/5 | 0/6 | 0/6 | −1/5 | −1/6 |
| **NONE_of_added** | 25 | — | 0/0 (bare noise) | — | — | — | — |

**读法（稀释假说验证的边界）**：
- **稀释假说不成立**（整体）：如果 learned 条款真的在其 trigger 子集上有效，应该每个 trick slice 都显示跨机一致的正。实际没有——绝大多数 slice 落在 ±2 cell 之内，样本噪声内。
- **T9（pop vs sample stddev）是唯一跨机一致正**：6 道题上三机都 +2/+3 cells（oq_s2），符合"添加 pop vs sample 约定"的预期——这是真能帮到小样本题的具体规则。
- **T2（multi-vintage）跨机一致中性或负**：尽管 learned 加了"prefer most recent issue"规则，29 道 multi-vintage 题上 learned 要么不帮要么微害（GLM-5.3 oq_s1 上 −6 cells 最明显）。假设：新加的规则**干扰了模型本已 OK 的默认行为**。
- **T10（bracketed multi-part）行为对立**：GLM-5.3 和 deepseek 上 oq_s1 为正；glm-5.3-flash 上 oq_s1/s2 都是负（−3、−5 cells）。模型族差异。
- **T4 rounding** 覆盖 55/74 道，learned 几乎零增量——"rounding compliance check" 这条规则 bzero 其实已经有了，重写一遍没用。
- **NONE_of_added**（25 道完全没有触发任何新 trick）：learned−bzero 跨机噪声内——这证实未命中集上无差别**不是**稀释，就是没差别。

**真正的信号（1 条）**：**T9 pop vs sample stddev**（6 道）：oq_s2 跨 3 机都在 trigger 子集上 +2/+3 cells。这是**一个** learned 条款在**合适子集上**真正带来可测收益的证据——证明"**条款级有用，整体稀释掩盖**"**在一个地方成立**，不是在所有地方成立。

## 8 优化方向：**条款级 ablation 门**（在当前流程基础上）

**问题诊断**（综合 §2、§7）：当前 learning 的"门"是**整体通过率**（候选 vs 父 Skill 在整个 panel 上）。候选是 bzero + 多条新加 trick 的集合体，整体门把"**T9 这条有用 + T2 这条有害 + 其它中性**"混在一起 → 整体零增量 → 候选被拒 → 实际有效的 T9 条款**也被丢弃**。

**优化思路**（不改研究流程主干，加一个辅助判定）：
1. **拆分**：把 learned 候选的"edits"每一条单独保留（analyst 原本就按 edits 列表输出），每条带其在训练 rollout 中观察到的 trigger 条件
2. **条款级 ablation**（零调用）：对每条 edit，构造"候选 = bzero + 这一条 edit"的虚拟 Skill（只需字符串拼接），**但不重新跑 solver**——而是**从训练 rollout 里按 trigger 子集的 bzero 行为与候选行为做对比**，衡量这条 edit 带来的净胜
3. **条款级门**（有付费）：对条款级 ablation 显示正号的 edit，构造"bzero + 该 edit"作为**窄候选**，在 generated gate 上单独过门
4. **合并**：所有通过的 edits 合并成最终候选（bzero + 挑选过的 edits），然后在**整体门**上再过一次复核

**风险 / 不确定**：
- 条款级 ablation 需要"**哪条 edit 适用于哪些 rollout 行**"的归因——analyst 的 reasoning 字段里有这个信息（10/10 的 memo 已经分析过）；若归因不清晰，退回到启发式 trigger（像 §7 做的那样）
- 窄候选的 token 开销：每条 edit 单独测 ≈ 原本 1 份 Skill 的开销 × N edits；若 N=5-10 条，成本放大 5-10 倍。但 **ablation 预筛**后真正过门的只有 2-3 条，付费开销可控
- 不改学习主干（反馈、analyst、decision）；只在"候选产出 → 门" 这一环中间插一个 **"edit 级过滤"**

**代码量预估**：
- 条款级 ablation 读数脚本：~150 行 Python，零调用；可以利用 §7 已经写好的 trick_slice_analysis.py 结构
- 窄候选门：复用现有 `scripts/run_fivebench_g_stage.py` 的门，仅需传不同的候选 Skill 文本
- Codex 审查：1-2 轮，没有新的接口
- 本机 + 开发机测试：复用 skillopt.feedback_study 的 fixture pattern

**早上建议第一步**：对 10/14 OfficeQA gv 阶段的 oq_s1/oq_s2 候选，用现有封存记录做一次**完整的条款级 ablation 回放**（零调用），输出"若把这条 edit 保留 → 整体 Skill 预估增益" 的表。再据此决定要不要写代码（新的"条款级门"模块）。

### 8.1 根据 §7 数据的具体 edit 保留/丢弃建议

| 条款 | n (trigger) | 跨 3 机信号 | 决定 |
|---|---|---|---|
| **T9 "population vs sample" std dev** | 6 | GLM +3, flash +3, deepseek +2（oq_s2） | **保留** —— 唯一跨机一致正 |
| T1 "multistep compute + 2nd route" | 16 | 混合（−1/+2/+3）；oq_s2 偏正 | 保留但观察（分母大、符号弱正） |
| T4 "rounding compliance check" | 55 | 跨机噪声内（±5 cells/110 known） | **丢弃** —— bzero 已覆盖，重写零增量 |
| **T2 "multi-vintage prefer latest"** | 29 | **跨机一致负或零**（GLM-5.3 oq_s1 −6）| **丢弃** —— 规则干扰了默认行为 |
| T10 "bracketed multi-part" | 7 | 对立：GLM/deepseek 正，flash −3/−5 | 保留格式部分，去掉解释部分；模型族风险 |
| T3 "chart-only" | 3 | 样本太小 | 保留（低频，无害） |
| T5 "32nds fractional" | 9 | 跨机一致微负 | **丢弃** —— trigger 启发式可能不准，规则本身也许正确但未触发 |
| T6 "indirect date language" | 3 | 噪声 | 保留（低频） |

**预测**：若 oq_s2 只保留 {T9, T10 格式部分, T1 弱保留}，其它丢弃，整体 Skill 相对 bzero 的真题增量**可能从 0 变成 +2～+4 cell/74**（点估计，样本小）。这不是显著收益，但方向明确；而且**这是现有流程零调用能做到的**，不需要重跑任何付费实验。

### 8.2 可以**今天就做**的下一步（都在"当前流程优化"范畴内）

1. ~~**条款级 ablation 回放**（零调用，1-2 小时）~~ **已做（§7）**
2. ~~**用保留的 edits 重构 "oq_s2_pruned"**~~ **已做**：`/root/fivebench-g-20261015-probe-skills/oq_s2_pruned.md`（4,476 B = bzero 2,936 B + T9 pop vs sample stddev 段落 + multi-part 一行；全部其它新加条款按 §8.1 建议丢弃）
3. **已 02:09 启动付费验证**（tmux `ae-prune`，deepseek-v4-flash，排队等 cross-ds 完）：三个 Skill `bzero / oq_s2 / oq_s2_pruned` 在同一 OfficeQA panel 上评测，1188 格、预计 ~45 分钟。结果写入 §10。
4. **若 oq_s2_pruned > oq_s2**：把"条款级 ablation + edit filter" 作为 learning v10 的 **新一步**（candidate → clause-ablation → filtered candidate → gate），写成新模块、Codex 审查、新协议版本
5. **若 oq_s2_pruned ≈ oq_s2**：假设否证，回到路 A 或 C

关键是：**这整条路都在用户 "当前流程基础上继续优化" 的授权范围内**，不是 C 的流程层改动，而是"候选 → 门"中间加一个过滤。

## 9 cross-ds 探针结果

### 9.1 OfficeQA Skills on SearchQA（02:09 完成）

| Skill（当前 panel） | pass rate (known) | 对比"SearchQA 自己 Skill" |
|---|---|---|
| empty | 257/335 = **0.767** | ≈ 之前 deepseek SearchQA empty 0.768 ✓ 无漂移 |
| **oq_s1**（OfficeQA 学到的） | 301/336 = **0.896** | SearchQA 自己的 qa_s1 = 0.899，差 0.3 pp |
| **oq_s2**（OfficeQA 学到的） | 300/336 = **0.893** | SearchQA 自己的 qa_v9 = 0.902，差 0.9 pp |

**配对**：empty vs oq_s1：3/31 (p=7.7e-07)，empty vs oq_s2：4/29 (p=1e-05)——OfficeQA Skill 在 SearchQA 上**大幅帮助**（+13 pp）；oq_s1 vs oq_s2：6/4 (p=0.75)，二者无差。

**读法**：
- **不是"伤害"而是"几乎 wash"**：deepseek 上 OfficeQA Skill 用到 SearchQA ≈ SearchQA 自己的 learned Skill（0.893-0.896 vs 0.899-0.902）
- 与之前 SearchQA 自己的 qa_bzero 0.917 相比，**跨数据集 Skill 比域内 bzero 低 2 pp**——这是"域内 bzero"的真实优势量级，不是 learning 本身
- 跟 10/14 20:50 的 GLM-5.3 数据对比（SearchQA 用别的数据集 Skill 害 −3 到 −8 pp）：**deepseek 的 cross-dataset tolerance 比 GLM-5.3 高**；"模型族依赖"再一次出现（如同生成题领先那条）
- 关键推论：**现在 OfficeQA 学到的 Skill 文本的通用部分（读题、用 context、exact format、concise）本身就能把 SearchQA 从 0.767 推到 0.896**——Skill 的大部分价值不是领域知识，是通用答题结构

### 9.2 SearchQA Skills on OfficeQA（03:59 完成）

| Skill | 生成题 124 (empty/qa_s1/qa_v9) | 真题 train 50 | 真题 val 24 |
|---|---|---|---|
| empty | 0.451 | 0.609 | 0.674 |
| **qa_s1**（SearchQA 学到的） | 0.679 (+22.8 pp) | 0.767 (+15.8 pp) | 0.833 (+15.9 pp) |
| **qa_v9**（SearchQA 学到的） | 0.663 | 0.800 (+19.1 pp) | 0.821 (+14.7 pp) |

**对比"OfficeQA 自己的 Skill"**（10/16 00:50 条数据，same deepseek-v4-flash OfficeQA panel）：
- oq_bzero: train 0.734 / val 0.773
- oq_s1: train 0.789 / val 0.786
- oq_s2: train 0.742 / val 0.800

**读法**（按 label 拆后）：
- **真题 train 50 道**：qa_v9 (SearchQA 学的) = **0.800** 实际上 ≈ oq_s2 (OfficeQA 学的 0.742) 甚至 > oq_bzero (OfficeQA 自己的 bzero 0.734)。扣除 ~3pp 跨 run 漂移后，qa_v9 大致和 oq_bzero/oq_s2 **持平或稍强**。
- **真题 val 24 道**：qa_s1 **0.833** 和 qa_v9 **0.821** 都和 oq_bzero (0.773) / oq_s2 (0.800) **持平或稍强**。
- 生成题上 SearchQA Skill 大幅帮助（+22 pp over empty），但仍低于 OfficeQA 自己的 oq_bzero (0.731)——这是预期：生成题要求 OfficeQA-specific 格式/算法规则（32nds、CAGR 等 bzero 本来就有的东西），qa_s1 Skill 不说这些。
- **56 unknown** 全是 finish_length，是 deepseek 对复杂真题推理超过 32K tokens。

**跟 10/14 20:50 的 GLM-5.3 比**：GLM-5.3 上 SearchQA Skill 用到 OfficeQA 是"不帮不害"；**deepseek 上更强，可能略有帮助**。这是**跨模型族的"no harm/mild help" 再次复现**。

**综合 §9.1 + §9.2 结论**：**跨数据集 Skill 没有伤害**（在 deepseek 上），有时甚至匹配域内 bzero——这意味着 **Skill 文本的主要价值是"**答题结构+格式+exact-match 约束**"的通用部分**，领域特定规则（32nds、Jeopardy 启发式）对整体 pass rate 贡献很小。这和 §2、§7 的审计（learned 加的具体 trick 真题零增量）**互相印证**。

## 10 剪枝验证探针结果（bzero / oq_s2 / oq_s2_pruned，05:51 完工）

**oq_s2_pruned 构造**：bzero 2,936 B + T9 pop-vs-sample stddev 段 + T10 multi-part 一行 = 4,476 B（剪掉 oq_s2 中其它 ~5,000 B 的 T2/T4/T5/T6 等条款）。详见 §8。

**结果**（deepseek-v4-flash OfficeQA panel，198 题 ×2 run，55 unknown）：

| | 生成题 124 (empty/bzero/oq_s2/oq_s2_pruned) | 真题 train 50 | 真题 val 24 |
|---|---|---|---|
| bzero | — / **0.740** / 0.814 / 0.722 | — / 0.733 / 0.778 / **0.787** | — / 0.780 / 0.738 / 0.721 |
| 配对（符号检验）| | | |
| bzero vs oq_s2 | 4/19 **p=0.003**（oq_s2 显著赢）| 2/5 p=0.45 | 1/1 p=1 |
| bzero vs oq_s2_pruned | 11/5 p=0.21 | 0/4 p=0.125（pruned 方向正）| 1/0 p=1 |
| oq_s2 vs oq_s2_pruned | 21/2 **p=6.6e-5**（oq_s2 显著赢）| 3/2 p=1 | 1/1 p=1 |

### 10.1 剪枝假说的两条路径

**(A) 真题路径（74 道）**：
- oq_s2_pruned ≈ oq_s2（3/2 p=1，差距 <1 pp）✓ **剪枝不损失真题性能**
- oq_s2_pruned 甚至在 train 上比 oq_s2 多一点点（0.787 vs 0.778）
- oq_s2_pruned 和 bzero 持平（0 better / 4 worse p=0.125 train；1/0 p=1 val）
→ **剪枝假说在真题上成立**：丢掉 T2/T4/T5 等条款不损失真题性能，symbol pruning 等于保留了"T9 这一条真正有用的"而丢掉了"无用+可能干扰"的其它条款。

**(B) 生成题路径（124 道）**：
- oq_s2 比 oq_s2_pruned 大幅赢（21/2，p=6.6e-5，差 9.2 pp = 0.814 vs 0.722）
- oq_s2_pruned 退化回 bzero 的生成题水平（0.722 vs 0.740）
→ **剪掉的条款在生成题上确实有效**：T2 multi-vintage、T5 32nds、T4 rounding compliance 这些规则**确实命中生成题的解法**，不是无用——是**只对生成题有用**。

### 10.2 关键推论

**这个结果比"剪枝假说简单成立"更有意思**：

1. **oq_s2 加的条款不是"错的"或"稀释"，而是"**只在生成题上有用**"**。
2. **生成题 ≠ 真题的证据再加一层**（跟 10/15 17:37、10/16 00:50 一致）：
   - 现在学习流程产出的 learned Skill 的"条款级价值" 几乎全部在生成题上兑现
   - 真题上这些条款零 marginal 收益
3. **"条款级门" 作为流程优化的 refinement**：
   - 原方案（§8.1）"用启发式 trigger 子集过滤 edits" 的目标应该修订为：**"把每条 edit 的生成题-vs-真题增量分开报告"**，而不是简单"丢弃负 edits"
   - 真正的瓶颈是**生成题偏差本身**——phase1 的 benchmark-feature-aware 生成器**不是无用**，它直接攻击"生成题门 → learned candidate 过门 → learned 条款只在生成题上有用" 这一链条
4. **更深的含义**（审慎表达）：**learning 的产出"看起来对（在生成题门上过了）→ 真题上零收益"** 可能不是 learning 的 bug，而是"**用生成题当门**" 本身在筛选"对生成题有用的条款"而不是"对真题有用的条款"。所以 phase1 和"条款级门"**是互补的**，不是二选一。

### 10.3 修订的建议路径

**不再推荐 "条款级门先行"**（§8 的旧建议）；改为：

1. **phase1 benchmark-feature-aware 生成器**：目标是让生成题的分布更贴真题，这样"过生成题门" ≈ "对真题有用"
2. 生成器改好之后**再加条款级 edit 分开报告**（generation-subset vs real-subset 的 learned−bzero 分别出）作为诊断工具，让 analyst/owner 看得见"这条 edit 只对生成题有用"
3. 跨数据集 "no harm"（§9）结果说明：Skill 的通用结构是主效应——phase1 生成器应该**保留通用答题结构**，只在"benchmark-specific"轴上加难度，这样生成的难题还能和真题可比

**可直接拿用的 artifacts**：`oq_s2_pruned.md` 作为"去掉 generated-only tricks" 版本保留；若将来有 real-only tricks 加进来可以增量叠加。
