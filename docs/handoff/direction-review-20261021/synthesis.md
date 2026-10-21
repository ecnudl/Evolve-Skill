# 后续方向怎么改：五份方案与十份审查的综合（2026-10-21，给负责人）

本文只读文件、未调用模型；[S数字] 见第 8 节来源表 [S63]。

## 1 一句话结论

先别实现、也别运行 v4（第 4 版协议：17 个 bug 修复加 7 项提示词改动），先做零花费的量尺修复；再花约 2,100–2,500 万 token（模型计费单位）做一次事先登记的决定性试验，问清"人写的任务卡（每个数据集一段的作答说明）之上还有没有 3–4 分以上可学"。有才继续做方法和迁移；没有就如实写成负结果，不再为"逐条规则过门"的进化链花钱。

## 2 证据说明了什么

1. 任务卡比空骨架（只有五个空标题的 Skill；Skill 指放进做题提示的文字）高，是测得出的大效果：cal-1（10/20 的标定实验，200 道 SearchQA 检索问答训练题、每题 4 次）里 +9.4 分 [5.05, 13.7]；但同类对比四次测得 +3.25 到 +16.2，随发送方式和评分器变，答案写法占三分之一到大部分。 [S1, S4, S5]
2. "任务卡之上再学"没有一处建立：v3（第 3 版正式运行，10/19–20，deepseek 做题）主链 I-ds（从任务卡出发）的 7 条规则在没见过的检查题上 −10.7 到 +0.5 分，ALFWorld（文字家务游戏）那条显著有害（−14.0）；GLM-5.3 做题、975 道新题上"学一步对零样本指令"+0.1 [−1.6, +1.8]。这是"未建立"不是"已证明没有"：足够多新题上事先登记的"任务卡+强规则包 对 任务卡"从没测过。 [S6–S9]
3. 逐条过门不适合作决策：v3 两条链 49 条提案收下 0 条；C1（每条规则只在 6–11 道触发题上与父版本比的第一道门）对 +9.4 分的整张任务卡也只放行 75.8%，属事先登记的"无法下结论"；"认不出 1–3 分规则"只来自模拟，cal-1 没有这么小的真实效果可校准。 [S2, S10, S11]
4. 量尺问题具体、可修、因数据集而异：严格评分器把 JSON（带花括号的结构化写法）答案全判错（0/364），但只伤空骨架一类的组；OfficeQA（财政公报计算问答）上同一文字换时段差 20 分以上，SearchQA 上任务卡跨天只差 −0.5；隔开发送无害，但同文本重跑仍有 8–10% 题翻转。 [S12–S16]
5. 迁移（目标二）没有能读的学习结果：v1（第 1 版，GLM 做题）的"迁移成功"几乎全是 OfficeQA 上的作答写法（任何 Skill 都 +19 到 +21）；v3 什么都没收下，相似方向的前向检查一次没跑；登记的相似关系全指向题最少的 OfficeQA（74 道训练题）。 [S17–S19]
6. 验证端（目标一）没有正面证据：模型写的判卷程序接近瞎猜（平衡准确率 0.47–0.55），生成题太容易；9 月同思路的 V 系列（验证端编码细则）V4 零次晋升、V16 零次新检出；"出题方钻评分漏洞"一说则已被推翻。 [S22–S25]

## 3 方向调整：停什么、留什么、改什么

**停**
- v4：它保留逐条过门、不做整版验收，已有规则加在任务卡上最多 +1.5 分。不是因为花费："11.6 亿"是 GLM 总封顶，照 v3 跑一轮实际约 1.5–2.5 亿。 [S7, S27–S29]
- 新的五数据集逐条过门链；用生成题或模型写的检查程序当门或证据。 [S22, S23]
- 全量迁移矩阵（约 2.9–5.2 亿，成功机会约 5.5%）；用相似数据集训练题"只否决"（变相验证集）。 [S30, S31]
- 夜间判"不值得"的五个方向：案例记忆、失败记录提炼成规则替换任务卡、部分得分当门、自动出题当验证端、换做题模型（要重跑基线约 1.7 亿）。 [S32]
- "学"LiveMath（数学选择题）的"更强结论"选项：按设计它就是被替换的正确答案。 [S33]

**留**
- v3、cal-1 的冻结结果与"0 收下"结论；任务卡作起点和参照；同时段逐题交错、至少两段安慰剂（等长无关文字）、每组记答案标签率；测试集冻结后经同意只读一次；相似关系表（"预测不了迁移"是缺证据，不是反证）。 [S43, S50, S64]
- ALFWorld 先零花费补完 D14（没写完的 ALFWorld 探索）的结果表再定。 [S53]

**改**
- 决策单位改为"整版在没用过的新题上一次验收，同时与任务卡、安慰剂比"，每批新题只用一次（夜间 D1 方向提出，未经审查）。 [S55, S62]
- 评分器加"也认 JSON"，登记为新版本，只作事后重读与并列报告。 [S13]
- 先做便宜的决定性试验，再定是否花 3,700–8,600 万做量尺标定或方法工程；费用按实际回执（接口返回的用量）计，上限按账本（正式记账）的 2 倍设——cal-1 账本 2,748 万、回执 1,400 万。 [S3, S36, S65]

## 4 接下来按顺序做的事

**第 0 步 收尾与登记**（目的：让第 1 步可登记、可复核；做题 0 token，约一个会话）
① 登记评分器 v2，事后重读 cal-1 与 v3 训练格；② 列清每道训练题的使用记录；③ 本机写新抽题脚本，从 SearchQA 原始题源（约 1.1 万道没抽过）抽 800 道，排除以前的 A–D 四块、训练池与测试题，只核题号；④ 两个独立的强模型各据 cal-1 训练错题写一份"内容包"（只讲检索与推理、不点名题目，≤600 字节），另写"写法包"（只讲作答写法）和两段等长安慰剂，冻结哈希；⑤ 补完 D14、更正状态页过时说法；⑥ 一轮 Codex（外部代码评审）审查。抽不出干净新题就退回 v3 没用过的 369 道×2 次（310 道被试跑用过，只能分辨约 3–4.5 分）。 [S39, S40]

**第 1 步 决定性试验**（目的：任务卡之上有没有 3–4 分以上可学；一夜）
- 做法：800 道新题×1 次，7 组同时段逐题交错：空骨架（只查有效性）、任务卡、任务卡分别加内容包甲、内容包乙、写法包、安慰剂一、安慰剂二；另 100 题重复任务卡作诊断；沿用 v3 冻结的做题提示。
- 费用：每格（一道题作答一次）任务卡大小约 4.0–4.8 千（实测 3,995–4,669），空骨架约 1,240；合计约 2,100–2,500 万实际 token，账本上限 5,000 万；约 6.5 小时，限流时 8–12 小时。 [S37, S38, S66]
- 判定（事先写死；官方评分为主、JSON 评分并报；两份内容包做 Holm 多重比较校正）：
  - 有效：某内容包比任务卡 ≥+3 分、校正后下界 >0，且比两段安慰剂平均下界也 >0。
  - 无效：两份内容包比任务卡的上界都 <+3。官方无效而 JSON 有效，记"内容或许有用、写法有害"，仍算无效。
  - 未分辨（其余）：补测一块 800 题（任务卡、未分辨的包、两段安慰剂，约 1,300–1,900 万），按时段分层合并再判；仍未分辨记"低于约 4 分分辨不了"，不记无效。
  - 有效性（否则重跑）：JSON 评分下任务卡比空骨架 ≥+2 且下界 >0，派发机械检查通过。
  - 把握（同类规则模拟）：误判有效约 1–2%；真实 +3 分约一半判有效（补测后约六成），+4 分 92–97%。 [S41, S42, S44]
- 改方向：有效→第 2 步；否则→第 3 步乙路。写法包有效、内容包无效＝量尺没问题，是任务卡之上没内容可学。

**第 2 步 项目自己的提规则环节学不学得到**（仅当第 1 步有效）
另抽 800 题×1 次，比任务卡、加胜出包、加项目环节写的包（按错误类别提问的新写法，事先冻结）、两段安慰剂；约 1,600–1,950 万，GLM ≤100 万。胜出包复现且项目包比任务卡 ≥+2、下界 >0 → 经您裁定（第 7 节第 6 条）后做精简 v5（下一版：只在 SearchQA 上学，每批新题只决定一次）；项目包不行 → 离线改提规则环节（每轮 ≤200 万）；胜出包不复现 → 按无效处理。 [S52, S66]

**第 3 步 分两路**
- 甲路（v5 收下了版本；目的：给目标二读数）：冻结后经您同意，在测试集上同时段交错各读一次，带任务卡与安慰剂，约 5,200–5,700 万（ALFWorld 占 2,800–3,100 万）；v1 测试已打开过，读数有适应性，要注明；自身提升不成立就转乙路。 [S48, S50]
- 乙路（目的：如实收尾）：零做题费用写成负结果与测量报告；若还想找余量大的地方，做新数据集预筛（如 FinQA 财报计算题：300 题×1 次，任务卡、加写法包、加交叉写的内容包，每个候选约 130–160 万，内容包 ≥+3 且下界 >0 才移植）；都不过就收束文字规则路线。 [S49]

## 5 两个目标怎么办

**目标一（Skill 与验证端评分细则协同进化）** [S58]：没有正面证据，上面四步也给不了它正面结果。建议本轮不作主线，由您拍板；若要保留，只做一个以标准答案为锚的小试验：验证端只进化"答案格式与题目有效性"的检查代码，按能否预测事先冻结的评分标签、能否检出一种没见过的人为埋错来收，每轮换新打分题、固定误拒率、不拿做题分数当奖励，GLM 约 60–150 万。先验偏低；成功也只说明检查程序在进步，不等于 Skill 变好。 [S24, S26, S56]

**目标二（一个数据集上进化、其余评测、不用验证集）**：没有可读的学习结果。SearchQA 是唯一有足够新题当来源的数据集；它唯一的相似目标 OfficeQA 只有 74 道训练题（已被反复用作开发题 [S59]）和 172 道测试题，每题 1 次只能分辨约 6.6–7.7 分，所以"相似也涨"只能描述；"不相似不掉分"只能写成"排除了大于约 7–11 分的下降"。唯一能测到约 2 分的方向是 OfficeQA 上学、到 SearchQA 封存的 C、D 两块（2,000 题）评测，前提是 OfficeQA 上先学得出东西。建议：第 1、2 步都过了才为它花钱；规则标明"通用"或"仅本数据集"，通用的须过"不改答案格式"的代码检查（放在 SearchQA 小节里的规则对别的数据集不起作用）。 [S20, S21, S60, S61]

## 6 五位策略员的分歧与取舍

- 瓶颈：量尺派（量尺、迁移）、没余量派（止损、论文）、单位与来源派（方法）。证据都不硬：事后给每题挑最好的文字也只多 +2.75 [0.6, 5.5]，实质余量却估约 6 分。第 1 步用写法包测量尺、内容包测余量，一次分开。 [S45, S46]
- 来源：四位选 SearchQA，方法派选 FinQA。先 SearchQA：唯一能一夜分辨 3–4 分、不用新协议；FinQA 要新协议和新评分，手写专家说明对任务卡 0.0，留作乙路候选。 [S47]
- 先大标定（3,700–8,600 万）还是先试验：采纳两份审查"先试验"的建议；200–400 万的更小试验只能看出 3.5–4 分以上、题也被用过，所以直接做 800 题版。 [S65]
- 比哪段文字：论文派用 v3 原规则，止损派用强模型事后写的包，方法、迁移派用项目环节。先用强模型包当"上限探针"（v3 规则在任务卡上已测得 0 到 +1.5 分），第 2 步再测项目环节。 [S7]
- 安慰剂是否在任务卡上测过：两位审查员说测过，一位说没有；核对 D1 报告，测的是只含 SearchQA 一段的说明，五段任务卡上没测过，所以第 1 步自带安慰剂组。 [S34, S35]
- LiveMath 是否并入第 1 步（止损派主张）：不并，无特殊选项的 154 题已被反复用过，只能看出 5–6 分以上。 [S54]
- 目标一去留（方法派留，论文、止损派停）、论文是否作交付、新题批算不算验证集：交您决定。

## 7 需要负责人决定的事

1. 是否同意停止实现和运行 v4（需要的 bug 修复带进新版本）。
2. 是否把"也认 JSON"的评分器登记为新版本（v4 待决事项 (d)）。
3. 是否批准在本机抽 800 道没抽过的 SearchQA 新题作新登记的块（补测、第 2 步各再要 800 道）。
4. 是否允许用两个强模型事后写的规则包当"上限探针"，用哪两个。
5. 预算：第 1 步账本上限 5,000 万（实际约 2,100–2,500 万），补测、第 2 步各自登记上限，碰上限不自动续跑。
6. "每批新题只用一次的整版验收"算不算您说的验证集（决定 v5 能否建）。
7. 目标一：本轮暂停，还是花 60–150 万 GLM 做那个小试验。
8. 第 1 步若无效，是否以负结果与测量报告作交付（等于改研究目标）；它与第 3 步甲路不能共用同一次测试读取。 [S51, S57]
9. LiveMath 任务卡是否写明"更强结论"选项的含义（含它的 129 道训练题里它全是答案），写了也不算"学到"。
10. 是否打开 v3 的测试分数（两条学习链增益按构造为 0）。

## 8 事实来源表

路径约定：仓库根 `/Users/dulin/Documents/Paper/SkillOpt/`；FS = `docs/handoff/feasibility-20261021/`；RL = `docs/results-and-lessons.md`；PS = `docs/project-status.md`；SP = `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/direction/`（方案在 SP`proposals/`，审查在 SP`critiques/`）。证据类型：实跑＝真实模型运行；回放＝对存档的重读；模拟＝统计模拟；未审＝探索方向未经反方审查。

| 编号 | 事实 | 来源（文件：行/节/字段） | 类型 |
|---|---|---|---|
| S1 | cal-1：任务卡（ids-full）比空骨架 +0.0938［0.0505, 0.137］，48 升 13 降；11 段文字×200 题×4 次 | docs/handoff/cal1-registration-20261020.md L36–47、L137 | 实跑（训练题） |
| S2 | C1 在 n=11 时对 ids-full 通过 75.8%（n=6/20 时 47.9%/99.0%）；50–80% 为“无法下结论”；“没有规则大小的真实效果可校准” | cal1-registration L74–84、L139–140、L148–152 | 实跑＋登记读法 |
| S3 | cal-1 账本 27,481,897；实际回执约 14.0M（计费 17.6M）；超 25M 上限暂停 | cal1-registration L113–117、L128–131；FS E7/critic-result.json refuted_claims #8 | 实跑记账 |
| S4 | 同一“任务卡对空骨架”四次测量：v3 单臂 +3.25（不显著）、cal-1 +9.4、E5 新题 +8.9、D1 新题 +16.2 | SP critiques/stoploss-evidence.md R3（引 FS E6/critic-result.json R3） | 实跑/回放 |
| S5 | 宽松（认别名）评分下任务卡仍 +6.1［+2.6, +9.8］，约三分之一是写法；写法占比三分之一到全部，视评分而定 | FS E10/critic-result.json confirmed_claims、R6；SP critiques/method-evidence.md §6 #7；stoploss-evidence.md R4 | 回放 |
| S6 | v3 I-ds 7 条规则在没见过的检查半题上 −0.107 到 +0.005 | FS D1/report.md §5.3；FS D1/result.json evidence | 回放（未审方向的回放，审查员复核） |
| S7 | v3 规则加在任务卡上：SearchQA +0.000/+0.004/+0.015；ALFWorld −0.140［−0.254, −0.035］ | FS D9/result.json evidence E；FS D9/critic-result.json confirmed_claims | 回放 |
| S8 | GLM-5.3，975 道新题：lz−bzero +0.001［−0.016, +0.018］，缺失界［−0.031, +0.032］，登记为“缺失条件下未分辨”；lh−bhand +0.049（bhand 读过学到的 Skill 后手写） | RL L222 | 实跑（新题） |
| S9 | 10/12：在通用指令上再学一步 +2.9［−1.1, +7.2］；“这是‘未建立’，不是‘已证明没有’” | RL L139 | 实跑（开发池反复使用） |
| S10 | v3 漏斗 I-ds 24→10→6→1→0→0、E-ds 25→18→9→1→0→0，0/49；deepseek 139,024,462，GLM 7,804,250；测试分未开 | RL L142；PS §0 | 实跑 |
| S11 | “每步检出 0.19–0.26”来自 D8 模拟；cal-1 没测出“认不出 1–3 分” | FS D8/result.json recommendation；SP critiques/instrument-evidence.md §F #4 | 模拟 |
| S12 | 官方评分下 JSON 格式回复 0/364 通过 | FS D5/critic-result.json #1（经 SP critiques/instrument-feasibility.md §10 #17） | 回放 |
| S13 | I-ds 回复带标签率 1.000、ids-full 0.999；JSON 评分下 E-ds s1-r1 初筛 +0.75→+13.75 题、复核 −2.50→+12.25，但内容复述任务卡；v3“0 收下”不变 | FS E7/critic-result.json refuted_claims #1；SP critiques/paper-feasibility.md §9 #14 | 回放 |
| S14 | OfficeQA：同一文字同 74 题跨时段 +20.3；v3 的 9 个 OfficeQA 单元 8 个处于“只给答案”状态；同 60 题四时段标准差 11.4（空骨架 1.3）；跨时段 22–24 分 | FS E9/critic-result.json R4；FS D12/result.json evidence；FS D11/result.json | 回放/实跑 |
| S15 | SearchQA 任务卡跨天 −0.5［−2.8, +1.6］；简短/啰嗦时段只差 +0.25 | FS E4/critic-result.json R7；FS D11/critic-result.json #9 | 回放 |
| S16 | 隔开发送：任务卡组反而翻转更多（10.4% 对 6.4%）；同文本翻转底噪 8–10% 不变 | FS E4/critic-result.json R2；SP critiques/method-evidence.md §6 #4 | 回放 |
| S17 | v1 测试（10/19 经同意打开）：OfficeQA 上指令 +20.3、SkillOpt +20.9、GEPA +19.2、E +20.3，“是作答写法的作用，不是学到的迁移” | RL L173 | 实跑（测试集） |
| S18 | 相似关系：SearchQA–OfficeQA、OfficeQA–LiveMath、OfficeQA–SpreadsheetBench；ALFWorld 与谁都不相似（10/17 负责人确认） | PS §5（10/17 条）；docs/handoff/coevo5-registration-v6-20261017.md L69–72 | 登记 |
| S19 | 题池：SearchQA 600/400，OfficeQA 74/172，LiveMath 283/125，SpreadsheetBench 120/279，ALFWorld 57/134 | coevo5-registration-v6-20261017.md L84–88 | 登记 |
| S20 | 测试集每题 1 次的最小可测差：SearchQA 4–5、OfficeQA 6.6–7.7、LiveMath 10–11、SpreadsheetBench 7–7.7、ALFWorld 9–10 | FS D5/critic-result.json missing #4；SP critiques/stoploss-feasibility.md §7 #14 | 计算 |
| S21 | SearchQA 封存 C、D 两块共 2,000 题，作评测目标时最小可测约 1.5–1.9 分 | SP critiques/stoploss-feasibility.md §7 #14 | 计算 |
| S22 | 模型写的判卷程序平衡准确率 0.47–0.55，6 次改进 0 次通过；23 道生成题 20 道两组都全对 | FS E1/result.json；FS E1/critic-result.json notes_cn | 实跑（小规模） |
| S23 | 仿 OfficeQA 生成题空白说明就答对约 89% | FS E9（经 SP critiques/transfer-evidence.md §5 #2） | 实跑 |
| S24 | 9 月 V 系列：V4 零次晋升、V16 自然新增检错为 0 | FS E10/critic-result.json R7、missing #2；docs/current-workflow.md L388 | 历史实跑 |
| S25 | “只求更难的出题方钻了评分漏洞”被推翻：逐字过滤器挡住了，变差的是有锚定的方针 | FS E10/critic-result.json R3；SP critiques/transfer-evidence.md §5 #2 | 回放 |
| S26 | 按分数改细则（DecoEvo 式）15 格中 13 格更差 | FS E1/critic-result.json missing #1 | 文献/回放 |
| S27 | v4 规格：不改 C1–C4′ 门槛，“整版新题验收”明确不做；B7 只对齐格式判定，不是 JSON 评分修复 | docs/handoff/v4-plans-20261021/spec.md L69–73、L177–178 | 规格 |
| S28 | 11.6 亿＝GLM 总封顶（OVERALL_CEILING）；v3 GLM 正式 7,804,250＋开跑前 1,433,782；“v3 十步共用 7.8M” | docs/handoff/v4-plans-20261021/G4.v2.md L1842–1846、L2050–2052 | 规格 |
| S29 | v4 照 v3 跑一轮实际约 1.5–2.5 亿（方法可行性审查）/约 1.9–2.3 亿（止损可行性审查） | SP critiques/method-feasibility.md §6 #1；SP critiques/stoploss-feasibility.md §7 #8 | 估算 |
| S30 | 全量迁移矩阵 E2：最小一行约 2.9 亿、QA 方案约 5.2 亿，联合成功约 5.5% | FS E2/critic-result.json notes_cn；SP critiques/stoploss-feasibility.md §8 | 估算 |
| S31 | 用相似数据集训练题“只否决”＝变相验证集，且用掉唯一的相似目标 | FS E9/critic-result.json R1；FS D12/result.json recommendation 3 | 审查结论 |
| S32 | 不值得的方向：D2（案例记忆，−1.0［−6, +4］）、E8（失败记录提炼成规则替换任务卡）、E6（部分得分当门）、E1（验证端自动出题）、E7（换 flash 做题，需重跑基线约 1.7 亿） | docs/handoff/overnight-report-20261021.md L53；FS D2/critic-result.json；FS E7/critic-result.json；SP critiques/instrument-feasibility.md §10 #19 | 实跑/估算 |
| S33 | LiveMath“更强结论”选项在含它的 129/129 道训练题里都是正确答案；基准论文称它替换掉正确答案 | PS §5（10/21 两问）；FS D7/critic-result.json | 回放/文献 |
| S34 | D1 试跑的 S 组＝空骨架＋SearchQA 一段说明（＝cal-1 seed-only，2,442 字节），不是五段任务卡；安慰剂 0.000/−0.023、副本 +0.004、S−E +0.162 | FS D1/report.md L168–171、L447–449；SP critiques/paper-feasibility.md §9 #1 | 实跑（未审） |
| S35 | cal-1 中 seed-only − ids-full −0.005［−0.036, +0.026］ | FS D1/report.md L157 | 回放 |
| S36 | D1 试跑 1,560 格，账本 2,388,219＝回执，每格 1,531 | FS D1/report.md L449–451 | 实跑（未审） |
| S37 | 每格 token：SearchQA 任务卡 v3 实测 4,088、E5 3,995、cal-1 ids-full 4,669；空骨架 1,236 | FS D6/critic-result.json（v3 入口训练格）；FS E5/result.json cost_estimate；SP critiques/transfer-evidence.md §5 #6 | 实跑 |
| S38 | 6 路并发约每小时 880 格 | FS D1/result.json risks #10 | 实跑 |
| S39 | SearchQA 原始 validation 划分 16,980 题，已抽 4,000（A–D 块），约剩 1.1 万；现有抽题脚本不能排除旧块，新块须本机、只核题号、负责人签字 | SP critiques/stoploss-feasibility.md §7 #6；scripts/make_searchqa_fresh_sample.py L114–121 | 核对 |
| S40 | 600 道训练题里从没用过的最多 59 道；v3 没用过的 369 道里 310 道被 D1、E5 试跑用过；退回方案可分辨约 2.8–3.7 分，加 Holm 校正与安慰剂条件约 3.5–4.5 分 | FS E5/critic-result.json missing #7；SP critiques/paper-feasibility.md §9 #2、#7 | 核对/计算 |
| S41 | 判定规则把握：真实 +3 第一轮约 0.50、补测后约 0.63；+4 为 0.92–0.97；真实 0 误判有效 0.013–0.018 | SP critiques/stoploss-feasibility.md §1.2；SP critiques/stoploss-evidence.md F2 | 模拟 |
| S42 | 800 题×1 次：95% 半宽 1.7–2.1（嘈杂时 2.3），80% 把握最小可测 2.4–3.0（3.3），Holm 两项 2.6–3.3 | SP critiques/stoploss-feasibility.md §1.1 | 计算 |
| S43 | 至少 2–3 段安慰剂、比平均；逐字副本只作诊断（约 5% 必然误报） | SP critiques/stoploss-evidence.md F4、F5；FS E2/critic-result.json R6；FS D11/critic-result.json #7 | 审查结论 |
| S44 | 参照：止损方案 4 组补测约 1,350–1,390 万、基础 4 组 1,840–1,930 万；补测须按时段分层合并、单独登记上限（本文的组数不同，重算见 S66） | SP critiques/stoploss-feasibility.md §7 #3–5、§8 | 估算 |
| S45 | 事后在 11 段文字里给每题挑最好的：+2.75［0.6, 5.5］；“任务卡之上 0–3 分上限”未建立 | FS D9/result.json evidence D；FS D9/critic-result.json refuted #1 | 回放 |
| S46 | SearchQA 实质余量约 6 分（止损方案自己的数） | SP critiques/stoploss-evidence.md F6；SP proposals/stoploss.md §1 | 估算 |
| S47 | FinQA：官方按执行程序比数（5 位小数），6,251 题中 3,508 题答案带百分号；手写专家说明对任务卡 0.0；接入需新协议 | SP critiques/method-feasibility.md §6 #8、#13；SP critiques/method-evidence.md §6 #9（FS E3/critic-result.json） | 核对/实跑 |
| S48 | 一个冻结版本的测试读取（同时段交错、带任务卡与安慰剂）：不含 ALFWorld 2,400–2,600 万，ALFWorld 134 局×2 组 2,800–3,100 万 | SP critiques/instrument-feasibility.md §10 #18(b) | 估算 |
| S49 | 新数据集预筛：300 题×1 次×3 组，每候选约 130–160 万；“≥+3 且下界>0”在真实 +5 时把握 82–92%；须分写法包与内容包、交叉拟合 | SP proposals/stoploss.md Exp 4；SP critiques/stoploss-feasibility.md §7 #20 | 估算 |
| S50 | v1 测试 10/19 已打开；v3 测试分已算未开；PS 中“测试集未读”已过时 | RL L173；PS L118–119、§5；SP critiques/stoploss-evidence.md R12 | 核对 |
| S51 | 测量论文服务不了两个目标，采用与否由负责人定 | FS D10/critic-result.json R13；SP critiques/stoploss-evidence.md R14 | 审查结论 |
| S52 | D13：“旧规则失败主因是效果太小，提示词改不了”；按错误类别提问的新写法从没在做题模型上跑过 | FS D13/critic-result.json notes_cn；SP critiques/stoploss-feasibility.md §3 #4 | 回放 |
| S53 | D14 未写完（结论与结果表为占位符）；目标物 55/57 局在开放台面；v3 里任务卡是唯一测得出动 ALFWorld 的文字（+0.105） | FS D14/report.md L8、L67–69、L76–78、L194–222 | 回放（未审） |
| S54 | LiveMath 无特殊选项 154 题已被多方用过；只能判出约 5–6 分以上 | SP critiques/stoploss-feasibility.md §1.3；SP critiques/stoploss-evidence.md F7 | 计算 |
| S55 | D1、D12、D14 未经反方审查 | docs/handoff/overnight-report-20261021.md L72–97（6.5 表） | 核对 |
| S56 | 目标一的小试验设计：只进化答案格式检查、按预测冻结标签收；或埋错留出类型、固定误拒、每轮换打分题；GLM 约 60–150 万（依据 E1 实测 86 万、E6 132 万） | SP critiques/transfer-feasibility.md §5 #14；SP critiques/method-feasibility.md §6 #17；SP proposals/method.md M3 | 设计/估算 |
| S57 | 测量论文会用掉唯一一次测试读取，与迁移读数冲突，须二选一 | SP critiques/transfer-evidence.md §5 #21 | 审查结论 |
| S58 | 负责人两个目标原话（10/20）：“1. 协同进化，skill进化，验证端coding rubric进化 2 评测指标是泛化性……必须还是要在一个bench上进化，然后其余bench上评测” | SP brief.md | 原话 |
| S59 | OfficeQA 74 道训练题已被四个试跑反复用过，实际上是开发集 | FS E2/critic-result.json missing #7（经 SP critiques/instrument-evidence.md §F #10） | 核对 |
| S60 | 放在 SearchQA 小节的规则对别的数据集按设计不起作用；规则须标“通用/仅本数据集”，通用的过“不改答案格式”检查 | SP critiques/transfer-feasibility.md §5 #18；SP critiques/paper-feasibility.md §9 #15 | 审查结论 |
| S61 | 唯一能测约 2 分的迁移方向：OfficeQA 上学、SearchQA 封存 C/D 上评测 | SP critiques/stoploss-feasibility.md §7 #14 | 计算 |
| S62 | 同一批验收题跨多次决定复用＝事实上的固定验证集；赢家诅咒 1.34–1.51 倍 | FS D8/critic-result.json R4；SP critiques/instrument-feasibility.md §10 #5–6 | 审查结论 |
| S63 | 本文输入：五份方案与十份审查，十份审查都判“需修订”（needs_revision） | SP proposals/*.md；SP critiques/*.md 各文件 Verdict 行 | 核对 |
| S64 | “登记的相似数据集对没用”是缺证据，不是反证，相似关系表应保留 | FS E4/critic-result.json R4；SP critiques/instrument-evidence.md §E | 审查结论 |
| S65 | 大标定费用：迁移方案 T1 实际约 3,700–4,600 万；量尺方案 S1–S4 合计约 7,600–8,600 万；量尺可行性审查建议的小试验 200–400 万（3 组 250–300 题×1 次约 340–410 万，只能分辨约 3.5–4 分）；迁移可行性审查建议先做 SearchQA 小标定 | SP critiques/transfer-feasibility.md §5 #1、#8；SP critiques/instrument-feasibility.md §10 #4、#19 | 估算 |
| S66 | 本文重算（按 S37、S38）：第 1 步＝800×(3,995–4,669)＋4,000×(4,145–4,819)＋800×1,236＋100×(3,995–4,669)≈2,116–2,447 万，共 5,700 格÷每小时 880 格≈6.5 小时；补测 4–5 组≈1,314–1,916 万；第 2 步 5 组 4,000 格≈1,646–1,916 万；“加包约 +150”为≤600 字节包的估计 | 本文计算 | 计算 |
