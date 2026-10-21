# 终审核对：synthesis.md（2026-10-21）

结论：**ok = false**。主体建议（不实现 v4、先修评分、先做一次 SearchQA 上"任务卡＋事后包 对 任务卡"的试验）有来源支撑，算术也核对无误。但有 17 处需要改正，另有 11 项漏掉的内容。最要紧的五处如下。
- 第 3 节"不值得的方向"清单与夜间汇报原文不符（C1）。
- "放在 SearchQA 小节里的规则对别的数据集不起作用"与实测相反（C2）。
- 第 1 步无效的含义被推广成"任务卡之上没东西可学"（C3）。
- 975 道题研究的负结果被说软了（C5）。
- 已测到的负迁移没有写（C6）。

核对方式：只读文件，未调用模型，未连任何机器，未打开测试池。路径约定沿用 synthesis 第 8 节：仓库根 `/Users/dulin/Documents/Paper/SkillOpt/`；FS = `docs/handoff/feasibility-20261021/`；RL = `docs/results-and-lessons.md`；PS = `docs/project-status.md`；SP = 本目录。

---

## 一、需要改正的地方（按严重程度排序）

### C1　§3"停"第 4 条与 S32：夜间"不值得"的方向清单
- **问题**：与来源不符。
  - 夜间汇报 L53 与 RL L146 (5) 的"明确不建议"共六项：案例记忆（D2）、用适用条件挑题（D4）、部分得分进门槛（E6）、让模型写判卷程序（E1）、现在换 flash 做题（E7 审查）、把登记的相似对当泛化尺子（E4）。
  - 本文删了 D4 和 E4，加进了不在清单上的 E8，并把 E1 写成"自动出题当验证端"。但 E1 实测失败的是"模型写判卷程序"（FS E1/result.json verdict_cn 一："'会写代码的判卷员'不可行"；二："代码真正有用的地方在出题一侧"）。"自动出题"那半（E1-X）恰恰是夜间汇报推荐的第③项（L53："③ 目的一的判定实验 E1-X（约 310 万 token）"）。
  - E8 审查原话："证据只能说明'提炼出的规则替代不了任务卡'，说明不了'热启动不值得做'"（FS E8/critic-result.json notes_cn 第 2 条）。
- **改法**：见结构化输出 C1 的 fix_cn。要点：列六项原文，每项附一句白话；E8 单列为"替换不行，'加在任务卡上'没测过，第 1 步正是测这个"；E1-X 的去留单独说明理由。
- **来源**：overnight-report-20261021.md L53、L66；RL L146；FS E1/result.json verdict_cn；FS E1/critic-result.json refuted R13、notes_cn 四；FS E8/critic-result.json notes_cn 2。

### C2　§5 目标二括号与 S60："放在 SearchQA 小节里的规则对别的数据集不起作用"
- **问题**：把设计意图当成了事实，而实测结果相反。
  - E9 实测：LiveMath 的说明放在它自己的小节里（加在空骨架上），OfficeQA 仍掉 9.5 分（另一时段 −8.1）；SearchQA 的说明放在自己的小节里，OfficeQA 掉 4–7 分（不显著）。原话："即使这段文字写在别的基准的小节里也一样……每条规则都要做这个检查，不能只查标成'相似'的规则"。
  - v1（第 1 版，GLM 做题）期中分析 §3.12：SpreadsheetBench 的 r2、r4 两条规则进入 Skill 后，OfficeQA 60 道回归题里分别有 4、5 个回答没写答案标签。
  - 保留意见：测到的伤害都是整张任务卡加在空骨架上的结果。规则大小的文字加在五段任务卡上会不会渗，还没测过（FS E9/critic-result.json R3）。
  - "inert by design" 只是 E7 审查 missing 里的一句断言，未经实测。
- **来源**：feasibility-exploration-20261021-cn.md L116、L127；FS E9/result.json verdict_cn 1、recommendation（"Apply the guard to every rule, not only `similar` ones, since local text bleeds into other benchmarks"）；coevo5-midrun-analysis-20261019.md L355–357；FS E9/critic-result.json R3；SP critiques/transfer-evidence.md R2。

### C3　第 1 步无效的含义被推广
涉及四处：§4"改方向"末句、§4 乙路"都不过就收束文字规则路线"、§1"没有就如实写成负结果"、§1/§6"决定性试验""上限探针"。
- **问题**：
  - 止损方案与审查都写明：无效只说明"这两份事后包在 SearchQA 上没带来 ≥3 分"，不能说明"任务卡之上没东西可学"，也不支持五个数据集全停（SP critiques/stoploss-evidence.md F6；SP proposals/stoploss.md L73："a null bounds rule-shaped text, not all text"）。
  - OfficeQA（任务卡只答对 25–29%）和 ALFWorld（D14 提出按状态条件写的规则）都没测。
  - 第 1 步对真实 +3 分只有约 50%、补测后约 63% 的把握（SP critiques/stoploss-feasibility.md §7 #2），称"决定性"言过其实。
- **来源**：同上；FS D14/report.md L67–69。

### C4　§6 第 1 条"第 1 步用写法包测量尺、内容包测余量，一次分开"
- **问题**：审查原话是："F 包相对任务卡的区间下界不大于 0，只说明任务卡已经管住了写法，不能说明量尺看不见规则大小的效果"。审查建议另加一段已知会伤分的短文字（如"只写姓"）当灵敏度对照，约 330 万（SP critiques/stoploss-feasibility.md §7 #11）。现设计做不到"一次分开"。

### C5　§2 第 2 条：975 道题的负结果被说软了
- **问题**："这是'未建立'不是'已证明没有'"出自 10/12 那条（RL L139），不是 975 道题这条。
  - RL L222 的读法是："'从任务经验学习'相对一份不看任何任务结果的零样本指令的增量为0±2个百分点"。只因缺失结果的最坏界 +0.032 略超 +0.03，才按规则登记为"缺失条件下未分辨"。
  - 同一批题上，用验证集把关的 SkillOpt v9 也只有 +0.010 [−0.005, +0.026]。
  - 止损方案 §1.3 也写："For GLM the 975-item result bounds it near 2 points (missing-result bound 3.2)"。
  - "零样本指令"一词未解释。

### C6　§2 第 5 条（迁移）漏了已测到的负迁移
- 以下均为 GLM 做题：
  - RL L206：OfficeQA、LiveMath 上学到的 Skill 搬到 SearchQA，比零样本指令低 −7.2 / −8.4 / −8.0；lm_z41 低 −63.6（把"只答选项字母"带了过去）。
  - RL L209：搬到 OfficeQA 为 −5.4 到 −1.4，区间都含 0。
  - RL L173：v1 的 GEPA 文字让 SpreadsheetBench 比空白低 −7.8 [−15.3, −0.5]。
  - overnight L63、FS E2/result.json：只在 SearchQA 学出的文字，在 SpreadsheetBench 上比任务卡低 13–17 分，四个目标平均比任务卡低 3–4 分。
- 换 deepseek 做题后，互换 Skill 不害（RL L181）。
- 见 SP critiques/transfer-evidence.md R1。

### C7　§5 目标二："唯一能测约 2 分的方向是 OfficeQA 上学……前提是 OfficeQA 上先学得出东西"
- **问题**：没说这个前提几乎不可能满足。
  - OfficeQA 当来源只够学 1 步，只能认出 10–15 分以上的规则（FS E2/critic-result.json notes_cn 三.3）。
  - 一条真实 +5 分的规则过关的机会约 0.19（FS E9/critic-result.json R1）。
  - 同一文字换时段差 20.3 分（R4）。

### C8　§3"停"第 3 条与 S30："全量迁移矩阵（约 2.9–5.2 亿）"
- **问题**：数字对应的方案配错了。
  - 2.9 亿是"最小一行"，5.2 亿是"三个问答来源"，都是审查重算值。
  - 五个来源的全表按探索者自己算约 15.7 亿；要达到方案声称的分辨力需要约 11–20 亿。
  - 5.5% 是在真实效果"相似目标 +2、自身 +4、链间差异 1 分"时的联合成功率。
- **来源**：FS E2/result.json（"五个来源的全表约 15.7 亿"）；FS E2/critic-result.json notes_cn 三.1–2、refuted 中的把握表；overnight L63。

### C9　§6"先大标定（3,700–8,600 万）"与 §3"改"第 3 条
- **问题**：8,600 万不是标定费。
  - 量尺方案 S1–S4 全套约 7,600–8,600 万计费（账本约 1.18–1.34 亿），其中含 S3 学习阶段（约 3,100 万＋GLM 300 万）和 S4 迁移读数（约 1,450 万）。
  - 标定部分只有 S1（约 930 万）加 S2（约 1,970 万），约 2,900 万。
  - 迁移方案的标定 T1 约 3,700–4,600 万。
- **来源**：SP proposals/instrument.md L69、L74、L80、L84；SP critiques/instrument-feasibility.md L132、L398；SP critiques/transfer-feasibility.md L58。

### C10　§4 第 1 步"费用"与 §3"上限按账本的 2 倍设"
- **问题**：
  1. 3,995 是 E5 试跑的实际平均（FS E5/result.json cost_estimate），4,669 是 cal-1 的计费平均（FS E9/critic-result.json R6：来自 cal-1 TSV 的 'charged' 列）。两者被混写成"实际 token"。
  2. "上限按账本的 2 倍设"字面意思是"账本×2"，原意是"上限＝实际用量估计×约 2"。cal-1 实际 1,400 万、计费 1,760 万、账本 2,748 万；没返回用量的请求按约 15 万预扣（SP critiques/paper-feasibility.md §9 #6）。
  3. "限流时 8–12 小时"是止损方案约 4,500 格的估计（stoploss-feasibility L235、L307）。本方案 5,700 格应约 10–16 小时，可能跨过一夜。

### C11　§4 第 1 步"有效性（否则重跑）"
- **问题**：
  - 审查要求另加一个事先定好的"只答一句"回答比例允许范围，本文没有采纳（SP critiques/paper-feasibility.md §9 #5）。
  - "否则重跑"与"已开始的付费运行永不自动续跑"冲突（PS L126），应改为经负责人同意。
  - "派发机械检查"一词未解释。

### C12　§4 第 2 步"胜出包不复现 → 按无效处理"
- **问题**：
  - 胜出包的测得效果会被高估 1.34–1.51 倍。这是 D1 的模拟结果（FS D1/result.json evidence），D1 方向未经审查。
  - 第 2 步复现的把握约 0.65–0.85，即一个真实 +2.5 分的包有 15–35% 机会复现失败（SP critiques/stoploss-feasibility.md §1.5）。
  - 应记为"未复现"，不记"无效"。

### C13　§4 第 0 步 ①④
- ① cal-1 续跑部分（attempt-2）的数据只在老机器上（RL L144："attempt-2 只在老机器"；overnight L26、L141），要先拷到新机器。
- ④ 写包用的强模型费用没写，止损方案估 ≤100 万（SP proposals/stoploss.md Exp 0）。
- ④ 两段安慰剂没说与哪个包等长（stoploss-feasibility §7 #11）。

### C14　§2 第 1 条与 S4："四次测得 +3.25 到 +16.2"
- **问题**：+16.2 来自 D1 试跑，比的是只含 SearchQA 一段的说明（seed-only，2,442 字节），不是五段任务卡（FS D1/report.md L447–449），与本文自己的 S34 矛盾。cal-1 里两者在 SearchQA 上只差 −0.5（D1 report L157），可以并列，但要注明这一点和"未经审查"。

### C15　§3"停"第 1 条"最多 +1.5 分"，以及 §6 同类说法
- **问题**：0 / +0.4 / +1.5 都是点估计，区间上端分别到 +3.6、+2.6、+4.4。面板含规则自己的证据题，结果偏乐观（FS D9/result.json evidence E）。

### C16　§6 末条"目标一去留（方法派留，论文、止损派停）"
- **问题**：量尺方案（instrument.md L95）和迁移方案（transfer.md L98）也主张暂缓。实际是四份暂缓、一份保留。

### C17　术语没解释
| 出现位置 | 没解释的术语 |
|---|---|
| §2.6 | V4、V16（与本文 v4 同名易混） |
| §2.2 | 零样本指令 |
| §4 第 1 步 | Holm 校正、派发机械检查 |
| §4 第 0 步 | A–D 四块 |
| §3"改" | D1 方向 |
| §2.4 | 隔开发送 |
| §6 | 策略员、量尺派、没余量派、单位与来源派 |
| §7 #2 | (d) |
| §8 表 | E-ds、s1-r1、lz、lh、bzero、bhand、S−E、B7、C2–C4′、OVERALL_CEILING、DecoEvo、赢家诅咒 |

每一项的白话注释见结构化输出 C17。

---

## 二、漏掉的内容
1. **明说预期结果**：按现有证据，第 1 步最可能的结果是"无效"或"未分辨"。
   - 证据：
     - 已有规则加在任务卡上只有 0 到 +1.5 分；
     - 事后为每题挑最好的现成文字只多 +2.75 分 [0.6, 5.5]；
     - GLM 上学一步只多 +0.1 分；
     - "实质余量约 6 分"这个数，出自一位 AI 审查员读 54 道题的判断；
     - 止损方案的默认假设是 0–2 分，但在 deepseek 上只排除了 5 分以上。
   - 由此，两个目标大概率都推进不了。只有第 1 步判为有效，目标二才开始；而且先得到的也只是 SearchQA 内部的证据。
   - 来源：FS D9/result.json evidence D/E、FS D9/critic-result.json、SP critiques/instrument-evidence.md A9、SP proposals/stoploss.md §1.3、SP critiques/stoploss-feasibility.md §7 #23。
2. **服务时段与回答状态的监测**（五份方案都提到；见 stoploss-feasibility §7 #13、paper-feasibility §9 #8、FS E2/critic-result.json missing #4、FS E8/critic-result.json notes_cn 4）：
   - 每组都记答案标签率、JSON 格式率和回复长度；
   - 按"只答一句"和"详细作答"两种状态分层报告，状态只按任务卡组的回答判定；
   - 结论加一句"只在这一个服务时段测得"。
3. **OfficeQA 的任何读数都要在两个时段各读一次**，按回答状态分层，并预先指定"边算边写"状态为主读数（FS E9/critic-result.json R4；FS D11/result.json evidence C 与 risks；SP critiques/transfer-feasibility.md L161–162）。
4. **E1-X 的去留理由**：夜间汇报推荐过 E1-X。论文方案的可行性审查认为，加了对照的 E1-X 约需 600–800 万，是目标一最便宜的直接试验，比较对象须为"任务卡加候选规则 对 任务卡"。本文改推另一个小试验，但没说为什么不选 E1-X（SP critiques/paper-feasibility.md L284–292、L519–524；FS E1/critic-result.json R5、R6、R13）。
5. **目标一小试验还缺三条**（SP critiques/method-feasibility.md §6 #17；FS E1/critic-result.json missing 1）：
   - 检查程序不得读取标准答案和标准程序；
   - 另报对真实坏题（非人为埋错）的检出；
   - 直说这只是验证端的单边进化，不是协同进化。
6. **LiveMath 的读数要分层**：有"更强结论"选项的题与没有的题分开报。去掉这类题后，测试题约剩 68 道（SP critiques/transfer-feasibility.md L171–172）。
7. **"不相似的不掉分"应登记成合并的不劣检验**：LiveMath 与 SpreadsheetBench 合并后，可测的允许下降约 4–5 分；单个数据集只能排除 7–11 分以上的下降（SP critiques/transfer-feasibility.md L168–170；SP proposals/transfer.md L18、L43）。
8. **零花费的现成读数**：v1、v3 里每条过了初筛的规则，都在之前数据集的回归面板（60 题×1 次）上与父版本比过，但从没当迁移数据分析过。可以零成本重读，只作描述（SP critiques/transfer-evidence.md R2）。
9. **对比方法缺口**：GEPA、SkillOpt 两个对比方法只在 GLM-5.3 上跑过，deepseek 上没有，即使成功也无法与现有方法比较；原登记估计重跑约 1.7 亿（FS E7/critic-result.json missing；SP critiques/transfer-feasibility.md L173–175）。
10. **DeepResearch 角色的对应**：负责人限定 DeepResearch 只做一件事，即看过训练结果后写更好的生成题或规则文字。本计划应写明两点：
    - 第 1 步的内容包和第 2 步项目自己写的包，承担"写更好的规则文字"这一半；
    - "写更好的生成题"这一半暂停，因为生成题太容易，生成题上的增益在真题上归零（SP brief.md；RL L197；FS E9/result.json verdict_cn 2）。
11. **Skill 使用说明要统一**：第 1 步与之后的 v5 要用同一句"Skill 使用说明"（沿用 v3 原句，或采用 v4 的 B13/P7 新句："只照适用条件匹配的小节去做"）。这句话决定了别的小节会不会渗；否则第 1 步测出的结果不能直接搬到 v5（docs/handoff/v4-plans-20261021/spec.md L99–102；SP critiques/transfer-evidence.md §5 #12）。

---

## 三、已核对无误的部分（不需改）
- **第 1 步算术**：5,700 格；低端 800×3,995＋4,000×4,145＋800×1,236＋100×3,995＝21,164,300；高端＝24,466,900；5,700÷880≈6.5 小时。
- **补测**：4 组 1,314 万到 5 组 1,916 万。
- **第 2 步**：1,646–1,916 万。
- **甲路**：2,400–2,600 万＋2,800–3,100 万。
- **乙路**：每候选 130–160 万。
- **目标一小试验**：GLM 60–150 万，依据 E1 实测 86 万、E6 实测 132 万。
- **账本上限 5,000 万**：高端 2,447 万×1.96≈4,796 万，在上限内但余量很薄。
- **来源表逐条核对一致**：
  - S1–S3、S8 的数值、S9、S10、S12、S13、S15–S20、S22–S25；
  - S27（spec L177–178："Out of scope for v4 (explicitly NOT to implement): fresh-batch version-level acceptance, changes to C1-C4' thresholds"）；
  - S33–S38（D1 report L157、L447–451）、S39、S40、S41、S42、S45、S47、S53（D14 report）、S55、S58、S63、S66。
- **S62**：赢家诅咒数字实为 D1 的模拟结果，经 instrument-feasibility 转引，可接受。
