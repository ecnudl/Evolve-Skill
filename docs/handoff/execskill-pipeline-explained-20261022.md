# 路线 B 管线详解：可执行技能与考官协同进化（fivebench-execskill-v1）

2026-10-22，代码与登记稿逐条核对；读法说明：这是上半部分（第 0 节到 5.3 节），下半部分从工程师改包（5.4）讲到验收、测试读取、预算、冒烟和试点。每节按「设置（在哪、为什么）→ 做法 → 输入/输出 → 上限与调用 → 现状 → 代码入口」排列。括号里是出处：「登记稿 §x」指 `docs/handoff/execskill-registration-v1-20261021.md`，「裁定」指 `execskill-registrar-decisions-20261022.md`，「计算稿 Tn」指零调用算术输出 `execskill-calc-output-20261021.txt`，`xxx.py` 指 dl 机器构建树 `/data/execskill-dev/skillopt/execskill/` 里的文件。代码今天还在被改，所以引用常量名或函数名，少引行号。核对由六份阅读笔记逐条对照代码和登记稿完成，本文据此整理，并在 14 点半后对关键常量重新抽查过一遍。「未核实」表示我没能确认；「正在修（工单号）」表示这块代码此刻正在改，写的是登记的目标行为。文中所有数字都是设计、上限或估计，不是实验结果。

## 0 三十秒版本

```
  S0 准备（零调用：给代码拍快照、造题池、排除测试题、检查表格引擎和隔离箱、钉住清单）
        │
        ▼
  冒烟（在新接口上花小钱做真实调用；做题只用链 D 的模型）
        S0 零调用汇总 → S1 接口探针 → S2 做题 ∥ S3 角色 → S-E6 成本外推 → 汇总
        │   冒烟通过就直接开试点（主人 10/22 13:2x 已授权，不用再等一句“开”）
        ▼
  试点：两条链各跑各的，账本分开，题目消耗账也分开
        链 D：做题模型 deepseek-v4.1-flash-1017      链 G：做题模型 glm-5.3
        每条链都是：第 1 步 SB（表格题） ──►  第 2 步 OQ（报表问答题）
        每一步的八个小步（从父包 S 出发，可能得到候选包 S'）：
          5.1 跑题 → 5.2 考官诊断 → 5.3 考官出题（必须先查证）
          → 5.4 工程师改包 → 5.5 自测（5.4 和 5.5 最多各两轮）
          → 5.6 验收（一批新题只判一次）→ 5.7 冻结，传给下一步
          → 5.8 读测试集（试点里不在每步读，挪到整条链最后读一次）
        │   每条链走完两步后各自读一次（要主人亲手写的读取同意书 shared/consent.json，15:01 已写好；
        │   一条链若什么也没收下，最终包就等于空包，这条链不读，记 not_read）
        ▼
  测试读取：五个题库的测试集一次性读完，多组对照；分数先封存
        → 两条链都结束后，主人只看学习侧记录决定继续或停止 → 解封 → 读数报告
```

1. 我们不再把「技能」写成一段提示文字，而是写成一个包：里面最多 24 个小 Python 程序（叫「过程」）。做题模型每次作答前后，固定的外壳程序（叫「壳」）在断网、只读的 Docker 容器（叫「隔离箱」）里运行这些过程，把它们从题面里摘出的数字、表格、提醒，或者表格程序的试跑报告，当作便条递给做题模型；答案仍由做题模型自己给。
2. 每一步里，工程师模型读当前包在「跑题段」上的失败记录，最多改三处，得到候选包；考官模型同时写「失败检测器」，并且先查证、再出生成题。两个角色都用 GLM-5.3，一起进化。
3. 候选包只在一批本路线从没用过的新题（叫「验收段」）上判一次。它要同时赢过旧包，也赢过「长度和位置一样、内容无关」的安慰剂，故障率和格式也不能变坏，否则丢弃。整个路线没有可以反复使用的验证集。
4. 试点只走两步（SB 再 OQ）。链 G 和链 D 用同一套切题方式各跑一遍，所以两条链是复现，不是两份独立证据。
5. 每条链走完后才读一次测试集（要主人书面同意；什么也没收下的链不读），分数封存到两条链都结束、主人只凭学习侧记录决定继续还是停止之后才解封；那才是泛化证据，验收只是挑选证据。登记稿事先写明，最可能的结果是两步都什么也没收下。

**现状。** 到本次核对时（10/22 下午）：主人的排除同意书（09:18）和测试读取同意书（15:01）都已写好；零调用检查和几次「用完即弃」的演练跑过；冒烟、试点、测试读取一次都还没跑。各模块都有单元测试；14:10 登记的第 7、8、9、17 行已由构建员 P2C 补完代码和针对性测试；随后 P2C 在 dl 上跑完全套 route-B 单元测试（`tests/test_execskill_*.py`）：1,183 项通过，用时 824 秒，退出码 0，含故意破坏条目 1–55（P2C 进度笔记；笔记自标 16:4x，但文件实际写于 15:44，自标时间是估计）。还没有任何一步在真实数据上跑过。

### 0.1 代号速查（本文第一次出现时也会就地解释）

| 代号 | 白话意思 | 详见 |
|---|---|---|
| 过程（procedure） | 一个小 Python 模块（≤ 6,000 字节），只能实现下面 6 个钩子中的若干个 | 3.1 |
| 钩子（hook） | 壳在固定时机调用的函数名，一共 6 个，名单封闭 | 3.2 |
| 包（package） | 若干过程加一个顺序（≤ 24 个），就是被学习的「技能」 | 3.3 |
| 壳（shell） | 固定不学的外壳代码：路由、调用钩子、拼请求、调用做题模型、处理第二次调用 | 3.4 |
| 隔离箱（sandbox） | 断网、只读、无权限的 Docker 容器，过程只在里面运行 | 3.8 |
| 任务卡（card） | 从 v3 冻结下来的每个题库一段说明文字，放在系统提示里，永不学习 | 3.9 |
| 链 G / 链 D | 两条并行的完整流水线，只有做题模型不同：G 用 glm-5.3，D 用 deepseek-v4.1-flash-1017 | 2.3 |
| SB / OQ / LM / SQ / ALF | 五个题库：SpreadsheetBench 表格题、OfficeQA 报表问答、LiveMath 数学选择题、SearchQA 检索问答、ALFWorld 文字家务环境 | 2.5 |
| 跑题段（run slice） | 每步开头用当前包去做的一批训练题，用来产生失败记录 | 2.6、5.1 |
| 验收段（acceptance slice） | 每步结尾用来判候选包的一批新题，只用一次 | 2.6 |
| 格（cell） | 一道题 × 一个组 × 第几次运行 = 一次完整作答及其记录 | 3.10 |
| 组（arm） | 同一批题用不同的包去做，每种包是一个组 | 下面几行 |
| S | 父包：这一步开始时的当前包 | 5.1 |
| S' | 候选包：工程师改出来的新包 | 下半部分 |
| C | 只有任务卡、一个过程都没有的空包组 | 5.1 |
| S_dup | S 的一份完全相同的拷贝，再跑一遍，用来看「同一个包两次跑分是否一致」 | 下半部分 |
| P_y | 配对安慰剂：改动过的过程照常出现，但便条内容换成它在别的题（供体）上产生的内容，长度对齐 | 下半部分 |
| P_i | 无关文字安慰剂：便条换成无关文字，只做描述，不参与决定 | 下半部分 |
| 供体（donor） | 给 P_y 提供便条内容的旧题，取自父包 S 在跑题段上的作答记录 | 下半部分 |
| 孪生格（twin） | 「拿掉/放回」某一个过程再做一遍：`withhold:<p>` 拿掉过程 p，`restore:<p>` 把被删的 p 放回，用来算单个过程的作用 | 下半部分 |
| A / A* | A = 验收段的全部题；A* = 其中被改动的过程会被触发的题。只有 A* 会被真正发出去、记为用掉 | 2.6 |
| G_self / G_acc | 考官生成题的两半：G_self 给自测用，G_acc 在验收时用来检验生成题能否预测真题 | 5.3 |
| J1–J7 | 验收的七条判定规则。例如 J1：S' 和 S 逐题成对比较要统计上显著（单侧配对 t 检验 p ≤ 0.05；配对安慰剂明显有害时改为 0.025），并且全批至少高 2 分 | 下半部分 |
| 账本（ledger） | 记录每次调用预留和实际花费 token 的记账系统，碰到上限就暂停 | 2.3、5.1 |
| 作用域（scope） | 账本里的一个子账户（例如 `G:solver`），各有上限，一次调用要同时记进好几个 | 5.1 |
| 单元（unit） | 一个小步在磁盘上的工作目录：加锁、按次尝试、结果只写一次 | 5.0 |
| attempt | 单元的第 N 次尝试，目录 `attempt-N`，最多 3 次 | 5.0 |
| 消耗账 | 每道训练题被哪条链、为了什么用掉的登记簿，只增不改 | 4.12 |
| F | 一条链走完两步后的最终包；什么也没收下时 F 就是空包 C（记作 F = C），这条链不读测试集 | 4.13、下半部分 |
| C7b1、I1、OPS1、P2-A1、P2-A2、P2C | 构建阶段各个构建员（写代码、做演练的代理）或构建步骤的代号；它们的笔记在 `docs/handoff/execskill-build-20261021/notes/` | 2.8 |
| 工单（ticket） | 登记员或构建员开出的一项待改事项，编号如 `PR-C61-2`、`C7b1-3`、`P2C-1` | 2.8 |
| D2、D3、D14 | 10/20–21 夜里的可行性试跑编号（D3、D14 是 ALFWorld 试跑）；D3 的轨迹被 S0 拿来做回放检查 | 4.3、4.11 |

代码入口：`scripts/run_execskill.py`（命令行总入口）；`skillopt/execskill/runcli.py:run` → `chain.py:run_manifest` → `chain.py:run`（一条链）；`step.py:UNITS`（一步的单元顺序）。

## 1 我们要解决什么、核心想法

**设置。** 这一节不对应某个命令，讲的是整条路线为什么这样设计。依据是登记稿第 0、2、4、7 节和主人 10/21 的两次定调：16:4x 批准路线 B；22:3x 定下三条规则 (a)(b)(c)。(a) 32 项待定事项全按默认值；(b) 考官出题必须先查证；(c) 做题用两个模型，分成两条链。

### 1.1 为什么把技能改成能运行的程序包

- **前一条路线失败在哪。** 前一条路线是 v3 五题库协同进化，10/20 结束，技能写成文字规则。结果两条链一条规则也没收下。更麻烦的是，同一段文字原样重跑一遍，194 道题里就有 30 道对错翻转：测量本身的噪声，比任何一条规则的净效果都大。
- **格式错误吃掉了一半提案。** v3 工程师的 49 个提案里，有 21 个死于小格式错误（登记稿 §4.2）。所以新工程师的回复格式固定为「一个 `` ```json `` 清单块 + 每条过程一个 `` ```python `` 块」。
- **文字只能劝，程序能做。** 文字规则只能劝模型，听不听说不准。程序能做确定的事：从题面逐字摘出数字；用分数做精确计算；在公开的输入表格上先把模型写的程序试跑一遍，把报错告诉模型。
- **程序不能替模型答题。** 壳根本没有「改最终回答、改格式要求、替模型选动作」的接口（登记稿 §2.1「结构性保证」）。改写模型输出属于「答案修补」，不算学到的技能（AGENTS.md）。
- **过程能做的事是一张封闭清单**（登记稿 §0 第 1 条、§2.1）：
  - 往提示里加一段整理好的信息，叫便条；
  - 从题面抽带名字的数字，让模型可以要求精确计算，最多多问模型一次；
  - 表格题看了试跑报告，可以请求一次修改调用；
  - ALFWorld 里把某些动作标成「不建议」，只标注，不删除。

### 1.2 工程师和考官一起进化

| 角色 | 谁扮演 | 每一步做什么 | 怎样才算「进化成功」 |
|---|---|---|---|
| 工程师 | GLM-5.3 | 读失败记录，最多改 3 处（新增、修订、撤掉、缩小范围），得到候选包 S' | S' 在验收段上被收下（J1–J7，见下半部分） |
| 考官 | GLM-5.3 | 写「失败检测器」（5.2）；先查证、再写出题规格（5.3） | 有检测器被接受，或有出题程序被证明「生成题上的好坏能预测真题上的好坏」（登记稿 §7.2） |

- **两边都有改不动的锚**：参考答案、模拟器、固定代码算出的真值（登记稿 §0 第 2 条）。
- **考官一侧事先写好的诚实预期**（登记稿 §0 第 6 条、§7.2）：
  - 试点题量下，失败检测器在 SB、OQ 上大概率「无法判定」；
  - 出题程序的预测效度要至少 8 轮验收才能检验，试点每个题库只有 1 轮，所以会写「无法评估」（代码里叫 `not_evaluable`）。
  - 因此试点不可能证明考官进化成功，报告也不会这样写。

### 1.3 出题之前必须先查证

- **规则。** 主人 10/21 22:3x 的规则 (b)：协同进化的宗旨不改。考官出题的路径里必须有一步查证；没有合格的查证发现，就不出题（登记稿 §0、§7.2、§21）。
- **查证机器沿用 v3 冻结的那一套**：
  - 来源：固定参数的英文维基百科接口，加上开跑前按 SHA-256 钉死的文档存档（Python 3.11、openpyxl、LibreOffice Calc 帮助页和公开任务卡）；
  - 查证员由 GLM-5.3 扮演；每个请求最多 3 轮，每轮 3 个检索词，最多读 3 页，最多 8 次调用；
  - 引文必须逐字出现在存档页面里。
- **查证只给素材和参数，不给答案。** 每道生成题的真值都由固定代码算出。
- **理由一：考官自己算答案不可靠。** v3 那种做法，冒烟时 9 道题只有 4 道合格；v1、v2 冒烟分别是 12 道里 9 道、10 道（登记稿 §0 (b)）。
- **理由二：生成题的分数从没预测过真题。** E1 生成题上 +13，真题上 0；E9 在 0.891 饱和，却漏掉了真实的 −9.5（登记稿 §5.5）。所以生成题永远不当验收标准，在试点里也不当筛子。

### 1.4 没有可反复使用的验证集：挑选证据与泛化证据

- **一个候选只判一次。** 判它用的是一批本路线没用过的训练题，叫验收段。真正发出去的那些题（A*）从此记为用掉，同一条链不再用（登记稿 §0 第 3 条、§3）。
- **「没用过」只指本路线没用过。** SB 和 OQ 的题以前都被别的方法反复用过；登记稿 §3.1 的表显示，两种口径下真正没碰过的都是 0 道。
- **所以验收给的是挑选证据**：「这个版本在本路线没用过的训练题上胜过父版本」。它不是独立的泛化证据。泛化证据只来自最后的测试读取（这句措辞是主人决定 #31）。
- **测试分数不许影响任何决定。** 继续还是停止，只看学习侧记录（下半部分第 8 节）。
- **每条结果记录都带证据标签 `evidence`**，取值有四种：
  - `engineering_fixture`：工程夹具，人造的测试题和测试过程，永远不算学到的技能；
  - `smoke`：冒烟；
  - `pilot_real_run`：试点真实运行；
  - `historical_replay`：历史回放。

### 1.5 一步的总输入和总输出

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 输入：父包 S | 上一步 5.7 冻结的包；第 1 步是空包 `empty(step="<chain>/s0")`；存 `<chain root>/packages/<sha>.json` | `parent_sha256, procedures（过程哈希）, order（过程编号顺序）, retired, narrowed, step, describer` |
| 输入：本步的两段题 | 按固定顺序从题池切出（2.6）；存 `<chain root>/s<k>-<bench>/slices.json` | `{chain, k, bench, slices: {run: [题号], accept: [题号]}}`，只写一次 |
| 输入：冻结的任务卡与格式句 | S0 导入（4.6），`$PRE/texts/texts.json`；清单里钉死 | 每个题库一张卡，只给当前题库那一张 |
| 输出：下一步的父包 | 5.7 冻结 | 收下：S'（加每条新过程的冻结文字说明）；没收：S 原样传下去，S' 存档 |
| 输出：9 个单元目录 | `<chain root>/s<k>-<bench>/<unit>/`（5.0 的表） | 每个单元一个只写一次的 `unit.json` |
| 输出：消耗账新行 | `/data/execskill-history/consumption/<G 或 D>/<bench>.jsonl`（4.12） | 每道被用掉的题一行，只增不改 |
| 输出：账本流水 | `<run root>/shared/ledger-<chain>` | 每次调用的预留与结算 |

`slices.json` 的骨架（字段名是真的，值是占位）：

```json
{"chain": "G", "k": 1, "bench": "spreadsheetbench",
 "slices": {"accept": ["spreadsheetbench/<id>", "..."], "run": ["spreadsheetbench/<id>", "..."]},
 "version": "fivebench-execskill-v1-step-slices", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

每条记录都盖同一种章：`version = "fivebench-execskill-v1-<种类>"`、`evidence`（证据标签），以及 `record_sha256`（去掉这个字段后，对规范化 JSON 算的 sha256）。记录只写一次，重跑时只读回来核对，不覆盖。

### 1.6 事先登记的预期（不是结果）

- **最可能的结果**（登记稿 §0 第 4 条、§11）：两步都什么也不收；考官一侧「无法判断」；迁移「分不出来」。
- **把握有多大。** 一条真实 +5 分的改进被收下的机会，SB 约 0.17，OQ 约 0.24。如果两步的真实效果都是 +5 分，默认试点两步都不收的概率约 0.63（各种假设组合下 0.27–0.82；登记稿 §0 第 4 条、§6.6）。
- **认得出多大的提高。** 登记的最小可检测提高：SB 12.1 分，OQ 10.0 分（`protocol.py` 的 `MDE_POINTS`，联合把握 80%）。
- **名义 5% 的检验在偏斜分布下会多收**（计算稿 T9）：30 道题时实际误收率 12.3%（Codex 给的偏斜零假设），「平局多、偶尔大跌」的分布下最高约 16%；150 道题时降到 5.9%–8.1%。
- **以上全是事先算好的估计**，用来提醒「什么都没收下」不等于「过程没用」，只等于「这个题量认不出」。

**上限与调用。** 每步（每条链）登记的做题上限，按跑题 / 考官 / 自测 / 验收四块（`protocol.py` 的 `STEP_CAPS`）：

| 题库 | 跑题 | 考官 | 自测 | 验收 | 合计 |
|---|---|---|---|---|---|
| SB | 1.2M | 3.5M | 2.6M | 8.3M | 15.6M |
| OQ | 2.3M | 7.3M | 6.6M | 29.5M | 45.7M |

方法角色每步的上限（`ROLE_CAPS`）：工程师 1.5M，考官 2.5M，查证 4.6M。单位是账本 token，「M」= 一百万。账本按预留记账，比实际花费高（2.3 节）。

**现状。** 这一节全是设计。到 10/22 14 点半，没有任何一步在真实数据上跑过，也没有任何一个过程被收下。

代码入口：`protocol.py`（全部登记常量：`SLICES`、`STEP_CAPS`、`ROLE_CAPS`、`MDE_POINTS`、`HOOKS`）；`step.py:UNITS`、`step.py:_slices`；`package.py:empty`。

## 2 全局：机器、目录、两条链、角色、题池

**设置。** 所有东西都在 dl 开发机上跑。这台机器是主人 10/20 迁过去的；Mac 上只放拉回来的代码镜像，用来做 Codex 审查和发布到 GitHub（登记稿 §1）。这一节把「在哪跑、谁在跑、用哪些题」一次讲清楚，后面各节只引用这里。

### 2.1 机器与解释器

- **机器。** 15 GiB 内存，7 个 CPU（裁定 A5-1；登记稿 §2.6）。C7b1 实测可用内存 11,089,964 KiB，S0 内存守卫按它的 70% 算，见 4.11。
- **代码在哪写。** 构建树 `/data/execskill-dev`：git 克隆，分支 `research/exec-skill-coevolution`，起点提交 010d453。单元测试也在这里跑，离线，用假后端。
- **解释器。** `/root/continual-alf-prep-20260928/env/bin/python`（3.11.16），每次都加 `-B` 和 `PYTHONDONTWRITEBYTECODE=1`：以前试跑时，曾往快照里写进 9 个 `.pyc` 文件（登记稿 §1）。
- **SearchQA 补充题的解释器。** 生成它要读 Hugging Face 缓存，所以单用工具环境 `/data/execskill-tools/hfenv/bin/python`，并且离线运行。

### 2.2 目录

| 名称（`protocol.py` 常量） | 路径 | 放什么 |
|---|---|---|
| `BUILD_TREE` | `/data/execskill-dev` | 构建树：写代码、跑单元测试 |
| `SNAPSHOT_ROOT` | `/data/execskill-20261021-source` | 代码快照。从构建树复制而来，不带 `.env*`、`.git`、`__pycache__`，之后不再改；正式运行只用它 |
| `OPS_ROOT` | `/data/execskill-20261021-ops` | 运维记录 |
| `PRE_ROOT`（下文写 `$PRE`） | `/data/execskill-20261021-pre` | 准备阶段的产物：S0 记录、夹具、题池视图、任务卡 |
| `SMOKE_ROOT` | `$PRE/smoke` | 冒烟的运行根目录，账本单独一本；主人的排除同意书 `shared/exclusion-consent.json` 也在这里 |
| `PROBE_ROOT` | `$PRE/probe` | S1 接口探针，账本 `$PRE/probe/ledger` |
| `PILOT_ROOT` | `/data/execskill-20261021-pilot` | 试点的运行根目录，下面分 `G/`、`D/`、`shared/` |
| `PILOT_MANIFEST` | `/data/execskill-20261021-pilot-manifest.json` | 钉住一切输入的清单（4.13） |
| `HISTORY_ROOT` | `/data/execskill-history` | 跨运行根目录的本路线历史：消耗账（4.12）、补充题来源文件 |
| `SLOT_ROOT` | `/data/execskill-slots` | 整机共用的并发锁（2.7） |
| （运行手册路径） | `/data/execskill-20261021-sheet-q23` | 表格引擎的 23 项资格记录（4.2） |
| `NEVER_WRITTEN` | `/data/execskill-ops`、`/data/skillopt-work` | 永不写入：前者属于另一个探查任务；后者不是 git 仓库、里面有 `.env` |

规则：所有路径必须是真实路径，不能有符号链接（`safe_path`）。开跑以后若要改任何东西，就算新版本 v1.1，用新目录，旧目录和旧记录不动（登记稿 §1、AGENTS.md）。

### 2.3 两条链

一条「链」是一条从空包出发、按 SB → OQ 顺序走两步的完整流水线。两条链的系统提示、任务卡、壳、路由、裁判和判据都完全相同，只有做题模型和下表几行不同（登记稿 §4.1、§21）。

| 设置 | 链 G | 链 D |
|---|---|---|
| 做题模型 | `glm-5.3` | `deepseek-v4.1-flash-1017` |
| 客户端 | 冻结的 v3 BigModel 通道 `weak_solver_probe.Client` | 新客户端（代号 elucid），接口路径 `/v1/chat/completions` |
| 推理（思考） | 开，强度 low（冻结设置），推理 token 照常记账 | 关：`reasoning_effort: "none"`。每张回执都核对有没有偷偷推理，有就记 `thinking_mismatch` |
| 名义输出上限 M | 65,536（各题库相同） | 问答 8,192；SB 16,384；ALF 每步 1,024 |
| 账本上限 B | = M = 65,536 | 冒烟 S1-b 决定分支：E 分支 B = 2 × M；N 分支 B = max(4 × M, ⌈1.5 × 探针里最长的回答⌉)（这里的 M 是上一行的名义上限，不是「百万」；`protocol.py:ledger_bound`） |
| 读超时 | 2,400 秒 | 问答 600、SB 900、ALF 180 秒 |
| 并发 | `glm-5.3` 10 路，和两条链的方法角色共用 | 8 路，只给链 D（和冒烟） |
| 截断判定 | `finish_reason` 为 length / max_tokens | 同左，另外：可见 token ≥ M − 16 且标签或代码块没闭合 |

共同设置：温度 0；单轮 `[system, user]`；都走显式网关 `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`，并设 `trust_env=False`（不读环境里的代理变量）；凭证只按路径读，永不打印（`protocol.py`：`CHAINS`、`GLM_SOLVER_TOKENS`、`ELUCID_MAX_TOKENS`、`ELUCID_READ_TIMEOUT`、`GATEWAY`）。

- **两条链分开到什么程度。** 每条链有自己的账本 `<run root>/shared/ledger-<G 或 D>`，也有自己的消耗账命名空间。一条链停了，不会拖停另一条（`budgets.py:ledger_root`）。
- **为什么只算复现。** 两条链切的是同一批题，所以是同一批题上的重复运行，不是两份独立证据（登记稿 §0 (c)）。
- **账本怎么记。** 每发一次请求，先预留 4 × (请求字节数 + 512 + B) 个 token；回答回来后按实际结算（`budgets.py` 文档串，冻结的 v3 ledger）。这是故意保守的记法：cal-1 实验里，账本记 27.48M，账单 17.6M，实际 14.0M（登记稿 §9.3）。

### 2.4 五个角色（外加做题模型）

| 角色 | 模型 | 做什么 | 记在哪个作用域（`budgets.py:glm_scopes`） | 每步上限 |
|---|---|---|---|---|
| 工程师 engineer | GLM-5.3 | 写和改过程（5.4，下半部分） | `<c>:xs:<bench>:<k>:role:engineer` | 1.5M |
| 描述员 describer | GLM-5.3 | 冻结时把每条新过程改写成给做题模型看的文字说明（5.7） | 记在工程师作用域 | 同上 |
| 泄漏裁判 leakage | GLM-5.3 | 工程师代码里疑似泄漏参考答案时，判一次（5.4） | 记在工程师作用域 | 同上 |
| 考官 examiner | GLM-5.3 | 写检测器（5.2）、写出题策略和出题规格（5.3） | `<c>:xs:<bench>:<k>:role:examiner` | 2.5M |
| 查证员 researcher | GLM-5.3 | 按考官的查证请求，去维基百科或存档找素材（5.3） | `<c>:xs:<bench>:<k>:role:examiner:research` | 4.6M |
| 做题模型 solver | 链 G：glm-5.3；链 D：deepseek | 做题；每格记进 `overall`、`<c>:solver` 和本步的某一块 | 见 5.1 | 见 1.6 的表 |

- `<c>` 是链名 G 或 D，`<k>` 是第几步（1 = SB，2 = OQ）。
- 每次角色调用还要同时记进 `overall` 和 `<c>:glm`。`<c>:glm` 每条链 30M（`GLM_CAP`）；`overall` 每条链 210M（做题 180M + 角色 30M），两条链合计 420M。
- 角色调用的固定设置：`max_tokens` 16,384，读超时 900 秒，推理强度 low，输入不超过 220,000 字节（登记稿 §4.2；`protocol.py`）。

### 2.5 五个题库与题池

| 代号 | 题库 | 一道题长什么样 | 登记题池（训练/验证） | 测试集 | 试点用吗 |
|---|---|---|---|---|---|
| SB | SpreadsheetBench | 给一个 Excel 工作簿和要求，模型写一个 Python 程序：读 `input.xlsx`，写出 `output.xlsx`，答案放在指定格子里 | 120（80/40），其中 91 道参考答案合格（58/33） | 279 | 第 1 步 |
| OQ | OfficeQA | 给一段财政公报的文字和表格，问一个要计算的数，答案放进 `<answer>` 标签 | 74（50/24） | 172（分两段，各 86） | 第 2 步 |
| LM | LiveMath | 数学选择题，五个选项，回一个字母 | 283（155/128） | 125 | 只在测试读取里 |
| SQ | SearchQA | 问题加检索片段，回简短答案 | 600（400/200） | 400 | 只在冒烟和测试读取里 |
| ALF | ALFWorld | 文字版家务游戏，每步回一个动作 | 57（39/18） | 134 | 只在冒烟和测试读取里 |

出处：`supply.py:REGISTERED_POOLS` 和各分部数字（阅读笔记 r1）；测试集数见 `protocol.py` 的测试读取表。

- **题池是什么。** 题池 = v3 冻结的历史训练题加验证题（`coevo5.data.pool`），任何测试题都会被拒绝。
- **补充供给。** ALF 和 SQ 另有「补充供给」（4.7）：ALF 有 3,514 局题池外的训练局；SQ 有冻结抽样表第 4,001 位以后的「尾部」。ALF 的补充供给在冒烟里切出 12 局（S2 用 6 局，另 6 局原给已删掉的 S-N1；`protocol.py:SMOKE_REAL_ITEMS`），SQ 的尾部只在正式链里当验收段；试点的两步都用不到。

### 2.6 试点：SB → OQ，题怎么切

- **试点方案。** 默认方案 `PILOTS["default"]`：顺序 (SB, OQ)；每条链做题上限 180M，其中测试读取上限 99M，重做储备 14.8M。登记稿推荐过 SB → ALF（上限 300M / 126M / 22.9M），主人 22:3x 按默认值决定不走它，只留作记录（`protocol.py:PILOTS`）。
- **切法**（`supply.py:order`、`supply.py:slices`）：
  1. 每个题库排一个固定顺序：`data.ranked(题池, 20261021, "execskill-v1:order:<bench>")`，即按种子、标签和题号算哈希再排序；
  2. 先拿掉冒烟要用的题（SQ：顺序里最后 280 道；ALF：冒烟房间组里的 12 局）；
  3. 跳过本链别的单元占着的题，以及冒烟命名空间里用过的题；
  4. 从剩下的题里按顺序连续切出跑题段和验收段，每段只用一次。
- **试点的两段**（`protocol.py:SLICES`；阅读笔记 r1 用一次性导出核对过）：

| 题库 | 跑题段（题数 × 次数） | 验收段（题数 × 次数） | 验收分几块 | 顺序里的位置 |
|---|---|---|---|---|
| SB | 31 × 2 | 60 × 2 | 1 | 第 1–31 位跑题，第 32–91 位验收 |
| OQ | 24 × 2 | 50 × 4 | 2 块，每块 25 道，两块间隔 ≥ 7,200 秒 | 第 1–24 位跑题，第 25–74 位验收 |
| ALF | 60 × 1 | 150 × 1 | 4 | 只在正式链 |
| LM | 119 × 1 | 100 × 2 | 1 | 只在正式链，暂定 |
| SQ | 300 × 1 | 1,000 × 1 | 4 | 只在正式链，暂定；验收段取自尾部（`step.py` 里还没接上） |

- **SB、OQ 没有剩余。** 两个题库的每道合格题都被用上了。
- **验收段并不全部用掉。** 只有 A*（被改动的过程会触发的题）才真正发出去、记为用掉；其余题退回供给，记 `routed_not_dispatched`。|A*| < 30 时整轮不跑，什么也不消耗（`MIN_ASTAR = 30`；判法见下半部分）。
- **两条链切出的是同一批题。** 两条链切出的题一样，但各记各的消耗账（4.12）。

### 2.7 并发、锁和内存

| 名额池 | 数量 | 谁用 |
|---|---|---|
| `glm-5.3` | 10 | 链 G 做题，加上两条链全部方法角色调用 |
| `deepseek-v4.1-flash-1017` | 8 | 链 D 做题，以及冒烟 |
| `spreadsheet-native` | 3（S0 测得 native 峰值内存 > 2 GiB 时降为 2） | SB 的程序试跑和最终运行 |
| `alfworld-episode` | 6 | ALF 每局一个 |
| 隔离箱：存活容器 / 每次调用 | 6 / 4（SB 一个单元最多 2 个存活） | 过程运行（3.8） |

- **整机锁** `/data/execskill-slots/memory-heavy.lock`：SB 单元独占，ALF 单元共享，问答单元不拿。所以两条链的 SB 单元只能一个接一个跑，SB 也不会和 ALF 同时跑；OQ 单元可以重叠（`chain.py:heavy`，主人决定 #10）。
- **单元内的并发。** 一个单元里 16 个线程并发做格（`units.py:Setting.workers` = 16），ALF 单元是 6 个（`units.py:ALFWORLD_WORKERS` = `SLOTS["alfworld-episode"]` = 6）；同时活着的隔离箱另由 `SANDBOX_SLOTS`、`LIVE_SANDBOX_UNIT_CAP` 限制。

### 2.8 时间线（10/22）

| 时间 | 事件 | 状态 |
|---|---|---|
| 09:18 | 主人写好排除同意书（内容 sha256 前缀 `77872f24418fd20f`），`consent` 命令判定有效 | 完成 |
| 11:2x–11:41 | C7b1 的零调用真实检查（用完即弃的根目录 `/tmp/c7b1-root`，直接从构建树 `/data/execskill-dev` 跑，不是快照）：逃逸、隔离箱、确定性、测量、题池视图、回放、遗留进程通过，空包等价性修好计时后通过；SB 引擎一行被 C7b1-3 卡住 | 完成，用完即弃 |
| 12:50 | 一次性题池导出演练（I1） | 完成，用完即弃 |
| 13:0x | 主人裁剪冒烟：去掉 S-N1（重复测噪声）和 S4（完整小步加恢复演练） | 已登记 |
| 13:2x | 主人授权：冒烟通过就直接开试点 | 已登记 |
| 13:45 | 工单 C7e-1（G_acc 的做题费用记进考官作用域）、PR-C12-1（SB「不给工作簿」捷径探针）、PR-F2-1（每 15 分钟一窗的时段序列）写入代码（构建员 P2-A2） | 完成；14:20 连同测试和故意破坏检查一起收尾 |
| 13:49 | 一次性 q23 演练：23/23 项合格，54 秒；夹具 20/20/20 | 完成，用完即弃 |
| 14:10 | 登记员登记第 7、8、9、17 行：首次调用确认、测试读取估计、链级同意等待、`recover` 拒绝误操作 | 代码和针对性测试已由 P2C 补完（链 +20 项、协议 +13、验收 +2、命令行 +2、故意破坏条目 37–55，dl 上通过）；新开工单 P2C-1（`step-unit` 单独跑一步时绕过首次调用确认）、P2C-2（读取门在每次重启时都重新检查，读取已花掉一部分之后也照样检查；这是原有行为） |
| 14:4x | 主人指示：dl 上 29 个 D3/D14 遗留进程已杀掉（复查剩 0 个）；登记员裁定 S3 的跑题单元是 20 道 SQ 格 + 1 个确认格 | 完成 |
| 15:01 | 主人写好测试读取同意书 `/data/execskill-20261021-pilot/shared/consent.json`（252 字节，sha256 前缀 `2748d886fcb1b207`），`consent --root` 判定有效（裁定 15:1x：做到留出测试集评测就够，不另加确认集） | 完成 |
| 之后 | 全套单元测试（P2C 已跑完：1,183 项通过，824 秒，退出码 0）→ 整合员 I1 的收尾部分（笔记里写的是等 P2C 完成后再做的 (c) 部分，内容未核实）→ 一轮 Codex 审查 → 提交 → 最终快照 → 从最终快照重做 q23 → 冒烟 S0 → S1 → S2 ∥ S3 → S-E6 → 汇总 → 试点 | 全套测试已过；其余都没开始 |

- **试点怎么起步**（pilot-runbook）：开跑前检查 → `test-read-estimate`（从通过的冒烟算出测试读取估计）→ 钉住 → `make-manifest` → 起两条链；每条链先单独发一次首次调用确认（第 7 行，已建好，见 4.13），运行手册 5.3 的错开启动办法只留作后备。
- **之后的顺序**：SB 一步（链 G 在这一步的跑题单元一结束就做成本核对，见 5.1）→ OQ 一步 → 测试读取（读取同意书 `shared/consent.json` 已于 15:01 写好；什么也没收下的链不读）→ 解封。
- **要多久。** 登记的墙钟估计是每条链 1–2 天；每个 OQ 验收至少 2 小时，因为两块之间要隔 7,200 秒。两条链抢资源的影响没估计过。

**现状。** 本节的常量都在代码里，并有单元测试。两条链都还没起跑；链 G 的每格费用在冒烟里也量不到，因为冒烟只用链 D 的模型，要等链 G 第一个跑题单元结束后的成本核对（5.1）。

代码入口：`protocol.py`（`CHAINS`、`PILOTS`、`SLICES`、`SLOTS`、各根目录常量）；`supply.py:order`、`supply.py:slices`、`supply.py:registered_sizes`；`budgets.py:solver_scopes`、`budgets.py:glm_scopes`、`budgets.py:chain_caps`；`chain.py:heavy`。

## 3 学到的东西长什么样

**设置。** 被学习、会变的只有「包」。壳、路由、任务卡、格式句、裁判都是冻结的固定代码或固定文字（登记稿 §2）。这一节先讲包里装什么（3.1–3.3），再讲一次做题时壳怎样使用它们（3.4–3.7），然后讲运行环境（3.8）和不学习的部分（3.9），最后用两格完整例子串起来（3.10）。

### 3.1 过程（procedure）：被学习的最小单位

**做法。** 一条过程是一个 Python 模块，不超过 6,000 字节。模块顶层只许三种东西：import、常量（每个字面量 ≤ 2,000 字符）、函数定义。它实现 6 个钩子（3.2）里的若干个，并附一份记录（`package.py:PROCEDURE_FIELDS`）。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 过程记录 | 工程师写出，通过固定检查后由登记员保存：`<chain root>/procedures/<sha>.json`，其中 `<chain root>` = `/data/execskill-20261021-pilot/<G 或 D>` | `id, origin, accepted_at, description, hooks, source, header, max_note_chars, requests_second_call, state_bytes, excluded_benches, replay_tests, lineage` |

各字段的意思如下。
- **身份**：`id` 是编号，学到的过程叫 `p-<来源题库>-<步>-<n>`（登记员编号，例如 `p-spreadsheetbench-1-1`），夹具过程叫 `fx-<名字>`；`origin` 是来源题库；`accepted_at` 代码里一直写 null；`lineage` 是血统 `{engineer_call, parent, revises}`。
- **内容**：`hooks` 声明实现了哪些钩子；`source` 是源码；`description` 1–600 字符，只给人看，绝不给做题模型看。
- **对做题模型说话的方式**：`header` 是 ≤ 200 字符的固定便条抬头，也要过词表筛（3.5）；`max_note_chars` 只有实现了便条钩子才有，取值 1–4,000；`requests_second_call` 声明是否可能请求第二次调用。
- **其他**：`state_bytes` 是 ALF 状态的声明大小（≤ 65,536）；`excluded_benches` 用来缩小适用范围，默认空；`replay_tests` 是每条新增或修订的过程 1–8 个回放测试（`protocol.py:MAX_TESTS` = 8；`replay.py:run_tests`）。每个测试指定一条存下的轨迹（格号）、一个钩子和一个性质；性质只能从固定种类里选，例如 `applies_true`、`binding_equals`，还要写明拿掉这条过程或扰动输入后性质必须不成立（`nonvacuity`）。

```json
{"id": "p-spreadsheetbench-1-1", "origin": "spreadsheetbench", "accepted_at": null,
 "description": "<给人看的说明，≤ 600 字符>", "hooks": ["applies", "before_call", "bindings"],
 "source": "<Python 源码，≤ 6,000 字节>", "header": "<≤ 200 字符的抬头>", "max_note_chars": 1200,
 "requests_second_call": true, "state_bytes": 0, "excluded_benches": [],
 "replay_tests": [{"id": "t1", "trajectory": "<格号>", "hook": "bindings", "claims_fix": true,
                   "property": {"kind": "binding_equals", "name": "<名字>", "value": "<值>"},
                   "nonvacuity": {"withheld_expect": false, "mutation": null}}],
 "lineage": {"engineer_call": "<请求哈希>", "parent": null, "revises": null},
 "version": "fivebench-execskill-v1-procedure", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

### 3.2 六个钩子（名单封闭，`protocol.py:HOOKS`）

| 钩子 | 什么时候跑 | 收到什么 | 可以返回什么 | 时限 |
|---|---|---|---|---|
| `applies(view)` | 每道题开始时一次（ALF：每局开始时一次） | 路由视图（3.4） | 只能是真或假：这道题启不启用我 | 2 秒 |
| `before_call(view, state)` | 问答、SB：第一次请求之前 | 公开视图 | 有类型的便条字段（3.5） | 5 秒 |
| `bindings(view)` | 问答：第一次请求之前 | 公开视图 | 带名字的数 `[{name, value, quote}]`；数值和原文引语都必须逐字出现在题面里，否则这一条被丢掉 | 5 秒 |
| `sheet_feedback(view, run_report, state)` | SB：程序在公开输入上试跑一次之后 | 公开视图 + 试跑报告 `{status, exc_type, message, answer_cells}` | 便条字段，外加是否请求一次修改调用（`request_repair`） | 5 秒 |
| `alf_before_step(view, state)` | ALF：每一步请求之前 | 这一步的视图 + 状态 | 便条字段 + 「不建议的动作」列表（只标注，模型仍可输入） | 5 秒 |
| `alf_after_step(event, state)` | ALF：每一步执行之后 | 这一步的事件 + 状态 | 只能返回新状态 | 5 秒 |

- **哪些钩子能产生便条、哪些能引出第二次调用**（`package.py`）：
  - 能产生便条的有 4 个（`NOTE_HOOKS`）：`before_call`、`bindings`、`sheet_feedback`、`alf_before_step`；
  - 能引出第二次调用的只有 2 个（`SECOND_CALL_HOOKS`）：`bindings` 和 `sheet_feedback`。
- **出错不会让运行暂停**：
  - `applies` 出错，这道题就不启用这条过程（登记稿 §4.4 P2 行）；
  - 其他钩子出错，这道题从出错那一刻起不带它继续做（P1 行，「失败即放行」）。
  - 两种都算过程故障，计入验收的 2% 故障上限。

### 3.3 包（package）：被学习的「技能」本身

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 包记录 | 每步开始时的父包、工程师得到的候选包、冻结后的新父包；`<chain root>/packages/<sha>.json`，按内容寻址、只写一次 | `parent_sha256, procedures（过程记录的哈希）, order（过程编号的顺序）, retired（撤掉的）, narrowed（缩小范围的）, step, describer（冻结时的文字说明）` |

- **上限**（`protocol.py`）：
  - 一个包最多 24 条过程（`MAX_PROCEDURES`），源码合计不超过 64,000 字节（`MAX_PACKAGE_BYTES`）；
  - 每一步最多改 3 处（`MAX_CHANGES`）。改动只有四种：新增、修订、撤掉、缩小范围（`EDIT_KINDS`）。
- **起点和冻结。** 每条链从空包 `empty(step="<chain>/s0")` 出发。冻结时加上描述员写的文字说明（`with_describer`），会得到一个新哈希。

```json
{"parent_sha256": "<父包 64 hex>", "procedures": ["<过程记录 64 hex>"], "order": ["p-spreadsheetbench-1-1"],
 "retired": [], "narrowed": {}, "step": "G/s1-spreadsheetbench", "describer": {},
 "version": "fivebench-execskill-v1-package", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

（核对过 `package.py`：`step` 写成 `<链>/s<k>-<题库>`，空包是 `<链>/s0`；`narrowed` 是 `{过程编号: [被排除的题库]}`；`describer` 冻结前是空的 `{}`，冻结后每条过程一项 `{prompt_sha256, text_sha256}`，只存两个哈希。）

### 3.4 壳与路由：一次做题调用前后发生什么

**做法**（`solver.py:solve`；`router.py`）：
1. **空包时什么都不起。** 问答和 SB 上，包里没有适用于本题库的过程（比如第 1 步的空包）时，不启动容器，请求和 v3 冻结的请求逐字节相同。ALF 是例外：每一局都起一个容器并先 ping 一下，让所有组走同一条名额路径（`cells.py:_worker`）。空包的这个等价性有零调用测试（S0 的等价性一行）；ALF 只比较每一步都在标签里原样给出合法动作（`tag_exact`）的那些局。
2. **路由。** 包里有过程时，这一格按需启动一个容器（用到才起，一格一个），先对每条过程跑一遍 `applies`，得到这道题的启用名单，写进路由日志（`fivebench-execskill-v1-route`）。路由视图分题库：
   - 问答：公开视图；
   - SB：`{instruction, workbook_preview, input_path, required_output_path, required_answer_position}`；
   - ALF：准备阶段零调用预先重置一次得到的视图 `{initial_observation, admissible_commands_at_reset, task_text}`，做题时逐字节核对哈希。
3. **便条。** 对启用的过程依次运行 `before_call` / `bindings`，结果过一遍便条筛（3.5），渲染后放进用户 JSON 的最后一个键 `procedure_notes`。没有过程启用时，请求里没有这个键。
4. **系统提示**在所有组里逐字节相同（`continual_eval/backends.py`）：`"Solve the supplied task using only the supplied public information."` + 格式句 + `"\n\nFrozen skill guidance (use only where applicable):\n"` + 当前题库的任务卡。这个顺序来自 v3 的运行设置 `prompt_layout = contract-first-v2`（格式句在任务卡前面；`solver.py:_system`、`coevo5/protocol.py:RUNTIME`）。ALF 的拼法稍有不同。
5. **第一次调用做题模型。** 之后视情况再调一次：问答走计算往返（3.6），SB 走修改往返（3.7）。
6. **判分并写记录。** 裁判 v2（`execskill-judge-v2`）判分，壳把自己的记录写进格记录（3.10）。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 用户 JSON | 题目的公开部分 + 便条 | OQ、SQ：`{question, context}`；LM：`{question, choices}`；SB：`{instruction, workbook_preview, input_path: "input.xlsx", required_output_path: "output.xlsx", required_answer_position}`，其中 `workbook_preview` 最多 20 张表，每张给前 5 行 × 20 列；ALF 每步：`{initial_observation, observation, admissible_commands, recent_history}`（最近 5 步）。有便条时最后再加 `procedure_notes` |
| 壳记录 | 写进格记录和作答轨迹；种类 `fivebench-execskill-v1-shell` | `route, calls, procedure_events, faults, notes, notes_chars, compute, precheck, fallback, deciding_receipt, worst_delivery, arm, sandbox`，ALF 另有 `alfworld_steps`，捷径探针另有 `shortcut` |

```json
{"route": {"bench": "officeqa", "package_sha256": "<64 hex>", "routing_view_sha256": "<64 hex>",
           "order": ["p-spreadsheetbench-1-1"],
           "per_procedure": {"p-spreadsheetbench-1-1": {"applies": true, "enabled": true, "withheld": false,
                                                        "restored": false, "shadow_fired": false, "fault": null}},
           "enabled": ["p-spreadsheetbench-1-1"], "faults": [],
           "version": "fivebench-execskill-v1-route", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"},
 "calls": [{"purpose": "first", "request_sha256": "<64 hex>", "receipt_index": 0, "reason": null},
           {"purpose": "second", "request_sha256": "<64 hex>", "receipt_index": 1, "reason": null}],
 "procedure_events": [{"id": "p-spreadsheetbench-1-1", "fn": "before_call", "args_sha256": "<64 hex>",
                       "value_sha256": "<64 hex>", "fault": null, "cpu_ms": 12}],
 "faults": [], "notes": [{"id": "p-spreadsheetbench-1-1", "hook": "before_call", "fields": {"facts": ["<一条事实>"]},
                          "rendered_chars": 812, "dropped": []}], "notes_chars": 812,
 "compute": {"tags": ["a/b"], "results": [{"expr": "a/b", "value": "<精确值>"}]}, "precheck": null, "fallback": null,
 "deciding_receipt": 1, "worst_delivery": "delivered",
 "arm": {"withheld": [], "restored": [], "placebo": [], "text": []}, "sandbox": {"restarts": [], "cleanups": []},
 "version": "fivebench-execskill-v1-shell", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

（键名逐项对过 `solver.py:_Shell.record` 和 `router.py:RouteLog.to_json`，值是占位。`worst_delivery` 取 `delivered`、`truncated`、`no_call` 或 `undelivered:<原因>` 这类记号；没发生的 `compute`、`precheck`、`fallback` 是 null；问答格没起容器时 `sandbox` 是 null。）

### 3.5 便条：过程能对做题模型说的全部

- **有类型的字段**（`notes.py:FIELD_TYPES`）。过程不能直接写自由文字，只能返回下面五种字段：

| 字段 | 形状与上限 | 壳加的固定表头（`protocol.py:NOTE_HEADERS`） |
|---|---|---|
| `facts` | 字符串列表，每条 ≤ 200 字符 | "Facts extracted by a helper program (may be incomplete):" |
| `table` | 表格，每格 ≤ 40 字符，≤ 20 行 × 12 列 | "A table extracted by a helper program (may be incomplete):" |
| `candidates` | 字符串列表，每条 ≤ 120 字符 | "Candidates listed by a helper program (may be incomplete):" |
| `warnings` | 字符串列表，每条 ≤ 200 字符 | "Cautions noted by a helper program (may be incomplete):" |
| `bindings` | `{name, quote, value}`，≤ 200 字符 | "Named values quoted from the task by a helper program:" |

- **词表筛**（`LEXICON_TERMS`）。字段里只要出现下列「教模型怎么输出」的词，整个字段就被丢掉，并记一次过程故障：`<answer`、`<action`、`` ``` ``（代码块记号）、answer、respond、output、return、json、only the、just the、bare、single letter、round、decimal places、units、format。
  - 不分大小写，词形变化也算，比如 formatted、rounding；
  - SB 豁免 format 一词；
  - 便条里原样引用题面的引语或表格格子，算题目自己的文字，不筛（裁定 A3-1）。
- **总长上限**（`MAX_NOTE_CHARS`）：问答和 SB 每次请求 4,000 字符；ALF 每步 1,500 字符。超出时按包内顺序整条跳过，所有组都一样处理。

### 3.6 计算往返（问答题）

**做法**（登记稿 §2.4；`compute.py`、`solver.py`）：
1. **邀请。** 某条过程的 `bindings` 便条被展示时，壳在便条后加一句固定邀请（`COMPUTE_INVITE`）："If you need arithmetic, you may write <calc>EXPRESSION</calc> tags (at most 8) using these names or plain numbers; they will be evaluated exactly and returned to you once."
2. **精确求值。** 第一次回答里有合法的 `<calc>` 标签，壳就用固定的精确计算器求值。限制：
   - 最多 8 个标签，每个 ≤ 300 字符；
   - 用分数算术；只认 ASCII 的 `+ - * /` 和 `**`，整数指数绝对值 ≤ 12；
   - 嵌套 ≤ 20 层，任何中间值的分子或分母 ≤ 4,096 个二进制位（`MAX_BITS`）；
   - 函数只有 abs、round、min、max、sum。
   - 登记稿写的是「+ − × ÷」，代码只认 ASCII 写法，两者有出入。
3. **第二次调用。** 用户内容 = 第一次的内容 + 第一次回答 + 计算结果 `[{expr, value}]` + 固定的跟进句（`COMPUTE_FOLLOWUP`）："The expressions above were evaluated exactly. Use these values if they are relevant and give your final answer in the required format."
4. **失败怎么办。**
   - 某个表达式算不出：照样发第二次，结果写 "not evaluated"；
   - 第二次回答没送达或被截断：退回用第一次回答，记 `second_call_fallback`（P5 行）；
   - 第一次回答已经截断：不发第二次，这一格按截断判错。
- **阅读时发现的疑点**（核对代码属实，尚无登记员裁定）：SB 的求解路径也调用同一个 `_Shell.before`（`solver.py:_solve_sheet`），所以 SB 上若有过程实现 `bindings` 且便条被展示，壳同样会在便条后加计算邀请；但 SB 路径把这些名字丢掉，从不做计算往返。没找到别的检查拦住。

### 3.7 SB 的试跑与修改往返

**做法**（登记稿 §2.5；`precheck.py`、`solver.py`）：
1. **抽程序。** 按 `explicit-python-fences-v1` 规则，从第一次回答里抽出程序。
2. **试跑。** 不管包里有没有过程，壳都在公开输入表上试跑一次：拿一个 native 名额，起一个一次性容器，命令行和环境变量照抄冻结的 `_native`。报告存进 `shell.precheck`。
3. **请求修改。** 如果有过程实现了 `sheet_feedback`，它读报告，可以给建议并请求修改；只有过程声明过 `requests_second_call` 时，这个请求才算数。
4. **修改调用最多一次。** 用户内容 = 第一次的内容 + 原程序 + 修改指令 `REPAIR_FRAME`（"Your program above was executed once on the public input workbook; the run report and a helper program's notes follow. Revise the program if needed and give the complete program in the required format."）+ 试跑报告 `{status, exc_type, message}` + 过程的建议。
5. **用哪个程序。** 修改后的程序送达、没截断、抽得出来，才用它；否则退回原程序，记 `second_call_fallback`。
6. **最终运行与判分。** 最终程序在冻结的 `_native` 里对公开输入运行（300 秒、4,096 MB、1 CPU），再交冻结的 v7 判分链 `qualified_lo_recalc_v7_v1` 判对错。

试跑报告的骨架（键名取自阅读笔记 r2）：

```json
{"status": "exception", "exc_type": "KeyError", "message": "<最后一行报错，≤ 500 字符>",
 "answer_cells": {"Sheet1!B2": "<值，≤ 200 字符>"}}
```

`status` 取 ok / exception / missing_output / unknown 之一；`answer_cells` 最多 2,000 格。公开输入表以只读方式挂在容器里的 `/input/input.xlsx`，从不放进消息正文，也从不挂答案表。

### 3.8 隔离箱：过程在哪里运行

| 项 | 登记值（`sandbox/client.py`、`protocol.py`） |
|---|---|
| 镜像 | 钉死的 native 镜像 `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd`，`--pull=never`，不新建镜像 |
| 加固 | `--network=none --read-only --user=65534:65534 --cap-drop=ALL --security-opt=no-new-privileges=true`，`/tmp` 是 16 MB、不可执行的内存盘 |
| 启动 | `python -s -B -P /runner/worker.py`；`PYTHONHASHSEED` 设为 0；工程师做确定性检查时，第二个工作进程用 1；docker 命令的环境只留 `PATH` |
| 每次请求 | 在容器里另起（fork）一个全新子进程：不能写文件（`RLIMIT_FSIZE` 0），最多 32 个文件描述符；内存紧张时先杀它 |
| 资源上限 | 做题、ALF 局、检测器：64 个进程、768 MB、0.5 个 CPU、地址空间 2,048 MiB、单帧 1 MiB；出题程序：1,024 MB、1 个 CPU（`CELL_LIMITS`、`LIMITS`） |
| 时限 | 适用条件 2 秒，钩子 5 秒，检测器 5 秒，出题程序 60 秒（`SANDBOX_TIMEOUTS`） |
| 容器名 | `execskill-sbx-<链>-<单元哈希前 12 位>-<uuid>`；单元结束后核对这个单元名下的容器一个不剩 |
| 辅助函数 | `public_workbook()`（读公开工作簿的唯一入口）、`safe_sympify()`（安全的符号计算） |

- **安全边界只有容器。** 导入白名单和禁用名单（exec、eval、open、os、subprocess、`openpyxl.load_workbook` 等）只是卫生层（登记稿 §2.6）。
- **出错怎么算。**
  - 一次请求里的崩溃、超时、超内存、输出不合格，都算那条过程的故障（P1 行），不暂停；
  - 镜像不在、docker 起不来、容器删不掉，才算「隔离箱不可用」（`SandboxUnavailable`，P4 行），这时单元暂停，等主人决定。
- **一处过时的注释。** `client.py` 注释里写「4 倍」，代码实际用 2 倍。不影响运行。

### 3.9 任务卡与格式句：冻结，永不学习

| 题库 | 任务卡（字符数，sha256 前缀） | 格式句（原文） |
|---|---|---|
| SQ | 1,846，`48b10afc` | "Return the concise final answer inside <answer>...</answer>." |
| OQ | 2,926，`2e92500a` | 同上 |
| LM | 2,068，`9cb3d860` | "Choose exactly one of the listed options and return only its letter inside <answer>...</answer>." |
| SB | 2,907，`48a5df7f` | `SHEET_CONTRACT_V2`："Return one complete Python program in a `` ```python `` code block whose opening fence starts its own line. The program reads input.xlsx and saves output.xlsx with the answer at the required answer position. A formula alone is not an answer: when the task asks for a formula, the program writes it into the answer cells." |
| ALF | 2,301，`5ae6ea9b` | "Act in the text environment. Return a single action inside <action>...</action>." |

- **任务卡从哪来。** 任务卡是 v3 I-ds 链起点用的五份指令，是已知最强的文字基线（cal-1）。每道题只给当前题库那一张：v3 把五张全给，结果别的题库的格式建议在 OQ 上造成 −9.5 到 −33 分（登记稿 §2.2）。
- **格式句只作指令。** 不做任何输出改写；四个格式句的 sha256 只记录下来（前缀：问答 `f8daf424`、LM `97e1b962`、SB `6dbedf61`、ALF `844c8c18`）。
- **工程师碰不到它们。** 工程师检查 C8 会确认：系统提示重新渲染后哈希不变。
- **ALF 的动作规范化只到第 1 级，所有组都开**（`canonical.py`）。规则：取第一个 `<action>` 标签里的文字（没有标签就取整段回答），去掉首尾空白；正好是某个可选动作就照它执行；否则反复去掉开头的 "action:"、首尾的引号和空白、末尾的句号，再不分大小写地比较，恰好对上一个可选动作时，换成那个动作的原写法执行；还对不上就原样执行。不会在回答里到处搜可选动作，那算答案修补。
- **一处要求。** 裁定第 12 行：清单里钉的必须是任务卡全文，不能只钉哈希。

### 3.10 两格完整的例子

**格是什么。** 格号 = sha256(`{unit, arm, task_id, run}`) 的前 32 位十六进制；`task_id` 写成 `"<bench>/<题号>"`。每一格写下：格记录 `<attempt>/cells/<格号>.json`（`fivebench-execskill-v1-cell`）和认领文件 `<格号>.claim`；完整作答轨迹 `<attempt>/trajectories/<格号>.json`（存全部文字）；启用日志 `enable_log.jsonl` 里的一行；存下的预测与判分 `<attempt>/artifacts/<sha>.json`；SB 另有判分用的宿主侧临时目录 `<attempt>/host_only/scorer_artifacts/<位置>/`。

**例一：SB 第 1 步，链 G，组 S（空包），一道跑题段的题，第 1 次运行。**
1. **路由。** 包里没有过程，路由为空，不启动隔离箱，没有便条。
2. **请求。** 系统提示 = 基础句 + `SHEET_CONTRACT_V2` + 指导语 + SB 任务卡；用户 JSON 是 SB 那五个键。这一请求和 v3 的冻结请求逐字节相同。
3. **记账。** 记进 `overall`、`G:solver`、`G:xs:spreadsheetbench:1:run` 三个作用域。B = 65,536，所以这一次预留 4 × (请求字节 + 512 + 65,536)。
4. **回答之后。** 抽出程序，照样在公开输入上试跑，报告存进 `precheck`。包里没有 `sheet_feedback`，所以不发修改调用。
5. **判分。** 程序在 `_native` 里运行，v7 判分链判对错。SB 没有 JSON 补救通道，裁判 v2 就等于考虑了完成情况的最终判定 `final`（`judge.py`）。
6. **写盘。** 记录写到 `/data/execskill-20261021-pilot/G/s1-spreadsheetbench/run/attempt-1/cells/<格号>.json`。

**例二：OQ 第 2 步，链 G，组 S。** 这是假设：第 1 步收下了过程 `p-spreadsheetbench-1-1`，它实现 `applies`、`before_call`、`bindings`。登记的最可能结果是什么也收不下。
1. **路由。** `applies` 在 OQ 公开视图上返回真。
2. **入场读数。** 这条继承来的过程在跑题段上启用的比例 ≥ 1/10，所以跑题单元还要加跑一组 C（5.1）。
3. **便条。** 起容器，`before_call` 给事实或表格，`bindings` 给带原文引语的数。过筛、加表头，后面接计算邀请，放进 `procedure_notes`。
4. **两次调用。** 第一次回答里写了 `<calc>` 标签，壳精确求值后发第二次调用；第二次回答送达且没截断，就作为最终回答。
5. **判分。** 裁判 v2 先认最后一个非空的 `<answer>` 标签，用 OQ 的规范化精确匹配判对错。
6. **对应的 C 格。** 不起容器，只有一次调用。
7. **写盘。** 记录写到 `/data/execskill-20261021-pilot/G/s2-officeqa/run/attempt-1/cells/<格号>.json`。

格记录的骨架（顶层键名取自阅读笔记 r2 对 `cells.py` 的核对，值是占位）：

```json
{"cell": {"id": "<32 hex>", "unit": "G/s2-officeqa/run", "arm": "S", "benchmark": "officeqa",
          "task_id": "officeqa/<id>", "run": 0},
 "arm": "S", "task_id": "officeqa/<id>", "run": 0, "package_sha256": "<64 hex>",
 "arm_kind": "parent", "enabled": ["p-spreadsheetbench-1-1"], "withheld": [], "restored": [],
 "attempts": [{"step": "solve", "prediction": "<存档引用>", "score": "<存档引用>", "verdict": {"outcome": "pass", "…": "…"}}],
 "remedies": {}, "spent": [], "sends": [], "refused": false,
 "logical_calls": [{"purpose": "first", "…": "…"}, {"purpose": "second", "…": "…"}],
 "deciding_receipt": 1, "worst_delivery": "delivered", "faults": [], "fault_kinds": {},
 "final": {"outcome": "<结果>", "kind": "<种类>", "reason": "<原因>", "row": null, "remedy": null,
           "exhausted": null, "token": "pass"},
 "official": {"status": "<冻结判分器的结果>", "reason": "<原因>"},
 "judge": {"version": "fivebench-execskill-v1-judge", "scorer": "execskill-judge-v2", "official": "…", "final": "…",
           "v2": {"token": "pass"}, "lenient": "…", "format": "…", "flags": "…", "carrier": "…"},
 "shared_with": null, "sandbox": {"restarts": [], "cleanups": []},
 "dispatch_ts": 1792627200.0, "finish_ts": 1792627500.0, "stop": null,
 "version": "fivebench-execskill-v1-cell", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

（键名逐项对过 `cells.py`，值是占位。`run` 从 0 数起；`token` 取 `pass`、`fail`、`unknown`、`unknown_artifact`，过程故障造成的未知记 `unknown_fault`；`dispatch_ts`、`finish_ts` 是 Unix 时间秒数；验收格另有 `set`、`block`，捷径探针格另有 `shortcut`；`attempts` 里每次尝试是 `{step, prediction, score, verdict}`，预测和判分本身存在 `artifacts/` 下。）

- **一格出问题时的补救**（冻结的 v3 规则，`coevo5/protocol.py`）：SB 重新执行同一个程序、SB 换新目录重新判分、ALF 在任何模型调用之前就失败时重新开局，各最多 2 次；什么都没送达时原样重发请求，最多 2 次，每次间隔 300 秒。
- **哪些情况不算基础设施问题。** 回答被截断算错，过程故障算方法自己的毛病。

**上限与调用。** 一格最多 2 次逻辑调用：第一次，加计算或修改中的一次。ALF 每步一次。所有容器和名额数见 2.7。

**现状。** 3.1–3.10 的代码都已写好并有单元测试。用夹具和假后端演练过；在真实接口上一格也没跑过。

代码入口：`package.py:PROCEDURE_FIELDS`、`package.py:empty`、`package.py:with_`、`package.py:with_describer`；`router.py:plan`；`solver.py:solve`；`notes.py:screen`、`notes.py:assemble`；`compute.py`；`precheck.py`；`sandbox/client.py`、`sandbox/worker.py`；`judge.py`；`cells.py`。

## 4 准备阶段（S0：数据与零调用检查）

**设置。** 冒烟和试点之前，按冒烟手册（`docs/handoff/execskill-build-20261021/smoke-runbook.md`，14:42 版）的顺序在 dl 上执行。
- **不调模型。** 全部步骤都不调用任何模型。
- **读测试集的只有一步**：「排除测试题」。它只在主人的排除同意书下运行，留下的记录只有计数和哈希。
- **命令前缀。** 命令写作 `$CLI <子命令>`，`$CLI = $PY -B $SRC/scripts/run_execskill.py`，从代码快照 `$SRC` 运行；运行前先 `unset OPENAI_API_KEY OPENAI_BASE_URL`（命令行程序启动时自己也会再清一次）。
- `$V3` 是 v3 的运行清单 `/data/coevo5-20261019-v3-run-manifest.json`，只从里面读训练题的路径；`$HIST` 是 `/data/execskill-history`。

### 4.0 总表

| # | 命令 | 主要输入 | 主要输出 | 现状 |
|---|---|---|---|---|
| 1 | 快照 + `verify-snapshot` | 构建树 | `$SRC`、`$PRE/build-head.txt`、`$PRE/source-sha256.txt` | 等最终提交 |
| 2 | q23 资格 + `sheet-runtime` | 快照、钉死的重算镜像 | `/data/execskill-20261021-sheet-q23/qualification.json`、`$PRE/sheet-runtime.json` | 演练 23/23；正式一次等最终快照 |
| 3 | `zero-call-checks`、`leftovers` | 快照、进程表 | 全套单元测试结果；有没有残留进程 | 待做；D3/D14 遗留进程主人已在 14:4x 杀掉 |
| 4 | `s0-pool-views` | `$V3` | `$PRE/s0-pool-views.json` | 演练过 |
| 5 | `make-fixtures` | 工作簿大小的 p99（4.4） | `$PRE/fixtures/fixtures.json` | 演练 20/20/20 |
| 6 | `import-texts`、`import-sheet-qualification` | v3 的任务卡、v3 的 SB 资格记录 | `$PRE/texts/texts.json`、`$PRE/sheet/sheet-qualification-import.json` | 待做 |
| 7 | `make-items`（alfworld、searchqa） | ALF 游戏文件、本地 HF 缓存 | `$HIST/supply/alfworld-xs.json`（含视图）、`$HIST/supply/searchqa-tail.json` | 12:20–12:22 只数数的空跑 |
| 8 | `exclude-tests` | 排除同意书 + 两份补充供给 | `$SMOKE/shared/exclusion/` 下三份记录 | 同意书已签，命令待跑 |
| 9 | `export-pools` | `$V3` | `$PRE/pools/<bench>.json` + `pools.json` | 12:50 演练 |
| 10 | `smoke-items` | 导出的 SQ 池、ALF 供给、夹具 | `$PRE/smoke-items/` | 待做 |
| 11 | `sandbox-selftest`、`s0-collect`、`smoke-make`、`smoke --stage S0` | 以上全部 | `$PRE/s0/`、`$SMOKE/s0/`、`$PRE/s0-pins.json`、`$SMOKE/smoke.json` | 待做 |
| 之后 | S1 `probe` → 冒烟清单 → S2 ∥ S3 → S-E6 → `smoke-summary` → 试点钉住 + `make-manifest` | | | 下半部分 |

### 4.1 给代码拍快照（#1）

**做法。** 依次做四件事：
1. `git rev-parse HEAD > $PRE/build-head.txt`；
2. 用 `prelaunch.sha256_list('/data/execskill-dev')` 写出 `$PRE/source-sha256.txt`；
3. `rsync` 复制 `skillopt/ scripts/ tests/` 到 `$SRC`，排除 `.env*`、`.git`、`__pycache__`；
4. `$CLI verify-snapshot --list $PRE/source-sha256.txt --root $SRC --git-head <提交号>`：逐个文件核对 sha256，并确认快照里没有任何 `.env*`。

输出的 `provenance` 是 `{build_tree, git_head, snapshot_root, sha256_list_sha256, env_files_absent}`，后面钉进清单。

代码入口：`scripts/run_execskill.py`（`verify-snapshot`）；`prelaunch.py:sha256_list`。

### 4.2 表格引擎资格 q23 与 sheet-runtime（#2）

**为什么每个快照要重做。** 冻结的 v7 判分引擎记录里，7 个判分源文件是按绝对路径登记的，所以它只能在当初生成它的那份代码里重新验证通过（裁定 C7b1-3）。v3 也是每个快照各做一次（q23-a … q23-f）。

**做法。**
- **生成资格记录。** 在 `$SRC` 里运行 `python -m scripts.replay_sheet_v6 qualify --output /data/execskill-20261021-sheet-q23 --image sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790 … --engine-version v7`。它不调模型，只起重算容器：v3 那次用了 48 秒，今天 13:49 的演练 23/23 项合格、54 秒。
- **生成 SB 运行设置。** `$CLI sheet-runtime --manifest $V3 --engine-qualification <q23>/qualification.json --out $PRE/sheet-runtime.json`：照抄 v3 的 SB 运行设置，只换掉 `recalculation` 里的 `qualification_path`、`qualification_sha256`、`qualification_hash` 三项。镜像或超时和 v3 不同，或者在这份代码里验证不过，它就拒绝。

```json
{"recalculation": {"image": "sha256:f7f6f598…c4d790", "qualification_path": "/data/execskill-20261021-sheet-q23/qualification.json",
                   "qualification_sha256": "<64 hex>", "qualification_hash": "<64 hex>", "timeout_seconds": "<照抄 v3 清单；v3 代码默认 120，清单里的值未核实>"}}
```

代码入口：`scripts/run_execskill.py`（`sheet-runtime`）；`scripts/replay_sheet_v6.py`（冻结）；`engines.py`。

### 4.3 零调用检查与遗留进程（#3）

- **`zero-call-checks --root $SRC`。** 在快照里跑全套单元测试，时限 3,600 秒。
- **`leftovers`。** 查机器上有没有残留进程，三种结论：`clean`、`leftovers`、`cannot_judge`。代码仍按命令行排除 D3、D14 的旧进程，并把「无法判断」算作通过（主人决定 #3 的默认值）。但主人 14:4x 已让人杀掉那 29 个 D3/D14 遗留进程（复查剩 0 个，可用内存 10 → 13 GiB），#3 的默认不再适用，这一行可以在干净的机器上判（裁定 14:4x）。另有一个无害的 D2 等待循环（PID 27038），删不删由主人定。

代码入口：`scripts/run_execskill.py`（`zero-call-checks`、`leftovers`）；`s0.py`。

### 4.4 题池视图（#4）

**做法。** `$CLI s0-pool-views --manifest $V3 --out $PRE/s0-pool-views.json`：算每个题库训练题的公开视图有多大，用来定隔离箱的单帧上限和夹具大小。演练时的数（题数 / 最大视图字节数）：ALF 39 / 176，LM 155 / 6,491，OQ 50 / 30,116，SQ 400 / 4,697，SB 80 / 12,449；SB 工作簿大小的 p99（99% 的工作簿不超过这个大小）是 599,328 字节。

代码入口：`scripts/run_execskill.py`（`s0-pool-views`）；`s0.py`。

### 4.5 工程夹具（#5）

**做法。** `$CLI make-fixtures --out $PRE/fixtures --p99-workbook-bytes <p99>`：
- **夹具题。** OQ、LM、SB 各造 20 道，编号 `fx-<bench>-NN`，分部标 `engineering_fixture`，种子标签 `execskill-v1:fixtures`。全是登记员自己写的内容，从不抄任何真题。SB 里有一道按 p99 工作簿大小加料，就是 `fx-spreadsheetbench-19`。
- **夹具包 X。** 一组夹具过程：`fx-note`、`fx-bindings`、`fx-print`、`fx-crash`、`fx-sheet-repair`、`fx-alf-tracker`，专门用来把便条、计算、修改、故障这些路径都走一遍。
- **输出。** `fixtures.json`（`fivebench-execskill-v1-fixtures`）。夹具永远不算学到的技能。

代码入口：`fixtures.py:make_fixtures_cli`。

### 4.6 导入任务卡与 SB 资格（#6）

- **导入任务卡。** `$CLI import-texts --source /data/coevo5-20261019-v3-pre/texts/texts.json --out $PRE/texts`，得到 `texts.json`，内容是 `{cards, card_sha256, source}`。
- **导入 SB 资格。** `$CLI import-sheet-qualification --source <v3 SB 训练资格> --sha256 <记录哈希> --out $PRE/sheet`：
  - `--sha256` 必须是记录自己的哈希 `acc5c07f76a088969181cf45e8224fae2d4d033aa49385713802cba5338827a1`；给文件哈希（`83ae6be2…`）会被拒绝；
  - 只认可导入版本表 `IMPORTABLE = ("fivebench-coevolution-v3-sheet-qualification",)` 里的版本；
  - 输出 120 道题，其中 91 道合格。

代码入口：`scripts/run_execskill.py`（`import-texts`、`import-sheet-qualification`）；`qualify.py`。

### 4.7 造补充题（#7）

- **ALF。** `$CLI make-items --bench alfworld …`：
  - 从题池外的 3,514 局训练局里造题，编号 `alfworld-xs:<游戏文件相对路径 sha256 前 16 位>`；
  - 108 个房间按种子顺序分组：冒烟 4、跑题 16、验收 40、挑选 20、备用 28；
  - 只给切出来的段做零调用的预先重置：冒烟 12 + 跑题 60 + 验收 150 + 挑选 200 = 422 局，约 7–21 分钟；
  - 写出 `$HIST/supply/alfworld-xs.json` 和 `alfworld-xs-views.json`；题号到游戏文件的对照只在这份登记员文件里，任何角色都看不到。
- **SQ。** 用工具环境运行 `make-items --bench searchqa …`，只读本地 HF 缓存：
  - 重放 10/12 冻结的抽样，只取第 4,001 位以后的尾部，排除题池题和以前抽到过的问题；
  - 封存的 C、D 块从不落盘；
  - 空跑数出 11,378 道尾部题（4.8 秒）。
- **一处出入（未核实）。** ALF 空跑在 3,514 局里只数出 6 种任务类型（`smoke-inputs.md`），登记稿 §3.1 写的是「实测 7 种前缀，建设时用代码重数」；第 7 种是否只出现在题池那 57 局里，没有查清。

代码入口：`supply.py:alfworld_items`、`supply.py:searchqa_tail`、`supply.py:prereset`、`supply.py:write_supply`。

### 4.8 排除测试题（#8，需要主人的排除同意书）

**设置。** SQ 尾部和 ALF 新局都可能和测试集重合，所以要先剔除。这一步要读测试集，所以必须在主人亲手写的同意书下运行。同意书已于 10/22 09:18 写好，`consent` 命令判定 `{"exclusion": "valid"}`。它以后不能再改，因为两份排除记录都存了它的哈希。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 输入：排除同意书 | 主人亲手写：`$SMOKE/shared/exclusion-consent.json`（`protocol.py:EXCLUSION_CONSENT`） | 字段恰好是 `{exclusion_runs, by, date, note}` |
| 输出：SQ 排除记录 | `$SMOKE/shared/exclusion/searchqa_test_exclusion.json` | `counts {supply, test_items, dropped_by_id, dropped_by_question, kept}`、`dropped`（哈希）、`exclusion_sha256`、`supply_sha256`、`consent_sha256` |
| 输出：ALF 身份核对 | `$SMOKE/shared/exclusion/alfworld_test_identity_check.json` | `valid_unseen`、`disjoint`（新局和测试局不相交） |
| 输出：测试金丝雀 | `$SMOKE/shared/exclusion/test-canaries.json` | SQ、ALF 各 5 条，每条 ≥ 24 字符，只存长度和 sha256 前 16 位，用来以后扫描有没有测试题泄进运行目录 |

```json
{"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner",
 "date": "2026-10-22", "note": "<主人的一句话>"}
```

命令：`$CLI exclude-tests --root $SMOKE --pinned <v3 数据钉> --searchqa-supply $HIST/supply/searchqa-tail.json --alfworld-supply $HIST/supply/alfworld-xs.json`。注意它和最后测试读取要用的读取同意书 `<pilot root>/shared/consent.json` 是两回事；后者主人已于 15:01 写好（252 字节，sha256 前缀 `2748d886fcb1b207`，`consent --root` 判定有效；裁定 15:1x），若 v1.1 换到新目录，要在新目录重写一次（下半部分）。

代码入口：`exclusion.py:exclude_tests`；`scripts/run_execskill.py`（`exclude-tests`、`consent`）。

### 4.9 导出题池（#9）

**做法。** `$CLI export-pools --manifest $V3 --out $PRE/pools`：用冻结的读取器 `coevo5.data.pool` 导出五个题库的训练加验证题，从不碰测试题。每个题库写一份 `<bench>.json`，按固定顺序排好；旁边写一份封存的 `pools.json`（`fivebench-execskill-v1-pool-export`），并打印清单要钉的 `data.pools`。SB 只导出 91 道合格题。12:50 演练打印的数（正式运行必须复现）：SQ 600 道（400 训练 + 200 验证），冒烟段 280 道 = 198 训练 + 82 验证（摘要 `7033d48d…`），跑题段 300；SB 91 = 跑题 31 + 验收 60；OQ 74 = 跑题 24 + 验收 50；LM 283 = 跑题 119 + 验收 100 + 选项探针 64；ALF 57 道带 `room`、`task_type`，这次没切（工单 I1-1）。

代码入口：`supply.py:export_pool`、`supply.py:write_pool_export`、`supply.py:load_pool`。

### 4.10 冒烟题（#10）

**做法。** `$CLI smoke-items --out $PRE/smoke-items --searchqa-pool $PRE/pools/searchqa.json …`，写出三类题和一份清单：
- **SQ。** 池顺序里最后 280 道：S2 用 20，S-N1 用 200，S4 用 60。S-N1 已被裁掉，那 200 道现在不用。S3 自己的跑题单元用 S4 那 60 道里的前 20 道，它的确认格用其中第 1 道（冒烟手册 14:42 版）。登记员 14:3x 的文字曾说约 60 道，已由 14:4x 的裁定改定为「20 道 SQ 格 + 1 个确认格」，和冒烟手册一致。
- **ALF。** 冒烟房间组里的 12 局。
- **夹具。** OQ、LM、SB 的夹具集。
- **清单** `smoke-items.json`：按 `SET=FILE` 列出各文件，供 `s0-collect` 和 `smoke-make` 使用。
- **消耗账。** 真题登记进消耗账的 `smoke` 命名空间，单元 `smoke/items`。这是消耗账的第一笔记录（4.12）。

代码入口：`scripts/run_execskill.py`（`smoke-items`）；`supply.py:slices`；`registry.py`。

### 4.11 隔离箱自检、S0 汇总与内存守卫（#11）

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 隔离箱自检 | `$CLI sandbox-selftest --out $PRE/s0 --items …` → `$PRE/s0/sandbox-selftest.json` | `escape_rows`（8 行逃逸探针）、`escape_probe_sha256`、`worker_sha256`、`image`、`limits`、`measured {vsz_kib, rss_kib, view_bytes_p99, start_seconds, views}`、`passed` |
| S0 各行 | `$CLI s0-collect --root $SMOKE …` → `$SMOKE/s0/s0-<行>.json`（`fivebench-execskill-v1-s0-row`；冒烟手册写成 `<行>.json`，少了 `s0-` 前缀，以代码为准）和 `checks.json` | 14 行，见下 |
| 上限推导 | 测量行通过后才写：`$SMOKE/s0/s0-limits.json`、`$PRE/s0-pins.json` | `s0-pins.json` 恰好是 `{limits, measured}`，`measured` 含 `native_peak_rss_kib` |
| 冒烟规格 | `$CLI smoke-make …` → `$SMOKE/smoke.json` | 阶段 `[S0, S1, S2, S3, SE6]`；冒烟账本 16M（做题 14M + GLM 2M），探针 0.5M；格式下限 9/10，组间差 ≤ 1/20；≥ 300 张正式回执；`control_cells` 为空，`noise_anchor` 为 null 并写明原因 |

- **`s0-collect` 的 14 行**：
  - 单元测试；空包等价性；异常分类；账本；
  - 隔离箱套件（12 个案例，约 20 秒）；逃逸探针；测量；
  - 确定性（111 个哈希）；
  - D3 回放（228 条轨迹 / 7,524 步，约 6.5 分钟）；
  - 供给；SB 引擎；消耗账；Codex 夹具；遗留进程。
  - 每行只跑一次，全部通过才以 0 退出。最后 `$CLI smoke --stage S0 --input $SMOKE/s0/checks.json` 把 S0 记成冒烟阶段。
- **C7b1 的实测**：
  - 工作进程虚拟内存 174,140 KiB，常驻 112,152 KiB；每次请求的子进程 85,464 KiB；
  - native 峰值 43,872 KiB，远低于 2 GiB，所以 native 名额保持 3 个；
  - 启动 3.18 秒；最大视图 30,116 字节。
- **内存守卫的公式**（裁定 A5-1）：
  - 地址空间上限 = max(2,048 MiB, 2 × 虚拟内存向上取整到 256 MiB)；
  - 单帧上限 = max(1 MiB, 2 × 最大视图向上取整到 1 MiB)；
  - 各类名额数 × 峰值常驻之和 ≤ 0.7 × 可用内存；否则先把每次调用的隔离箱从 4 降到 2，再把存活容器从 6 降到 4。
  - 实测 1,146,384 ≤ 7,762,974 KiB，有 6.8 倍余量。
- **阅读笔记发现的缺口。** 降档的结果没有带进清单，而且守卫是在降档之后才判；这和冒烟手册 §0 的说法不一致，还没处理。按现在 6.8 倍的余量，实际不会触发降档。

代码入口：`scripts/run_execskill.py`（`sandbox-selftest`、`s0-collect`、`smoke-make`、`smoke`）；`s0.py`；`escape_probe.py`；`smoke.py`。

### 4.12 消耗账：每道训练题被谁用掉

**设置。** 「没有可反复使用的验证集」要靠这本账来保证：同一条链里，一道题一旦被判过，就再也不能进入任何一段（登记稿 §3.4）。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 消耗账 | 登记员写：`/data/execskill-history/consumption/<G 或 D 或 smoke>/<bench>.jsonl`，旁边有 `.lock` | 每行字段恰好是 `version, chain, bench, item_id, item_hash, state, purpose, unit, run_root, attempt, ts, evidence, record_sha256` |

- **状态**：`registered`（已登记，题被这个单元占着）→ `dispatched`（已发出）→ `decided`（已判定）；没发出就退回的记 `routed_not_dispatched`。
- **用途**：`smoke`、`run`、`accept`、`accept_probe`、`examiner`、`detector_holdout`。
- **规则**：
  - 同一命名空间里，另一个单元占着的题再被登记，就抛 `ConsumptionConflict` 并暂停；
  - 重做的单元沿用自己原来的登记；
  - 判过的题永不再登记。
  - 两条链和冒烟各用一个命名空间（`protocol.py:NAMESPACES`），所以两条链会用到同一道题，各记各的。

```json
{"version": "fivebench-execskill-v1-consumption", "chain": "G", "bench": "officeqa", "item_id": "officeqa/<id>",
 "item_hash": "<64 hex>", "state": "dispatched", "purpose": "accept", "unit": "G/s2-officeqa/accept",
 "run_root": "/data/execskill-20261021-pilot", "attempt": 1, "ts": "2026-10-2xT00:00:00+00:00",
 "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

（`unit` 一栏就是单元标签 `<chain>/s<k>-<bench>/<unit>`，跑题单元登记时用的正是它；`attempt` 是尝试序号（整数），`ts` 是 UTC 的 ISO 时间，精确到秒。）

代码入口：`registry.py`（登记、状态变更、`entries`、`consumed`）。

### 4.13 钉住清单（`make-manifest`）与起跑

**做法。** `$CLI make-manifest --out <清单> --pins <钉住文件> --exclusion-root <根目录> --s0-pins $PRE/s0-pins.json`。冒烟用的清单在 S1 之后做一次；试点清单在冒烟通过后做一次，写到 `PILOT_MANIFEST`。
- **钉住的内容。** `pins` 的键恰好是 `root, data, sheet_qualification, cards, contracts, runtime, clients, fixtures, provenance`，外加 `evidence`。
- **它做三件事。** 先核对 S0 的排除记录和金丝雀并绑进 `data.exclusion`、重新验证 SB 运行设置，再写 `<root>/shared/test-canaries.json`，最后写清单（`fivebench-execskill-v1-manifest`）。清单的 `record_sha256` 就是这次运行的身份；各级上限取 `budgets.caps()`。
- **`--s0-pins` 实际上必填。** 不给它、钉住文件里又没有 `limits` 时，代码直接抛一个没有说明的 KeyError。
- **测试读取估计。** `data.test_read_estimate {G, D}` 必须给。它的生成器（登记员 14:10 第 8 行）已由 P2C 建好：公式是 `protocol.py:estimate_test_read`，命令 `$CLI test-read-estimate --smoke $SMOKE --out <文件>` 从通过的冒烟结果算一次、只写一次；协议和命令行都有新测试（P2C 笔记：协议 +13 项、命令行 +2 项，dl 上通过）。按登记的高锚点、账本/实际比例取 1，公式给出 54,409,087；开读前 `<c>:solver` 和 `<c>:test` 都要剩下它的 1.3 倍，约 70.7M（`<c>:test` 上限 99M）；链 G 还要乘上它最近一次成本核对的系数（大于 1 时）。
- **`consent --root <根目录>`** 只检查同意书，不写任何东西。

```json
{"pins": {"root": "/data/execskill-20261021-pilot", "data": {"pools": {}, "test_read_estimate": {"G": 0, "D": 0}},
          "sheet_qualification": {}, "cards": {}, "contracts": {}, "runtime": {}, "clients": {}, "fixtures": {},
          "provenance": {"git_head": "<提交号>", "sha256_list_sha256": "<64 hex>", "env_files_absent": true}},
 "caps": {"overall": 420000000}, "version": "fivebench-execskill-v1-manifest", "evidence": "pilot_real_run",
 "record_sha256": "<64 hex，即运行身份>"}
```

（骨架只示意顶层；`caps` 的具体键和 `pins` 下各块的内部结构未逐项核对。）

**起跑。** `run` 命令（`runcli.py:run` → `chain.py:run_manifest` → `chain.py:run`）依次做这些事：
1. 从清单造出运行设置（`manifest.setting_of`）和服务（`services_of`），研究存档放在 `<root>/shared/research/<chain>`；
2. 写 `chain.json`，在账本上声明本链的上限（`budgets.chain_caps`）和首次调用确认的上限（`<c>:confirm`，1.1M，`budgets.first_call_caps`）；
3. **首次调用确认**（登记员 14:10 第 7 行，P2C 已建好，`chain.py:first_call`）：用本链自己的做题客户端和第一步题库（SB）的登记设置，单独发一次固定夹具请求（101 字节，不用任何题池题，不记消耗账），核对有回答、回显的模型名对、账本确有结算，链 D 还要核对没有偷偷推理。通过就写一次 `confirm.json`，以后重启都复用、不再发；不通过就写 `confirm-failed-<n>.json`，以 `first_call_unconfirmed` 暂停（退出码 3），一个单元都不开；
4. 从空包出发，逐步调用 `step.learn`。每个单元开始前都重新核对一遍钉住的文件；
5. 两步走完后：什么也没收下（F = C）的链在 `test-read.json` 里记 `not_read`；否则先查读取同意书（缺了就写 `read-waiting.json`，以退出码 3 等主人），再查剩余预算是否够 1.3 倍估计（链 G 的估计先乘上它最近一次成本核对的系数，系数小于 1 时按 1 算；找不到通过的成本核对就拒读），然后读测试集（下半部分）。

**现状。** 第 4 节的命令都已实现并有单元测试（`test-read-estimate` 的测试是 P2C 最后补上的；补完后全套 route-B 单元测试 1,183 项通过，退出码 0）。真实运行至今只有两份同意书、几次空跑和用完即弃的演练；正式的 S0 等最终快照。

代码入口：`manifest.py`（`setting_of`、`services_of`）；`scripts/run_execskill.py`（`make-manifest`、`consent`、`test-read-estimate`）；`protocol.py:estimate_test_read`；`runcli.py:run`；`chain.py:run_manifest`、`chain.py:run`、`chain.py:first_call`、`chain.py:read_consent`、`chain.py:read_budget`。

## 5 一步的八个小步（上）：5.1 跑题、5.2 考官诊断、5.3 考官出题

**设置。** 一「步」是指：在一个题库上，从父包 S 出发，走完登记稿 §5 的八个小步。代码把它做成 9 个单元，因为工程师改包（5.4）和自测（5.5）各有第二轮，单元顺序是 `step.UNITS` = `run, diagnose, generate, engineer, selftest, engineer-2, selftest-2, accept, freeze`。5.8「读测试集」在试点里不放在每一步，而是挪到整条链的最后读一次。这一部分讲前三个单元，后面的见下半部分。

### 5.0 单元怎样工作，一步在磁盘上的样子

- **单元目录。** 每个单元一个目录 `<chain root>/s<k>-<bench>/<unit>/`，例如 `/data/execskill-20261021-pilot/G/s1-spreadsheetbench/run/`。
  - 同一时刻只有一个进程能拥有它（`.lock`）；
  - 每次尝试一个 `attempt-N/` 子目录，开始时写 `started.json`；
  - 做完写一次 `unit.json`。做完的单元以后只读回核对，绝不重跑（`units.py:run_unit`）。
- **暂停。** 出事时在当次尝试里写 `status.json`；如果是崩溃，回溯写进 `diagnostics.log`。
  - 没有任何东西会自己恢复：主人用 `recover` 命令在那次尝试里写下 `recovery.json`（`{by: "owner", date, decision}`）之后，下一次尝试才能开始；
  - 一个单元最多重做 2 次，也就是 `attempt-3` 是最后一次，再要第 4 次就拒绝（`redo_limit`）；
  - 第一次重做从 `<c>:redo` 储备（14.8M）里预先拨款，第二次要主人写明上限决定（`protocol.py`：`MAX_REDOS = 2`、`PREFUNDED_REDOS = 1`）。

```json
{"run": "<清单 record_sha256>", "identity": {"unit": "G/s1-spreadsheetbench/run", "chain": "G", "k": 1,
 "bench": "spreadsheetbench", "parent": "<父包 64 hex>"}, "status": "complete", "attempt": "attempt-1",
 "result": {"items": 31, "runs": 2, "cells": 62, "firing_share": 0.0, "entry_reading": null},
 "version": "fivebench-execskill-v1-unit", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

（核对过 `step.py`、`units.py`：`identity` 就是 `{unit: 单元标签 <链>/s<k>-<题库>/<单元>, chain, k, bench, parent: 父包哈希}`；`attempt` 存的是目录名 `attempt-N`。）

**一步在磁盘上的样子**（路径相对于 `<chain root>` = `/data/execskill-20261021-pilot/<G 或 D>`，`<k>` 是步号，`<bench>` 是题库全名）：

| 路径 | 内容 |
|---|---|
| `packages/`、`procedures/` | 包记录、过程记录（3.1、3.3） |
| `chain.json`、`.runner.lock` | 链的身份；一条链同时只能有一个运行进程 |
| `confirm.json` 或 `confirm-failed-<n>.json` | 首次调用确认通过的记录（只写一次，重启复用），或每次失败一份（4.13） |
| `cap-check-G.json`（主人改过上限后的重核写 `cap-check-G-<n>.json`） | 链 G 的成本核对（只在链 G，5.1） |
| `read-waiting.json` | 缺读取同意书时的等待记录，只有计数（4.13） |
| `s<k>-<bench>/slices.json`、`step.json` | 本步的两段题（1.5）；本步记录 `{chain, k, bench, step, parent_sha256, candidate_sha256, package_sha256, decision, reason, decision_sha256, fault_items, violating_items, units（各单元记录的哈希）, evidence_kind: "selection"}` |
| `s<k>-<bench>/<unit>/.lock`、`unit.json` | 单元锁；单元结果（只写一次） |
| `s<k>-<bench>/<unit>/attempt-N/started.json` | 这次尝试的开始记录 |
| `…/attempt-N/cells/<格号>.json`、`<格号>.claim` | 格记录；认领文件 |
| `…/attempt-N/trajectories/<格号>.json`、`enable_log.jsonl` | 完整作答轨迹；过程启用日志 |
| `…/attempt-N/artifacts/`、`host_only/` | 存下的预测与判分；SB 判分用的宿主侧临时目录 |
| `…/attempt-N/status.json`、`diagnostics.log`、`recovery.json` | 暂停状态；崩溃回溯；主人的决定 |
| `s<k>-<bench>/diagnose/attempt-N/candidates.json` | 封存的检测器候选（5.2） |
| `s<k>-<bench>/generate/attempt-N/research-split.json`、`generated-G_self/<16 hex>/` | 查证发现的两半；SB 生成题的工作簿（5.3） |
| `s<k>-<bench>/accept/sealed.json`、`accept/attempt-N/decision/decision.json` | 验收前的封存；验收决定（下半部分） |
| `test/<bench>/`、`test-read.json` | 测试读取（下半部分） |
| `chain-complete.json` 或 `chain-terminated.json` | 链正常结束或被终止的标记 |
| `<run root>/shared/` | `ledger-G/`、`ledger-D/`、`research/<chain>/sources/`、`test-canaries.json`、`consent.json`、`host_only/` |

### 5.1 跑题（`run` 单元）

**设置。** 每一步的第一件事，是用父包 S 在跑题段上做题。产生的成功和失败记录有三个用处：给考官诊断（5.2）；给工程师读（5.4）；在验收时当安慰剂的供体语料（下半部分）。

**做法**（`step.py:_run`）：
1. **登记。** 在消耗账里登记跑题段的题，用途 `run`。
2. **算触发比例。** 零调用计算 S 里继承来的过程在这些题上的启用比例（`_firing_share`，在路由视图上跑 `applies`）。
3. **定组。** 组 S 跑登记的次数。若触发比例 ≥ 1/10（`ENTRY_READING_SHARE`），组 C（只有任务卡）也跑 1 次，用来算描述性的「入场读数」S − C；它不进入任何决定（登记稿 §5.1）。
4. **发出。** 记为已发出，然后 `rounds.run_round`：全部格按种子顺序 sha256(`[20261021, "execskill-v1:round:<unit>:run", 序号]`) 打乱，16 个线程并发做。
5. **检查。** `rounds.guard`：任何一组里「基础设施未知」的格超过 1/10，就暂停，类型 `infrastructure_incomplete`。
6. **判定。** 记为已判定，写 `unit.json`。
7. **成本核对。** 如果是链 G 的第 1 步，接着做一次成本核对（见下）。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 输入：父包 S、跑题段 | `packages/<sha>.json`；`s<k>-<bench>/slices.json` 的 `run` | 见 3.3、1.5 |
| 输出：格与轨迹 | `s<k>-<bench>/run/attempt-N/cells/`、`trajectories/` | 见 3.10 |
| 输出：单元结果 | `s<k>-<bench>/run/unit.json` 的 `result` | `{items, runs, cells, firing_share, entry_reading: {items, mean_s_minus_c, decides: false}}`；没有 C 组时 `entry_reading` 为 null |
| 输出（只链 G、第 1 步）：成本核对 | `<chain root>/cap-check-G.json` | `{run, chain, ok, per_cell, anchor_high: 4273, scopes: {作用域: {cap, projected}}}` |

**上限与调用。**
- **格数。** SB 是 31 题 × 2 次 = 62 格。第 1 步 S 是空包，触发比例为 0，所以没有 C 组。OQ 是 24 × 2 = 48 格；若继承的过程触发比例 ≥ 1/10，再加 C 组 24 格，共 72 格。
- **暂停线。** SB 62 格里 ≥ 7 格未知；OQ 的 S 组 48 格里 ≥ 5 格、C 组 24 格里 ≥ 3 格未知。
- **作用域。** 第 1 次尝试记进 `overall`、`<c>:solver`、`<c>:xs:<bench>:<k>:run`。重做时多记 `<c>:redo`，并改记 `…:run:attempt-N`。
- **上限和估计。** 上限 SB 1.2M、OQ 2.3M；登记估计每条链 SB 0.16–0.42M、OQ 0.50–1.2M（登记稿 §9.2）。
- **一处限速。** 链 G 每发一次请求至少预留 4 × (512 + 65,536) ≈ 264k 账本 token，所以 1.2M 的跑题作用域里同时只容得下大约 4 个在途请求。其余的格排队等，不算暂停；对墙钟时间的影响没量过（阅读笔记 r2 的估计）。
- **链 G 的成本核对**（`step.py:cost_projection`、`chain.py:cap_check`；登记稿 §9.3，主人规则 (c)）：
  - **为什么要做。** 冒烟只用链 D 的模型，链 G 每格花多少没实测过，所以在链 G 第一个跑题单元之后补一次核对。
  - **怎么算。** 每格实际记账 token ÷ SB 的高锚点 4,273 = 系数；链 G 每个作用域的预计用量 = 上限 ÷ 1.5 × 系数。只要有一个超过上限，就算破线。
  - **折算成一条线。** 这等价于每格超过 1.5 × 4,273 = 6,409.5 个账本 token；62 格合计 397,389。
  - **破线之后。** 写 `cap-check-G.json`，只暂停链 G。提高上限解不开它，只能终止链 G，或者按 v1.1 在新目录里重新登记。
  - **预期。** 登记员 14:10 第 18 行引用 v1 的 GLM 证据，预计系数约 0.65–0.83。
- **首次调用确认**（登记员 14:10 第 7 行）。在链的第一个付费单元之前，单独发一次固定夹具请求，确认真能拿到回答（做法见 4.13 起跑第 3 条）。P2C 已建好并有测试；运行手册里错开启动两条链的临时办法只留作后备。这次调用记进 `<c>:confirm`（上限 1.1M：按链 G 一次完整预留 = 4 × (101 + 512 + 65,536) = 264,596，四次 = 1,058,384，向上取到 0.1M；`protocol.py:FIRST_CALL_CAP`），同时也记进 `<c>:solver` 和 `overall`；成本核对不把它算进去（`step.py:cost_projection` 跳过 `G:confirm`），冒烟 S-E6 的外推也不算它。

**现状。** 代码已实现，有单元测试（`step`、`rounds` 的测试和假后端端到端测试），从没在真实数据上跑过。第一次真实使用会是冒烟 S3 自己的跑题单元：S4 那 60 道 SQ 里的前 20 道，加 1 个确认格（冒烟手册 14:42 版；登记员 14:4x 裁定）。

代码入口：`step.py:_run`、`step.py:_firing_share`、`step.py:_entry_reading`、`step.py:cost_projection`；`rounds.py:run_round`、`rounds.py:guard`；`chain.py:cap_check`；`registry.py`。

### 5.2 考官诊断（`diagnose` 单元）

**设置。** 这是考官进化的前一半：在跑题段的失败里，找出固定的机械类别解释不了的那些，写成能运行的「失败检测器」（登记稿 §5.2、§7.1）。检测器被接受，是考官一侧「进化成功」的两条路之一。

**做法**（`step.py:_diagnose`；`detectors.py`、`examiner.py`、`trajectories.py`）：
1. **对半分。** 父包 S 的跑题轨迹按题分组（ALF 按房间），用种子标签 `execskill-v1:detsplit:<chain>/s<k>-<bench>/diagnose` 排序：双数位进「写的一半」，单数位进「验的一半」。
   - 试点里 SB 是 16 / 15 题，OQ 是 12 / 12 题。
   - 标签里含链名，所以链 G 和链 D 的分法不同。
2. **遮掩视图和机械类别。** 检测器和考官看到的轨迹都遮掉了答案：
   - 问答：`{bench, task, notes, replies}`，答案标签、JSON 答案等内容被换成 `[masked]`；
   - SB：只给任务、第一份便条和第一个程序，不给试跑结果；
   - 给考官看的视图多一个 `passed`（这一格对不对）。
   - 固定的机械类别（零参考答案）：问答有 `empty_reply`、`no_answer_tag`、`json_answer_untagged`、`multiple_answers`、`truncated_or_suspected`；SB 有 `no_program`、`excel_formula_only`、`fence_glued`、`program_exception_on_public_input`，最后这一类在遮掩视图上算不出，不参与残差定义。
3. **考官写检测器。** 最多 2 次调用：一次写；只有回答解析不了时，才再要一次重写（`DETECTOR_CALLS = 2`）。
   - 输入：写的一半每格的 `{residual, passed, categories, covered_by, view}`，从末尾裁到 220,000 字节以内；
   - 回答：一个 `` ```json `` 块 `{"detectors": [{"description": "…"}]}`（≤ 3 条），每条再配一个 `` ```python `` 块，定义 `detect(view)`；源码要过和过程一样的静态检查；
   - 编号 `d-<bench>-<k>-<n>`。
4. **先封存。** 碰验的一半之前，先把候选写进 `diagnose/attempt-N/candidates.json`。一个候选都没有时，就不读验的一半，`validation` 为 null。
5. **在验的一半上验证。**
   - 有效格少于 10 个，或者来自不到 6 道题：整份记录写 `cannot_decide`。
   - 「残差格」= 既没有机械类别、也没有已收检测器报警的格；基准失败率在残差格上算。
   - 每个候选在两个新隔离箱里各跑一遍：种子 0 按顺序，种子 1 倒序，结果必须一致。
   - 统计：按题整组重抽 10,000 次，检验「精确率 − 基准失败率 ≤ 0.10」；同一步的几个候选之间做 Holm 校正（同时检验好几个候选时，防止靠运气过关的校正），水平 0.10。另外要求在残差失败里的召回率 ≥ 0.15，与已收检测器的重合度（Jaccard）< 0.8。
   - 判词按先后，第一条不过就停：`faults_or_nondeterministic` → `too_few_alarms`（残差报警 < 10 或来自 < 6 题）→ `too_few_rooms`（ALF 用）→ `lift_not_established` → `recall_below_minimum` → `duplicate_of_accepted` → `accepted`。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 输入：S 的跑题轨迹 | `s<k>-<bench>/run/attempt-N/trajectories/*.json`，只取 `arm_kind == "parent"` | `fivebench-execskill-v1-trajectory`：`cell, task_id, run, calls, replies, shell, token` |
| 输入：已收检测器库 | 本链之前同一题库的 `diagnose` 结果 | 试点里永远是空的：每个题库只走一次 |
| 输出：封存的候选 | `diagnose/attempt-N/candidates.json` | `fivebench-execskill-v1-detector-candidates` |
| 输出：验证记录 | `diagnose/unit.json` 的 `result.validation` | `fivebench-execskill-v1-detector-validation`：`status, residual_cells, residual_failed, base, masked_categories, library, candidates[{id, n_fired, n_items, n_rooms, precision, lift, p_boot_lift_le_0.10, p_holm, recall_residual, jaccard_max_full_hold, faults, deterministic, reason, accepted}]`；题太少时 `status` 为 `cannot_decide`，`residual_cells`、`base` 为 null |
| 输出：单元结果 | `diagnose/unit.json` 的 `result` | `{split, written, validation, detectors}`；每个检测器一份 `fivebench-execskill-v1-detector` 记录，`retired_at` 为 null |

```json
{"status": "ok", "residual_cells": 22, "base": 0.45,
 "candidates": [{"id": "d-spreadsheetbench-1-1", "n_fired": 0, "n_items": 0, "precision": null, "lift": null,
                 "p_holm": 1.0, "recall_residual": 0.0, "deterministic": true, "reason": "too_few_alarms", "accepted": false}],
 "version": "fivebench-execskill-v1-detector-validation", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

**上限与调用。** 考官最多 2 次 GLM 调用，记进 `<c>:xs:<bench>:<k>:role:examiner`（每步 2.5M，和 5.3 共用）。检测器每次运行限 5 秒。这个单元不调做题模型。

**现状与诚实说明。**
- **代码。** 已实现，有单元测试。冒烟 S3 只走一次「写加验证」；其余部分第一次真跑就是试点。
- **试点里多半什么也收不下。** 验的一半在 SB 上约 30 格、OQ 上约 24 格，一个候选要有 ≥ 10 个残差报警、来自 ≥ 6 题，还要过 Holm 和召回率。所以最可能的判词是 `too_few_alarms`、`lift_not_established` 或 `cannot_decide`。
- **还没做的。** 撤下检测器（退役）还没实现。
- **收下了也不参与决定。** 一个被收下的检测器不参与任何决定。登记稿说工程师能看到「检测器计数」；代码里给工程师的只是固定机械类别在整个跑题段上的计数（`detectors.counts(detectors.diagnosis(...))`），已收检测器的报警不在其中（阅读笔记 r4，14 点半后抽查代码属实）。

代码入口：`step.py:_diagnose`、`step.py:_library`；`detectors.py:split`、`detectors.py:seal_candidates`、`detectors.py:validate`、`detectors.py:detector_records`；`examiner.py:detector_payload`、`examiner.py:detector_write`；`trajectories.py:masked_view`。

### 5.3 考官出题（`generate` 单元）

**设置。** 这是考官进化的后一半，也是主人定死「必须先查证」的地方（登记稿 §5.3、§7.2）。生成题分两半用：
- **G_self**：给工程师自测（5.5）用；
- **G_acc**：验收时由登记员用这里冻结的出题程序生成，用来检验「生成题上的好坏能否预测真题」，工程师永远看不到。代码用的是 `g_acc` 那一半查证材料，A* 只决定题数和配对（裁定 C1-3）；登记稿原文写的是「用在 A* 的公开题面上」。

SQ 和 ALF 没有登记的出题族（代码里叫 `selection_only`），这个单元立刻结束。

**做法**（`step.py:_generate`；`examiner.py`、`research.py`、`generators/`）：
1. **定策略**（1 次调用）。
   - 考官收到 `{"request": "policy", bench, families, previous, outcomes, max_requests: 24}`，回 `{families, requests, rationale}`，`rationale` ≤ 600 字符；有一条不合格，整份作废：沿用上一次的策略，没有上一次就是空策略（`examiner.py:policy_revise`）。
   - 出题族：OQ 有 difference、ratio、percent_change、sum；SB 只有 formula_edit；LM 的四族只在正式链里用。
   - 请求有两种：`family_material {family, concept ≤ 100 字符, topic}`；`parameter_choice {family, question ≤ 300 字符, names 1–6 个, topic}`。SB 上 `parameter_choice` 一律不合格。
2. **查证**（`research.py:Researcher`）。
   - **防泄漏。** 每个请求先用固定代码对跑题段做泄漏筛查，命中就不发。
   - **次数上限。** 最多 24 个请求；每个请求最多 3 轮、每轮 3 个检索词（每个 ≤ 100 字符）、最多读 3 页、最多 8 次调用。
   - **素材来源。** OQ 的表格和 LM 的定义来自英文维基百科接口（超时 60 秒，走网关）；SB 的函数说明只来自钉死的存档 `/data/coevo5-20261019-v3-archive`。
   - **合格条件。** 表格 2–60 行 × 2–15 列，至少 1 个数字格；定义的引文 ≤ 1,500 字符并逐字出现；函数引文 1–3 段、每段 ≤ 500 字符并逐字出现；参数值必须在它的引文里。
   - **存档位置。** 存到 `<run root>/shared/research/<chain>/sources/<sha>.json`。登记稿写的是单元目录，两者不一致，没有登记员裁定。
3. **分两半。** 合格发现按 sha256(`"execskill-v1:research-split:<unit>:<id>"`) 排序：双数位给 `g_self`，单数位给 `g_acc`，写进 `generate/attempt-N/research-split.json`，在工程师开始前就封存。
4. **写出题规格**（含重写和难度调整，最多 6 次调用）。
   - 考官收到 `{"request": "generators", bench, families, materials（只有 g_self 那一半）, parameters, sources（只有 SB：跑题段源题的路由视图）, max_parameter_sets: 10, band}`，回 `{"specs": […]}`，最多 24 条；
   - 像答案的键一律删掉。
5. **固定代码出题。** 出题程序编号 `g-<bench>-<k>-1`，生成题编号 `gen:<出题程序>:<n>`，每条发现最多出 10 道，真值由固定代码算出。
   - OQ：表格格子换数，小数位 0–4，最多扰动 2 个格子 ±20%。
   - SB：只改跑题段的源题，从不碰验收题或测试题；最多 5 处修改，公式 ≤ 200 字符；源题的答案格必须是公式。每道题要 3 次重算加 1 次资格检查，占 native 名额。
   - 工单 PR-C61-2 让 SB 生成题绑定两个工作簿的 `asset_sha256`，输入表和参考答案表都由引擎重算一遍、带上公式缓存：构建员 P2-A1 在 13:4x–13:5x 做完，测试通过，真实零调用检查里 6 道生成题全部保留（P2-A1 笔记）。
6. **四道关**（`examiner.gates`，全过才「准入」`admitted`）：
   - **真值关**：至少留下 1 道题，每道的真值都由出题族的固定代码算出；
   - **难度关**：组 S 在最多 30 道题上各做 1 次，通过率必须在 [1/5, 4/5] 之间。不在范围就把通过率和方向告诉考官重写规格、整套重建，最多探 3 次（首次 + 2 次调整）；
   - **捷径关**：组 C 在最多 30 道题的「残缺版」上各做 2 次，两次都对的题删掉，删掉的比例 > 1/4 就整套不可用。残缺版是：OQ 去掉表格只留问题（`question_only`）；LM 只给选项（`options_only`）；SB 不给工作簿（`no_workbook`，工单 PR-C12-1 13:45 写入代码，14:20 连同测试收尾）；
   - **标签关**：真值种类与出题模块一致；LM 另要求每个答案字母占 20% ± 5%。
   - 任何一关不过，`g_self` 就是空的，这一步照常往下走，自测只用前面各步留下的题集（或者不测）。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 输入：跑题段 | `slices.json` 的 `run`（查证的泄漏筛查语料；SB 的源题） | 公开题面 + 参考答案（只给固定代码，考官看不到答案） |
| 输出：查证发现 | `<run root>/shared/research/<chain>/sources/<sha>.json`；`generate/attempt-N/research-split.json` | 发现的 `status`（如 `found`）；两半 `{g_self, g_acc}` |
| 输出：生成题 | `generate/unit.json` 的 `result.g_self`；SB 工作簿在 `generate/attempt-N/generated-G_self/<16 hex>/` | 每题 `id, task_id, benchmark, family, source_item, material, public, private{answer 或 test_files, answer_position, asset_sha256, truth, engine_qualification}, set, seed` |
| 输出：关卡与出题程序记录 | `result.gates`、`result.generator` | `fivebench-execskill-v1-generator-gates`：`generator, bench, specs[{family, material, status}], truth, band{pass_rate, in_band, direction, rounds}, shortcut{dropped, flagged_share, used}, labels{ok}, failed, admitted, kept, kept_sha256`；`fivebench-execskill-v1-generator`：`id, bench, specs, specs_sha256, gates_sha256, gates, status, rounds: [], dup_control: null, validity: null` |
| 输出：单元结果 | `generate/unit.json` 的 `result` | `mode, policy, policy_record（只存哈希）, research, split, specs_record（只留最后一次）, outcomes, generator, gates, g_self, numbered` |

```json
{"generator": "g-officeqa-2-1", "bench": "officeqa",
 "truth": {"made": 40, "kept": 38, "dropped": {}, "no_material": 0},
 "band": {"pass_rate": 0.6, "in_band": true, "direction": null, "rounds": [{"probe_items": 30, "passed": 18}]},
 "shortcut": {"probe_items": 30, "dropped": ["gen:g-officeqa-2-1:7"], "flagged_share": 0.03, "used": true},
 "labels": {"ok": true}, "failed": [], "admitted": true, "kept": ["gen:g-officeqa-2-1:1", "..."],
 "version": "fivebench-execskill-v1-generator-gates", "evidence": "pilot_real_run", "record_sha256": "<64 hex>"}
```

**上限与调用。**
- **考官调用。** 策略 1 次、出题规格最多 6 次，记进 `…:role:examiner`（每步 2.5M）。
- **查证调用。** 记进 `…:role:examiner:research`（每步 4.6M，最多 24 个请求 × 8 次）。
- **做题格。** 难度关最多 90 格，捷径关最多 60 格，记进 `<c>:xs:<bench>:<k>:examiner`（SB 3.5M、OQ 7.3M）。这个作用域还要容纳验收时 G_acc 的做题格：工单 C7e-1 已在 13:45 合入。出题程序在隔离箱里每次限 60 秒。

**现状与诚实说明。**
- **只在冒烟里走过一小段。** 冒烟 S3 只走一次 LM「derivative」族的查证加出题（至少 5 道合格题）；本节其余部分第一次真跑就是试点。
- **两种判对口径。** 难度关和捷径关按 `final.token` 判对；自测和验收按裁判 v2 的 `judge.v2.token` 判对。两者只在问答题靠 JSON 救回答案时不同。
- **G_acc 不在这里生成。** 它在验收单元里生成（见上）。v1 里 SB 没有 G_acc，可是计算稿 T4 仍按 1.33M 给它定了价。
- **预测效度没有接上。** 试点每个题库只有 1 轮，会写「无法评估」。
- **LM 的检查会话。** 工单 I1-2（一次出题只开一个检查会话）已在 14:42 打上补丁并加了测试（I1 笔记）；默认试点没有 LM 一步，本来就不影响试点。
- **空策略的后果。** 第一步没有上一轮的策略可以沿用。考官的策略回答里只要有一条不合格，整份作废，这一步就没有查证、没有生成题（真值关记 `no_items`）。这不会让这一步停下，自测照常，只是没有本题库的生成题。

代码入口：`step.py:_generate`、`step.py:_build`、`step.py:_probe_band`、`step.py:_probe_shortcut`；`examiner.py:policy_revise`、`examiner.py:research_requests`、`examiner.py:generator_write`、`examiner.py:build`、`examiner.py:gates`、`examiner.py:generator_record`；`research.py:Researcher`、`research.py:split`；`generators/`（`officeqa`、`sheet`、`livemath` 各族）。


## 6 一步的八个小步（中）：5.4 工程师改过程、5.5 自测

> 读前说明：这部分接着第 1 部分讲。每个代号第一次出现时会先用一句话解释，§13 是全部代号的总表。数字后面的括号写的是来源：
> 「登记稿 §x」指 `docs/handoff/execskill-registration-v1-20261021.md`；「计算稿」指零调用算术文件 `execskill-calc-output-20261021.txt`；
> 「裁定 hh:mm」指 `execskill-registrar-decisions-20261022.md` 里的决定（写法同第 1 部分）；「第 n 行」指裁定 14:10 补充里、也是试点运行手册阻塞表里的第 n 行。代码文件都在构建树 `skillopt/execskill/` 下。
> 这里讲的全是**设计和代码**，不是实验结果。试点还没有开始，一个真实的格都还没有跑过（见 §12）。

本节反复用到这些词，先说明：
- **包（package）**：要“进化”的技能本身。它是一组小 Python 程序，最多 24 条，源码总共不超过 64,000 字节（登记稿 §2.1）。
- **过程（procedure）**：包里的一条小程序，由工程师模型来写。
- **壳（shell）**：固定不变的外壳代码。它在做题模型（solver）调用的前后，按固定位置调用各条过程。
- **钩子（hook）**：壳里预留的 6 个固定调用点：`applies`（这条过程管不管这道题）、`before_call`（发题前写便条）、`bindings`（QA 题的计算往返）、`sheet_feedback`（表格题程序预检后写修复便条）、`alf_before_step` / `alf_after_step`（ALFWorld 每一步前后）。
- **便条（note）**：过程通过钩子写给做题模型的文字，放在固定字段里交给做题模型（第 1 部分 §3.5）。
- **登记员**：登记规则、做裁定的一方；“登记员代码”指固定不学的检查代码。
- **S / S'**：S 是父包，也就是上一步传下来的包，第 1 步时是空包。S' 是本步的候选包，等于 S 加上本步存活的改动。
- **链 G / 链 D**：两条并行的进化链，题目完全相同，只是做题模型不同。G 用 glm-5.3，D 用 deepseek-v4.1-flash-1017（登记稿 §21）。
- **bench 缩写**：SB = SpreadsheetBench（表格操作），OQ = OfficeQA（表格问答），LM = LiveMath（数学选择题），
  SQ = SearchQA（检索问答），ALF = ALFWorld（家居文字游戏）。默认试点只走 SB（第 1 步）和 OQ（第 2 步）。
- **跑题段 / 验收段**：跑题段（run slice）是本步“先跑一遍、找出失败”用的真题。验收段（acceptance slice）是本步最后裁决用的另一批真题，到 5.6 才第一次发出去。
- **单元（unit）与 attempt**：一步被切成 9 个固定的工作块，依次是 run、diagnose、generate、engineer、selftest、engineer-2、selftest-2、accept、freeze（`step.py` 的 `UNITS`）。每个单元有一把锁、编号的尝试目录 `attempt-N/` 和只写一次的 `unit.json`；attempt 是单元的一次执行，暂停后重做会新开 `attempt-N+1`。
- **格（cell）与组（arm）**：一道题 × 一个组 × 第几次运行 = 一个格，也就是一次做题，存成一条记录。组指这道题用哪个包去做（例如 S' 组、S 组）。
- **账本（ledger）与作用域（scope）**：账本是每条链一本的 token 账；作用域是账本里的一个“小钱包”。一次调用同时记在好几个作用域上，只要其中任何一个会超上限，这次调用就不放行（§9）。

### 6.1 设置：5.4 和 5.5 在哪、为什么
- **位置**：前面依次是 run（做跑题段）、diagnose（考官找失败模式）、generate（考官出练习题）。
  - 5.4：工程师模型（GLM-5.3）读本链存下的做题记录，提出最多 3 个改动。登记员代码用固定检查 C1–C9 把坏改动筛掉。
  - 5.5：用考官出的练习题，便宜地查一下 S' 有没有把东西弄坏。
- **为什么判定交给代码**：v3 里 49 个提议中有 21 个死于小格式错误（登记稿 §4.2）。所以这次改成“一个 json 块 + 每个改动一个 python 块”的固定格式，由代码而不是模型来判定。
- **为什么自测只拦“坏”**：自测题是考官生成的，不是真题，不能拿来证明“变好”。所以准确率只记录，从不拦人（登记稿 §5.5）。

### 6.2 做法：5.4 工程师（按时间顺序）
1. 取父包 S，第 1 步时是空包。取本链第 k' ≤ k 步已经封存的 run 单元做题记录（下文称“轨迹”）。
2. 组织输入（见 6.4 的表），发一次“提议”调用。回复必须正好包含一个 json 代码块 `{"changes": [...]}`，最多 3 个改动（`MAX_CHANGES`），新增或修订的每个改动再配一个 python 代码块。
3. 回复解析不出来时（no_reply、manifest_blocks:n、manifest_json、manifest_shape、code_blocks），再给一次“重提”调用，附上 `unparseable` 原因。
4. 改动有四种：
   - `new`：新增过程；
   - `revision`：修订已有过程，多一个 `revises` 字段；
   - `deletion`：删除 `{kind, id}`；
   - `narrowing`：收窄适用的 bench `{kind, id, benches}`。

   过程的 id 由登记员代码分配，格式是 `p-<bench>-<k>-<n>`，并记下来历 `{parent, revises, engineer_call}`。
5. 每个改动按下表顺序逐项检查，第一项失败就停。删除和收窄只跑 C1 和 C3。
6. 某个改动第一次失败时，给工程师一次“修复”调用 `{"request":"fix", bench, change+source, failed}`。修复必须保持同一种类和同一目标，然后从 C1 重新查；再失败就丢弃这个改动。
7. 存活的改动加到 S 上得到 S'（`package.with_`）：修订原地替换，新增追加在后面，删除的移除，并保留 `retired` 列表和 `narrowed` 表。合起来超过整包上限时，从最后一个改动开始丢，直到合法（`engineer._combined`）。
8. 没有任何存活改动时，本步提前结束，验收段不登记、不消耗（登记稿 §5.4 末条）。

| 顺序 | 检查 | 查什么 | 典型失败细节 |
|---|---|---|---|
| 1 | C1 解析 | 种类、字段、类型合法；钩子名和 bench 名都登记过；修订/删除的目标在父包里；同一目标不能被改两次 | kind / keys / types / unknown_hook_or_bench / target_not_in_parent / target_edited_twice |
| 2 | C2 代码规则 | 静态查源码：语法；模块顶层只许定义；常量大小；禁用的语句、装饰器、导入、名字、属性；禁 numpy 随机数、时钟、sympify、双下划线字符串 | syntax、import、clock、dunder_string 等 |
| 3 | C4 静态禁词（默认对所有过程都查，因为过程可能在任何 bench 上生效） | 源码任何位置都不许出现 LiveMath “更强选项”那句话（`STRONGER_OPTION`）中的任意 4 个连续词，以及 "stronger result/statement"（meta_option）；字符串常量里不许出现 OQ 的公报文件、期号、页码写法，例如 "treasury bulletin 1"、"March 1985"、"page 23"、"p. 23"（bulletin_literal，按正则匹配），也不许出现 ALF 的“容器名 + 编号”，例如 "drawer 3"（receptacle_literal） | 同左三类 |
| 4 | C3 上限 | 单条过程 ≤6,000 字节；说明 1–600 字；钩子按登记顺序排列，必须含 `applies` 且至少再有一个；标题 ≤200 字且通过词表筛查；`requests_second_call` 只能配 `bindings`/`sheet_feedback`；`state_bytes` 0–65,536；整包 ≤24 条、≤64,000 字节、每步 ≤3 处改动 | 超哪条记哪条 |
| 5 | C5 加载 | 在全新的隔离箱子进程（PYTHONHASHSEED=0）里把代码加载起来。隔离箱本身起不来不算检查失败，而是 P4 暂停（P4 = “隔离箱不可用”这类不稳定情况，登记稿 §4.4，见 §9.3） | load |
| 6 | C6 零崩溃 | 在本链全部已存的跑题轨迹上（包括更早 bench 的）重放两遍：种子 0 正序、种子 1 倒序，每遍用全新子进程。不许崩溃、谓词返回非布尔、输出形状错、状态超过申报字节、未申报的第二次调用；两遍结果的哈希必须一致 | crash:*、predicate:not_bool、output_shape |
| 7 | C4 泄漏与输出禁词 | 过程写出的便条里不能带答案，见下面的说明 | leak、meta_option |
| 8 | C7 重放测试 | 工程师为每个改动附 1–8 条“重放测试”，见下面的说明 | 测试不成立、空洞、反向测试失败 |
| 9 | C8 输出格式 | 便条里不许出现 `<answer`、`</answer`、`<action`、`</action`、`<calc`、`</calc` 或代码围栏（不重新哈希系统提示，偏差 A10-9） | 出现即失败 |
| 10 | C9 便条字段 | 重放中便条故障必须为零，故障种类包括未知字段、类型错、超上限、词表命中、超申报上限、超 bench 上限 | note_unknown_field 等 6 类 |

**C4 泄漏怎么判**：
- 查的对象：过程的说明、源码里的字符串常量（这两样对所有已有语料查），以及在轨迹上重放时写出的每条便条（只对该题所在 bench 的语料查）（`engineer.leak_check`）。
- 机械查重只保留“题目公开文字里没有”的内容。具体有：
  - 共享的 8 词片段，但去掉 ≥5% 的题目都有的模板片段；
  - 多词答案，以及长度 ≥5 字符的单词答案；
  - OQ 里有效数字 ≥3 位的数（1900–2030 年的年份不算）；
  - LiveMath 中长度 ≥4 字符的选项文字。
- 有命中时，只请一次 GLM 裁判（`leak_adjudicate`）：
  - 输入是说明、被标出的内容（截到 4,000 字）和最多 3 道撞上的题；
  - 回复必须是 `{"verdict": "yes"|"no", "reason": ≤300 字}`；
  - "no" 保留改动，"yes" 或无效回复丢弃改动；
  - 每个改动最多 2 次裁判，每个单元最多 6 次，不计入工程师的 6 次调用上限。
- SB 和 ALF 只做 8 词片段这一项（SB 对比的是任务说明，ALF 是开局观察里的任务文字；冻结的 coevo5 `leakage.py`）。LiveMath 便条里出现“更强选项”或写出选项字母，直接失败，不经裁判。

**C7 重放测试是什么**：
- 每条测试有固定字段 `id、trajectory（一个格 id）、hook、property、nonvacuity、claims_fix`。
- property 是一个小字典，例如 `{"kind": "note_contains", "value": "..."}`。可选的种类有：applies_true/false、note_contains、note_matches（1–5 个按顺序出现的字面片段）、discourage_contains/excludes、binding_equals、repair_requested、state_equals。
- 测试必须在真实重放上成立，而且不能是“空洞”的：拿掉这条过程（`withheld_expect: false`）或做了声明的变异（strip_digits / drop_exception_message / program_ok / nothing_happens）之后，测试必须不再成立。
- 至少要有一条 `claims_fix: true` 的测试，在一条失败轨迹上非空洞地成立。
- 登记员另外加两条反向测试：SB 成功轨迹上不许请求修复；ALF 成功轨迹的最后一个动作不许被劝阻。
- ALF 状态跟踪的一致率必须 ≥97%。

### 6.3 做法：5.5 自测
1. 题目：
   - 本步的 **G_self**（考官出的练习题中，过了四道关——真值、难度频段、捷径、标签这四项准入检查，见第 1 部分 5.3——按生成顺序排在前面的 ≤60 道，`G_SELF_MAX`）；
   - 更早 bench 的练习题集，每集 ≤40 道（`EARLIER_SET_MAX`，按种子标签 `execskill-v1:selftest:<bench>` 排序）；
   - G_self 只用考官研究素材的一半来出题，另一半留给 5.6 的 **G_acc**（见 §7）。
2. 组：S' 和 S 各跑 1 次，混在同一个种子顺序里发出（`_cells(..., tag="selftest")`）。
3. 拦截规则一（故障）：数 S' 的格里判分结果为 unknown_fault（因过程或执行故障而“不知道”对错）、或“本步改过的过程”出故障的格。这些格 / S' 全部格 > 1/50 就拦，也就是 60 格里有 2 格、100 格里有 3 格就拦。父包里继承来的旧过程出故障不拦。
4. 拦截规则二（格式），每个题集单独判：S' 的格式违规比例比 S 高 ≥5 个百分点（1/20），**并且**精确单侧符号检验 p < 0.05，才拦。
   - 违规的定义（`judge.format.violation`）：QA 没有可用的 `<answer>` 标签；LM 回答不是单个字母；SB 没交出程序；ALF 合法动作比例 < 0.9。
   - unknown 格的违规标记是 null；自测计数时把它当作“不违规”，但它仍留在分母里（step.py `selftest_verdict`）。
   - 门槛换成题数：S' 更好的题为 0/1/2/3 道时，S' 更差的题至少要 5/7/9/10 道，对应 p = 0.031/0.035/0.033/0.046（我按二项分布核过）。
5. 准确率（按 judge v2 判分读法算的 "pass" 比例，见 §7.4）只记录，从不拦人。
6. 一道生成题都没有时，记 `{"sets": {}, "blocked": false, "reason": "no_generated_items", "cells": 0}`，候选直接进验收（step.py `_selftest`）。SB 第 1 步能不能有练习题，取决于 PR-C61-2（SB 生成工作簿）和 PR-C12-1（SB 无工作簿捷径探针）；这两项代码已落地，待 Codex 审查和最终快照（见 §12.4）。
7. 第一次被拦时进入 engineer-2：工程师从**同一个 S** 重新提议（不是去修 S'）。它只看到计数 `previous`：
   `{"decision":"not_accepted","faults":{"selftest_fault_cells":n},"format":{"<bench>":{"worse_items":n}}}`，
   然后做 selftest-2。再被拦，本步结束，验收段不消耗（登记稿 §5.5 末句）。
8. 提前结束的原因只有三种：`no_surviving_change`、`no_surviving_change_after_selftest`、`selftest_blocked_twice`（step.py `_candidate`）。

### 6.4 输入 / 输出
| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 父包 S | `step.json` 的 `package_sha256` → `<chain root>/packages/<sha>.json` | 过程列表；第 1 步为空 |
| 本链轨迹 | `<chain root>/s<k'>-<bench>/run/attempt-N/trajectories/<cell id>.json`（k' ≤ k，已封存） | 按白名单取字段，删掉每次调用的 `system` 文本；拒收 expert_plan、gamefile、game_file、extra |
| 给工程师看的轨迹 | 本 bench 父包组格里的前 12 个失败和前 6 个成功（`ENGINEER_SHOWN`），按种子 `execskill-v1:engineer-shown:<单元>` 排序 | 失败轨迹带 `reference`；超过 220,000 字节就从尾部删，删完仍超就暂停 |
| 参考答案 | step.py `_references` | 只转发私有 `answer` 文本或 `answers` 列表。SB 题存的是 `test_files`/`answer_position`，所以**SB 的参考答案永远到不了工程师** |
| 检测器计数 | `detectors.counts(detectors.diagnosis(parents))` | 只有机械类别：QA 的 no_answer_tag、json_answer_untagged、multiple_answers、truncated_or_suspected、empty_reply；SB 的 no_program、excel_formula_only、fence_glued、program_exception_on_public_input |
| 泄漏语料 | step.py `_corpora` | 本 bench 跑题段，加上更早步的跑题段 |
| SB 输入工作簿 | step.py `_inputs_dirs` | 只给本步 SB 轨迹用，供 C6/C7 重放 |
| 工程师记录 | `<chain root>/s<k>-<bench>/engineer/unit.json`（第二遍是 `engineer-2/`）→ `result.engineer`、`result.candidate_sha256` | bench、k、step、label、parent_sha256、prompt_sha256、proposals、changes、kept、candidate_sha256、procedures、calls |
| 过程与候选包 | `<chain root>/procedures/<sha>.json`、`<chain root>/packages/<sha>.json` | 按内容哈希命名，只写一次；`accepted_at` 一直为 null |
| 自测结论 | `<chain root>/s<k>-<bench>/selftest/unit.json`（或 `selftest-2/`），格在 `selftest/attempt-N/cells/` | 见下面的 JSON |
| 提前结束的本步结论 | `<chain root>/s<k>-<bench>/step.json` | `decision: "not_run"`、reason、`evidence_kind: "selection"` |

工程师回复和自测结论的骨架（字段名是代码里的真名，值是占位）：
```json
{"changes": [{"kind": "new", "description": "<≤600 字>", "hooks": ["applies", "before_call"], "header": "<≤200 字>",
  "max_note_chars": 800, "requests_second_call": false, "state_bytes": 0, "excluded_benches": [],
  "replay_tests": [{"id": "t1", "trajectory": "<cell id>", "hook": "before_call", "claims_fix": true,
    "property": {"kind": "note_contains", "value": "<字面片段>"},
    "nonvacuity": {"mutation": null, "withheld_expect": false}}]},
 {"kind": "deletion", "id": "p-spreadsheetbench-1-2"}]}
```
```json
{"fault_cells": 0, "inherited_fault_cells": 0, "candidate_cells": 60, "fault_share": 0.0, "fault_blocks": false,
 "sets": {"officeqa": {"items": 60, "format_gap": 0.0, "worse": 0, "better": 0, "p_sign": 1.0, "blocks": false,
                       "accuracy": {"S'": 0.5, "S": 0.5}}},
 "blocked": false, "cells": 120, "reason": null}
```

### 6.5 上限与调用
- **工程师调用**：
  - 标签为 `engineer/<单元>/propose`、`/repropose`、`/fix/<n>`；
  - 每个单元最多 5 次（1 次提议 + 1 次重提 + 每个失败改动 1 次修复），硬上限 `ENGINEER_CALLS = 6`，按单元标签分别计数；
  - 一步里 engineer 和 engineer-2 加起来最多 10 次工程师调用，外加最多 12 次泄漏裁判。
- **模型设置**：GLM-5.3，M = B = 16,384（M 是请求里允许的最大输出 token，B 是账本按多大来预留），读超时 900 s，推理档 low，输入 ≤220,000 字节（`protocol.py` `ROLE_*`）。
- **作用域**：`<c>:xs:<bench>:<k>:role:engineer`（`<c>` 是链名 G 或 D）。每步每 bench 上限 1.5M，与泄漏裁判和 5.7 的描述员共用；全链 GLM 总上限 30M（登记稿 §9.3）。
- **一次工程师调用要预留多少**：最多 968,264 token = 4 × (220,000 + 5,170 + 512 + 16,384)，其中约 5,170 是工程师系统提示的字节数（这条“乘 4”的预留规则见 §9.2）。
  - 所以按最大请求算，只有当这个作用域已结算的花费 ≤ 约 0.53M 时，下一次调用才放得进去；请求小一些，预留也小一些。放不进去就是预算暂停。
  - engineer-2 实际要装多少还没量过。
  - 登记稿 §5.4 写的是“每步 ≤6 次调用”，代码却按单元计数，engineer-2 另有 6 次；S-E6 的 GLM 外推也只按每步工程师 6 次、泄漏 6 次算。这处出入目前没有见到裁定（未核实是否有意）。
- **自测**：不调 GLM，只花做题模型的钱。
  - 作用域 `<c>:xs:<bench>:<k>:selftest`，上限 SB 2.6M、OQ 6.6M。
  - 每遍最多 SB 120 格（60 × 2 组）、OQ 200 格（(60+40) × 2）。
  - 预计每遍 SB 0.35–0.67M、OQ 1.04–2.07M；两遍最坏 SB 1.33M、OQ 4.14M（计算稿 T4）。
  - 如果按链 G 自己的预留重算，OQ 上限应是 6.8M；但主人的规定是登记过的上限不重算。

### 6.6 现状
- **已实现并有单元测试，但只用假模型（FakeGLM、FakeDocker）跑过**：`test_execskill_engineer` 7 条、`test_execskill_replay` 13 条，step 测试覆盖了 `no_change` 和 `blocked_twice` 两种提前结束，自测规则也有专门测试。
- **从来没有用真 GLM 跑过**：冒烟 S3 会做第一次真实的工程师调用（一步），试点是第一次在真数据上跑 C1–C9 和自测。
- **不保存的东西**：工程师和裁判的原始回复不落盘，只有 S3 的 `role-calls.json` 会留。
- **已知的薄弱点**：
  - SB 失败轨迹不带参考答案；
  - 到 OQ 那一步，C6 重放更早的 SB 轨迹时不带工作簿；
  - engineer-2 的过程 id 可能与第一遍重复。
- **依赖刚落地的代码（PR-C61-2、PR-C12-1）**：自测在 SB 第 1 步能否“有题”取决于这两项。代码在 13:40–14:20 由 P2-A1、P2-A2 落地，有单元测试；P2C 在开发树上跑的全套 route-B 测试（1,183 条）已包含并通过；还差一轮 Codex 审查和最终快照。

代码入口：step.py:_candidate、step.py:_engineer、engineer.py:run / check / leak_check / fix / _combined、replay.py:zero_crash / run_tests / negative_tests、package.py:with_、step.py:_selftest / selftest_verdict / _sets

## 7 5.6 验收：一批新题只决定一次

### 7.1 设置：这一步在哪、为什么
- **位置**：S' 通过 5.5 自测之后。这是整步里**唯一做裁决**的地方，用的是一直没发出过的验收段：SB 60 题、OQ 50 题（`protocol.py` `SLICES`）。
- **一批题只用一次**：一轮跑完，无论结果是收下、否决还是未决，被用到的题都算消耗掉（登记稿 §3.4）。只有一种情况不消耗，就是下面的 `not_run_small_astar`。
- **为什么要这么多组**：S' 赢了父包 S，不一定是过程内容好，也可能只是多塞了一段像样的文字、模型本身有随机波动，或者机器和网络出了问题。所以一轮里同时跑好几个对照组，每个组排除一种解释（登记稿 §5.6、§6.1–§6.6）。
- **大致流程**：先封存一切 → 被改到的题少于 30 道就不跑 → 否则所有组的格混成一个种子顺序发出 → 按 J1–J7 七条规则只裁决一次（§7.4 逐条说明）→ 冻结 S'，或把 S' 存档。

### 7.2 做法一：封存（零模型调用，`acceptance.prepare`）
封存的顺序是：供体语料 → 生效计划（哪条过程在哪道题上生效）→ 假过程 → 各组的包 → 真实便条长度 → P_y → P_i → G_acc → `accept/sealed.json`。这个文件只写一次，之后每次 attempt 都以它为准。

**A 和 A\***：A 是整个验收段。A\* 是其中“真被这次改动碰到”的题，判定条件如下：

| 改动种类 | 这道题算进 A\* 的条件 | 孪生格种类 |
|---|---|---|
| 新增 p | p 在 S' 里对这道题生效（`applies` 为真） | withhold（拿掉 p） |
| 修订 p → p' | 旧 p 在 S 里生效，或新 p' 在 S' 里生效 | withhold |
| 删除 p | p 在 S 里生效 | restore（放回 p） |
| 收窄 p | p 在 S 里生效 | restore |

- |A\*| < 30 时，结论是 `not_run_small_astar`：不跑，也不消耗任何题（`MIN_ASTAR = 30`，登记稿 §3.3，Codex F1）。
- 为什么至少要 30 道：按 Codex 提出的一种偏斜零假设做精确枚举（计算稿 T9，不是随机模拟），名义 5% 的单侧 t 检验在 30 道题时实际误判率是 12.3%（有大量平局时可到 16%）；41 道时 6.6%，150 道时 5.9%。也就是说，即使有 30 道，这个检验也偏松。这一点要如实知道。

**供体（donor）和配对安慰剂 P_y**：
- 供体是父包在跑题段上的做题轨迹：SB 31 题 × 2 次 = 62 条，OQ 24 题 × 2 次 = 48 条。
- 把改动过的过程放到这些供体的输入上重放，得到“供体语料”。新增和修订的过程用 S' 里的新版本；删除和收窄的过程用父包里的原版本。
- 配对（yoke）：A\* 的题和供体各按种子 `execskill-v1:yoke:<单元>` 排序，第 k 道题配第 (k mod 供体数) 个供体（`router.yoke`）。
- P_y 的包：在 S' 的基础上，把删除或收窄的过程按父包原样放回去，再把每条改动过的过程换成一个“假过程”。假过程不看本题内容，只输出配对供体（另一道跑题段的题）经过筛查的输出，并把长度调到本题真实便条长度的 ±20% 以内：太长就截短，太短就接上同一供体后面的输出补长，但不超过这条过程申报的便条上限（`placebo.py`）。从验收题上只读取一个长度。
  - `sheet_feedback` 和 ALF 钩子的长度目标改用供体语料的中位数。
  - 计算往返一律回“未计算”。
  - SB 修复是否触发，由真实钩子的一次隐藏影子运行决定。
  - ALF 被劝阻的命令按种子 `execskill-v1:discourage:<单元>:<格>` 抽。
  - 调用次数不做配平，两组差超过 10 个百分点会被标出来。
- 用意：如果 S' 赢只是因为“多了一段看起来相关的文字”，那 P_y 也会赢。

**无关文字安慰剂 P_i**：只用于 SB/OQ/LM。用 v3 的 8 段对照文字（俳句、十六进制颜色、菜谱、拉丁铭文、打油诗、开尔文、棋步、编织），按 sha256 mod 8 选一段，剪成相同长度。只用来描述，不做裁决。

**孪生格（twin）**：
- withhold:<p> = S' 拿掉 p；restore:<p> = S' 把 p 放回。
- 先排本步改动过的过程：在 A\* 里生效题 ≥10 道的才配孪生格（`TWIN_MIN_FIRED`）；但如果本步唯一的改动是一个“新增”，就不给它配，因为这时 S'−S 本身就是它的作用。
- 然后**总是**再排从别的 bench 继承来、本步没碰过、在 A\* 里生效题 ≥15 道的旧过程（`INHERITED_TWIN_MIN_FIRED`），按生效题数从多到少（`router.plan`）。
- 在种子 `execskill-v1:withhold:<单元>:<过程>` 的顺序里，取前 floor(n/2) 道生效题配孪生格，每道题最多 2 个孪生格。
- 孪生格只算 tau（这条过程单独的贡献），**从不参与裁决**。生效题为 25/50/100/200 道时，分辨率大约是 19/14/10/7 个百分点。

### 7.3 做法二：组、交错发送和分块
| 组（arm） | 用什么包 | 计分侧（L：unknown 算错；H：算对，见 §7.4） | 作用 |
|---|---|---|---|
| S' | 候选包 | L | 被裁决的对象 |
| S | 父包 | H | J1 的对照 |
| C | 卡片组：空包，只有任务卡 | H | 只描述；当 S 在本 bench 上没有任何过程时（例如第 1 步，`card_is_parent`），C 和 S 文字完全相同，C−S 就是 J6 的同文对照 |
| P_y | 配对安慰剂 | H | J2 的对照 |
| P_i | 无关文字安慰剂 | H | 只描述 |
| S_dup | 和 S 完全相同的包 | H | J6 同文对照。只在考官的生成器被收下且 k > 1 时跑，所以试点里只可能出现在 OQ 第 2 步。它会多带来约 1% 的“未决”概率和 0.98–3.17M token（计算稿 T4） |
| withhold:<p> / restore:<p> | S' 拿掉或放回 p | L | 只算 tau |

- **题集**：
  - 真题集：S'、S、C、P_y（再加 P_i、S_dup、孪生格）× 运行次数（SB 2 次、OQ 4 次）。
  - G_acc 集：S'、S、P_y、C（再加 S_dup），各 1 次。
  - LM 另有 J7 探针集：S' 和 C。
- **交错**：同一块里的所有格，按 sha256 `[20261021, "execskill-v1:round:<单元>:<块>", 题集, 题, 次, 组]` 排成一个顺序，绝不按组排（登记稿 §6.2）。
  - 不在 A\* 里的题直接释放，记 `routed_not_dispatched`；A\* 的题在第一个格发出前就标成 `dispatched`。
  - 一个 16 线程的池负责发送，机器级的并发槽为 glm 10、deepseek 8、表格原生引擎 3、活隔离箱 6（每个 SB 单元最多占 2 个）。
- **分块**：SB 1 块；OQ 2 块，每块 25 题，两块之间至少隔 7,200 s（`BLOCK_GAP_SECONDS`，登记稿 §3.3）。统计时按块分层。

### 7.4 做法三：每题得分、检验、J1–J7
- **每题得分**（`stats_ext.item_scores`，登记稿 §6.3）：
  - L 侧（S'、孪生格）= 通过次数 / 运行次数，unknown 算错；
  - H 侧（S、C、P_y、P_i、S_dup）= (通过 + unknown) / 运行次数，unknown 算对，unknown_fault 也按 unknown 处理。
  - 这样设计是为了**对 S' 不利**：S' 要赢，不能靠对照组的“不知道”。
  - 所有组都没拿到任何回复的题（`shared_unanswered`）退出所有对比。
- **检验**：对每道题的得分差做配对 t 检验（比较同一批题上两组差值的标准方法）。均值是所有题的总平均；方差用各块内部（减去本块均值后）的残差合起来算；自由度 = 题数 − 块数；取单侧 p（p 越小，越不像是碰运气）（`stats_ext.paired_t`）。
  - “整批平均差” = 差值之和 / |A|，分母是整个验收段，不只是 A\*。所以只改到少数题的效果会被稀释。
  - 分析题数不多于块数时，代码报错 “Too few answered items for the t-test”，进入暂停，并且这一轮算终局（见 7.5）。
  - 敏感性分析（bootstrap 重抽样 10,000 次、符号翻转、Wilcoxon，都是不依赖正态假设的备用检验）只记录，不裁决。

**J1–J7 逐条说明**（`acceptance.decide`）：
- **J1 比父包好**：S'−S 单侧 p ≤ 0.05，**并且**整批平均差 ≥ 2 个百分点（`MIN_WHOLE_BATCH = 1/50`）。
  - 如果“安慰剂有害”，也就是 P_y−S 按供体聚类做的 bootstrap 95% 区间上界 < 0，门槛收紧到 0.025（`HARMFUL_SHAM_ALPHA`）。
- **J2 比安慰剂好**：S'−P_y 单侧 p ≤ 0.05。安慰剂有害时 J2 自动算过；这时如果收下，理由写的是“只证明了优于父包，内容或篇幅的解释没有排除”。
- **J3 故障少**：故障题数 × 50 ≤ |A|，即 SB（60 题）和 OQ（50 题）最多容忍 1 道故障题，2 道就否决（`FAULT_SHARE_MAX = 1/50`）。
  - 故障题指：改动过的过程在路由时出错，或者在 S'/P_y 的格里执行出错、复跑得到 unknown_fault。
- **J4 格式不变差**：S' 有格式违规的题数 ≤ S 的违规题数 + max(2, ceil(0.02 × |A\*|))。
- **J5 仪器正常**：不过就判“未决”并暂停。要求：
  - 每组基础设施 unknown ≤ 10%；
  - 推理档不一致 ≤ 1%，所有真实格合起来算（这个标记只出现在链 D，链 G 上不会触发）；
  - 共同未答题 ≤ A\* 的 10%；
  - 开工平衡：各组“实际开工减去排定开工”的延迟中位数相差 ≤ 本轮时长的 1/20。登记稿原来写的“各组开工时间中位数之差”只记录、不判，因为在均匀交错下它多半会偶然超标（工单 A9-2；`acceptance._balance`，裁定 C5-5 定它为唯一的这项检查）；
  - OQ 两块的间隔满足 7,200 s。
- **J6 同文对照无差异**：不过就判“未决”并暂停。每一对文字完全相同的组（C−S、S_dup−S）都要双侧 p ≥ 0.01（`DUP_ALPHA`）。两个一样的包测出了差异，说明仪器有毛病。
- **J7 选项捷径（只用于 LM 正式链）**：只给选项、不给题干的探针上，如果 S'−C ≥ 10 个百分点且 p < 0.05，就算走捷径，否决（`META_PROBE_GAIN`）。没有探针格时为 null；试点没有 LM 步，J7 不出现。

**裁决**：
- J5 或 J6 不过 → `undetermined`（未决），理由是 “instrument guard failed (J5[, J6]); the run pauses, the batch is consumed but undecided”；
- 否则 J1/J2/J3/J4/J7 有任何一条不过 → `reject`，理由 “failed: J1, …”；
- 都过 → `accept`。

`decision.json` 在结算之前写好。结算规则：
- 收下或否决：A\* 和探针题改记 `decided`；
- 未决：题保持 `dispatched`，单元以 `Pause("acceptance_undetermined")` 暂停。

### 7.5 暂停、只重做一块、“跑完的轮是终局”
- **只重做一块**（主人决定 #15，工单 C7c-2/C7e）：
  - 已完成记录覆盖了全部格的块直接复用；
  - 开过头的块整块重做，记在 `<c>:redo` 和 `…:accept:attempt-N` 上，上限取 min(验收上限, 14.8M)；
  - 从没开始过的块仍记在首跑作用域上；
  - `_provenance` 检查每个格恰好出现一次、每块只来自一个 attempt；
  - SB 只有 1 块，所以 SB 的重做就是整轮重做。
- **重做次数**：每个单元最多重做 2 次（`MAX_REDOS = 2`）。第 1 次由 14.8M 重做备用金预付（`PREFUNDED_REDOS = 1`）；第 2 次需要主人先决定加上限（`raise_cap`，见 §9）。
- **跑完的轮是终局**（裁定 13:5x C7e-2）：
  - 一轮如果在最后一个格之后才暂停（`acceptance_undetermined`，或 `decide` 自己报错），就是终局，**不写 `recovery.json`**，直接报告主人。重做只会复用全部块，再停一次，白白耗掉一次重做。真想重来，要走 v1.1 规则。
  - 代码现状：判定函数 `acceptance.finished_round` 已写好，`run_execskill.py recover` 已接上并会拒绝这种 attempt（裁定 14:10 第 17 行）。P2C 构建者已在开发树里做完并加了单元测试，开发树上全套 route-B 测试 1,183 条通过（P2C 进度记录）；还没经过 Codex 审查，也还没进最终快照。

### 7.6 做法四：G_acc 和 15 分钟序列（都只描述，不裁决）
- **G_acc 怎么来**：
  - 考官研究素材在 5.3 被对半分开。G_acc 用的是另一半（g_acc 那半），不是用验收题本身出的；A\* 只决定 G_acc 的题数，并按位置一一配对（裁定 C1-3）。
  - 生成器 id 为 `g-<bench>-<k>-1`，题号接在 G_self 后面，按种子 `execskill-v1:examiner-probe:<生成器>:g_acc` 排序。
  - 题数上限：OQ 50、LM 100；SB 在 v1 里没有 G_acc。
  - G_acc 题不过频段、捷径、标签这三关，可能是空的。
- **G_acc 怎么跑**：S'、S、P_y、C（再加 S_dup）各 1 次，混进本块的顺序里。费用记在**考官作用域**，每个 attempt 都一样（C7e-1，代码 13:45 由 P2-A2 落地，开发树上的全套 route-B 测试已过，待 Codex 审查和最终快照）。
  - 最多 250 格、2,932,990 token。
  - OQ 验收上限 29.5M 对最坏 19.34M 有 1.53 倍余量；如果 G_acc 也记在验收作用域，余量只有 1.32 倍。
  - `decide` 只读真题集的格，所以 G_acc 从不影响裁决。
  - 它本来用于“预测效度”（生成题上的涨跌能否预测真题上的涨跌），但那需要 ≥8 轮，而且代码没接线，所以试点里一律“无法评估”。
- **15 分钟序列**（工单 PR-F2-1，代码 13:45 由 P2-A2 落地，开发树上的全套 route-B 测试已过，待 Codex 审查和最终快照）：
  - 从本轮第一次派发开始，每 900 s 一个窗口；按题集和组分别记格数、答案标签比例、平均可见输出 token、短回答比例。
  - “短回答”指平均输出 token 不到同题集同组第 0 窗口中位数的 1/4。
  - 记录里写着 `decides: false`。重做过的轮从第一次派发算起，中间暂停的时间表现为空窗口。

### 7.7 输入 / 输出
| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 验收段 A | 本步 `slices.json` 中的 `accept` | SB 60 题 × 2 次（1 块）；OQ 50 × 4（2 块） |
| 供体 | 父包组在本步跑题段的轨迹 | SB 62 条、OQ 48 条 |
| 封存记录 | `<chain root>/s<k>-<bench>/accept/sealed.json`（只写一次） | chain、bench、step、unit、runs、A、blocks、freshness、mde_registered、dup、card_is_parent、shams、packages、plan、corpus、placebo_y、placebo_i、g_acc、seals{candidate, parent, donor_corpus, placebo_y, placebo_i, plan_sha256, twins_sha256, g_acc_sha256} |
| 格与轨迹 | `accept/attempt-N/cells/<cell id>.json`、`accept/attempt-N/trajectories/<cell id>.json` | `cell{id, unit, arm, benchmark, task_id, run, set, block}`、`judge`、`final`、`dispatch_ts`、`finish_ts` |
| 裁决记录 | `accept/attempt-N/decision/decision.json` | 见下面的 JSON |
| 单元结论 | `accept/unit.json` → `result` | decision、reason、decision_sha256、sealed_sha256、cells、dup、g_acc、fault_items、violating_items、validity、provenance、reused、redone |

```json
{"A_star": 41, "A_star_rooms": null, "analysed": 40, "shared_unanswered": ["<item>"],
 "donors": {"corpus_sha256": "<64 hex>", "reuse_max": 2},
 "contrasts": {"S'-S": {"mean": 0.0, "p_t": 0.5, "whole_batch": 0.0, "ci95": [0, 0], "sensitivity": {}},
               "S'-P_y": {}, "S'-C": {}, "S-C": {}, "P_y-S": {"ci95": [0, 0], "by_donor": {}}},
 "guards": {"J1": {"p_t": 0.5, "alpha": 0.05, "whole_batch": 0.0, "ok": false}, "J2": {}, "J3": {}, "J4_items": {},
            "J5": {"infra": {}, "reasoning": 0.0, "unanswered": 1, "balance": {}, "block_gap": {}, "ok": true, "pause": false},
            "J6_dup": null, "J7_meta": null},
 "placebo_rule": "informative", "second_call_rates": {}, "repair_call_rates": {}, "worst_delivery_rates": {},
 "twins_cap": {}, "twins": {}, "provenance": {}, "series": {"window_seconds": 900, "decides": false, "sets": {}},
 "decision": "reject", "reason": "failed: J1"}
```

### 7.8 上限与调用
- **验收作用域**：`<c>:xs:<bench>:<k>:accept`，上限 SB 8.3M、OQ 29.5M（计算稿第 82–83 行）。
- **最坏排程**：SB 240 个无过程格 + 600 个带过程格，OQ 200 + 1,400。
  - 最坏花费 SB 5.13M、OQ 19.34M（计算稿 T4）。
  - 预计 SB 1.23–4.10M、OQ 5.15–16.17M。
- **检出力**（真实效果 +3/+5/+10 个百分点时，J1 和 J2 两条一起通过的概率；不含 J3–J7，并假设 A\* = A、安慰剂效应为 0）：SB 0.07/0.17/0.62，OQ 0.09/0.24/0.80（计算稿 T2，第 19–20 行）。
  - 最小可检出效果约 SB 12.1、OQ 10.0 个百分点。
  - 如果真实效果是 +5 个百分点，默认试点两步都什么也收不下的概率约 0.63（敏感性范围 0.27–0.82；计算稿 T3，登记稿 FE-F9）。
  - 如果一条链做 5–9 次独立裁决、而且真实效果全为零，至少错收一次的概率是 0.23–0.37（计算稿第 132 行）。
- **不调 GLM**：验收只花做题模型的钱。

### 7.9 现状
- **已实现并有单元测试，但只用假模型跑过**：acceptance 27 条（含 P2C 新加的 2 条终局轮测试）、placebo 7 条、stats_ext 14 条、router 5 条、端到端 11 条（按测试文件里的 `def test_` 计数）。
- **从未在真实模型上跑过**：一次真实的验收轮、暂停、重做、冻结都还没有发生过，试点会是第一次。
- **刚落地，待审查**：C7e-1（G_acc 记考官作用域）和 PR-F2-1（15 分钟序列）的代码在 13:45 由 P2-A2 落地，有单元测试，开发树上的全套 route-B 测试已过；还差一轮 Codex 审查和最终快照。
- **开发树里已做完、待 Codex 审查和最终快照**：“跑完的轮是终局”的代码拦截（第 17 行，P2C；全套测试已过）。
- **从不裁决的部分**：孪生格 tau、P_i、G_acc、15 分钟序列、敏感性分析都只是描述；C 组也只描述，只有当 C 与 S 文字相同时（如第 1 步）才作为 J6 的同文对照。

代码入口：step.py:_accept / _g_acc / _blocks、acceptance.py:prepare / schedule / dispatch / runner / decide / settle / earlier_blocks / finished_round / series、router.py:plan / yoke / draw_twins、placebo.py:build_y / build_i、donors.py:donor_corpus / pair、examiner.py:g_acc

## 8 5.7 冻结并传下去、5.8 最后读测试集

### 8.1 设置
- **5.7 冻结**：紧接在裁决之后。
  - 收下：S' 加上冻结的文字说明，成为下一步的父包。
  - 否决：S 原样传下去，S' 存档。
  - 未决：会先暂停，等主人决定（§9）。
- **5.8 读测试集**：每条链只做一次，在两步都走完之后。这是整个试点里唯一的“泛化”证据；在它之前的一切裁决都只算“挑选”证据（`evidence_kind: "selection"`）。
- **为什么要“文字孪生”**：同一条过程，用代码执行，和写成一段文字说明直接给做题模型看，哪个更好？测试时专门留一个文字对照组 T_F 来回答这个问题（登记稿 §5.7、§8.1）。

### 8.2 做法：冻结（5.7）
1. **收下时**，本步每条新增或修订、并且带便条钩子的过程，各调用一次 GLM “描述员”，每步最多 3 次，费用记在工程师作用域。
   - 输入 `{"procedure": {description, hooks, header, source}, "target_chars": <长度中位数或 null>}`，长度来自在父包组跑题轨迹上的重放。
2. **后处理**：
   - 含词表词的句子删掉；
   - 在 min(上限, int(1.2 × 目标)) 以内找句末截断，没有目标时在 min(上限, 600) 以内截断；
   - 打标签：within（在范围内）/ clipped（被截短）/ short（不到目标的 0.8 倍，照样保留）/ no_target；
   - 不调用或失败的原因：no_note_hook（没有便条钩子，不调用）、no_reply、screened_empty。
3. **冻结包 F** = `package.with_describer(S', 说明)`：只要至少有一条可用的文字说明，记录就变了，哈希也跟着变；一条可用说明都没有时 F 就是 S'，哈希不变（step.py `_freeze`）。所以 `step.json` 里同时有 `candidate_sha256`（封存的 S'）和 `package_sha256`（冻结后的包）。
4. **适用范围**：新过程默认对所有 bench 生效。“放宽范围”不是一种改动；范围只能被以后另一个经过正式收下的删除或收窄改动缩小。
   - 下一步的工程师只看到计数：`{decision, faults, format}`（主人决定 #17）。
5. **否决或没跑**：不调用描述员。S 传下去，S' 记在 `archived`（提前结束、没有候选包时为 null）。否决时 A\* 的题已经消耗，A 里 A\* 以外的题退回供给池；没跑（`not_run_small_astar` 或提前结束）时一道题都不消耗。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 冻结结论 | `<chain root>/s<k>-<bench>/freeze/unit.json` → `result` | 收下：`{accepted: true, package_sha256: <F>, archived: null, descriptions}`；否决：`{accepted: false, package_sha256: <S>, archived: <S' 或 null>, descriptions: []}` |
| 文字说明 | 只存在 `freeze/unit.json` 的 `result.descriptions` 里 | procedure、procedure_sha256、text、text_sha256、prompt_sha256、request_sha256、target_chars、chars、cap、band、dropped_sentences、reason |
| 本步记录 | `<chain root>/s<k>-<bench>/step.json` | chain、k、bench、step、parent_sha256、candidate_sha256、package_sha256、decision、reason、decision_sha256、fault_items、violating_items、units、evidence_kind |

### 8.3 做法：最后读测试集（5.8）
1. **F = C 就不读**：两步都没收下任何东西时，F 就是空包 C，`test-read.json` 记 `"not_read"`，理由 “F = C: nothing was accepted (§8.1)”。
2. **主人同意（唯一要主人亲手做的一步）**：
   - 主人写 `shared/consent.json`：`{test_evaluation: true, sheet_test_qualification: <bool>, multi_arm_arms: ["F","C","P_F","T_F","twins"], by: "owner", date, note}`；
   - 用 `consent --root $PILOT` 检查，应输出 `{"test_read": "valid"}`；
   - `consent` 检查只要求 `sheet_test_qualification` 是布尔值，但读 SB 测试集前要先做一次引擎资格检查，这一项不是 true 时 SB 读取会报错停下（`evaluation._sheet_qualification`），所以运行手册 §7.1 的模板写的是 true；
   - **现状**：主人已在 10/22 15:01 亲手写好 `/data/execskill-20261021-pilot/shared/consent.json`（252 字节，sha256 前缀 2748d886fcb1b207），`consent --root` 检查结果为有效（裁定 15:1x）。如果 v1.1 把试点挪到新目录，要在新目录里重写；
   - 链在开始读之前查一次同意书。没有时，代码写 `read-waiting.json`（kind `consent_missing`），链暂停、`run` 以退出码 3 结束，不开任何读取 attempt；主人写好后，主代理重新启动 `run`，不需要 `recovery.json`（裁定 14:10 第 9 行；P2C 已在开发树做完、全套测试已过，待 Codex 审查和最终快照）。在第 9 行修好之前，晚到的同意书会让两条链留下最多 10 个暂停的读取 attempt；同意书既然已提前写好，默认试点里不会再遇到这种情况（除非换目录重来）。
3. **预算闸门**：两条链各自的 `<c>:solver` 和 `<c>:test` 剩余额度，都要 ≥ 1.3 × 读取估算才开读（`TEST_START_FACTOR`，`chain.read_budget`）。
   - 估算 = ceil(比例 × Σ n_b × (card_b + 4 × f_b × proc_b))：n_b 是 bench b 的读取题数，card_b、proc_b 是无过程格和带过程格的每格成本，比例来自 S-E6，f_b 是过程生效比例的假设（本 bench 1.0，相似 bench 0.7，其他 0.5）。
   - 按高锚点算是 54,409,087，乘 1.3 后需要 70,731,813，99M 的读取上限还剩 28.27M 余量。
   - 链 G 的估算还要再乘 max(1, 链 G 实测成本系数)。估算记录 `test-read-estimate` 由 `run_execskill.py test-read-estimate` 从通过的冒烟结果写一次（第 8 行；P2C 已在开发树做完、全套测试已过，待 Codex 审查和最终快照）。
   - 重新启动时会重新套用整条 1.3 倍规则：如果这时已经花掉超过约 28.3M，就会触发 `test_read_budget` 暂停（工单 P2C-2，未关）。
4. **金丝雀**：用来查测试题有没有混进训练材料。
   - 共 25 条：S0 记录里 SQ 和 ALF 共 10 条，读取记录里 OQ、LM、SB 共 15 条；每条 ≥24 字符，只存长度和 16 位十六进制哈希前缀。
   - 和训练题重复的金丝雀只在读取记录里跳过（PR-C31-3，P2-A3 在 14:21 做完并有单元测试，待 Codex 审查和最终快照）。
   - 每个读取单元开始前和结束后各扫描一次，命中就记 `canary_hit`。
5. **读什么**：SQ 400、OQ 172（按种子分成 2 块、每块 86，两块依次发出，中间不等待；登记稿 §8.1 只要求分两段、按段分层，没有规定间隔，evaluation.py `_blocks`）、LM 125、SB 279、ALF 134 道，每题 1 次。
   - C 每道题都跑；F、P_F、T_F 和孪生格只在过程生效的题上跑；过程不生效（结构性为零）的格直接共用 C 的格。
   - 五个读取子进程并行：SB 独占内存锁，ALF 共享这把锁。
   - 只保存哈希，临时存储读完即删；基础设施失败超过 10% 就暂停。
6. **测试时的组**：F（最终包）；C（空包 `empty(step="<c>/card")`）；P_F（用收下那一轮封存的供体语料做假过程）；T_F（文字孪生，见下）；孪生格（种子 `"test/<bench>"`，不含链名，所以 G 和 D 拿掉的是同样的那一半题）。
   - **T_F** 把冻结的文字说明放在同一个位置：
     - `bindings`：文字加上 `<calc>` 邀请，但不给数值；
     - `sheet_feedback`：文字加上报错信息和一次修复机会；
     - ALF：每一步都给这段文字。
   - 两个已知缺口：A10-3 还没解决（没有文字说明的过程会显示它自己的输出）；±20% 的长度带只限制了上限。
7. **解封**：需要满足四个条件：
   - 所有链都结束；
   - 有 `shared/owner-continuation.json`（`{by, date, decision: continue|stop, note}`；运行手册 §7.3：主人只看学习侧记录做决定，主代理照原话写一次）；
   - 整个运行根目录扫描干净，或者主人放行（`recover … --decision "release <64 位哈希>"`）；
   - 如果要贴“confirmatory（确认性）”标签，解封前必须有经主人批准、用 `seal-addendum` 封好的正式补充 `shared/formal-addendum.md`（封存记录是 `shared/formal-addendum.json`；正文由主代理以登记员身份起草）。

   标签：准时决定继续 → `interim_read_addendum_before_unseal` / confirmatory；晚了才决定继续 → `interim_read_without_prior_addendum` / repeated_test_development；决定停止 → `read_after_stop_decision` / repeated_test_development。
8. **读数的固定顺序**（`readout.readout`）：
   - q1_home：在学过的 bench 上 F−C，单侧，按学过的 bench 数做 Holm 校正（同时检验几个 bench 时收紧门槛，防止碰运气）；
   - q2_similar：相似 bench，只描述（估计值、95% 区间、每条过程的 tau、启用率）。登记稿 §8.2 写明测试集每题 1 次时分辨率很粗（OQ 约 6.6–7.7、LM 约 10–11 个百分点），“相似也涨”认证不了；默认试点里 OQ 是学过的 bench，相似 bench 是 SQ 和 LM；
   - q3_noninferiority：不相似 bench 上 F−C 的等权平均，两种读法——“不利读法”（全部题，F 的 unknown 算错、C 的 unknown 算对）和“完整题读法”（只算两组都没有 unknown 的题）——都要求单侧 95% 下界 > −5 个百分点，才写“不劣成立”；F 在这些题上的生效率不到 10% 时只记 `cannot_act_by_construction`（`readout.q3_noninferiority`）；
   - code_vs_text：F−T_F；
   - placebo：F−P_F；
   - labels：给每条过程按优先级打一个主标签（harmful_elsewhere、general、home_benefit_established、cannot_act_elsewhere、no_measurable_effect）；
   - format_withholding；
   - arm_table。

   默认 L = {SB, OQ} 时，相似 = {SQ, LM}，不相似只有 {ALF}，Q3 的检出力约 0.37，所以“未确立”是最可能的读法。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 同意书 | `<run root>/shared/consent.json`（主人写） | 见上 |
| 读取结论 | `<chain root>/test-read.json`、`<chain root>/test/<bench>/` | not_read 或读取闸门 `{estimate, factor, cap_check, used, need}` |
| 金丝雀 | `<run root>/shared/test-canaries.json`、`shared/test-read-canaries.json` | 长度 + 哈希前缀 |
| 根目录扫描 | `<chain root>/root-scan/attempt-N/{scan.json, status.json}` | hits、hits_sha256、canaries_sha256 |
| 解封标记 | `<chain root>/unsealed.json` | 标签 |
| 读数 | `$OPS/pilot-readout/readout-<c>.json`（必须是新目录） | evidence_kind "generalization"、q1_home、q2_similar、q3_noninferiority、code_vs_text、placebo、labels、format_withholding、arms |

```json
{"test_evaluation": true, "sheet_test_qualification": true,
 "multi_arm_arms": ["F", "C", "P_F", "T_F", "twins"], "by": "owner", "date": "YYYY-MM-DD", "note": "<主人备注>"}
```

### 8.4 上限与调用
- **描述员**：每步最多 3 次 GLM 调用，记在 `<c>:xs:<bench>:<k>:role:engineer`（1.5M）。**读取**：记在 `overall`、`<c>:solver`（180M）和 `<c>:test`（99M）上，ALF 读取每条链要 1.8–6.5 小时。
- **根目录扫描**：最多 5 个进程，留出 2 个 CPU。25.5 MB 用单进程扫了 105 s；v3 的根目录有 1.5 GB。

### 8.5 现状
- **已实现并有单元测试，只用假数据跑过**：冻结、描述员、读取、解封、读数。描述员从没调用过真模型，测试集从没读过。
- **刚做完、待审查**：evaluation.py 的 PR-C31-3（金丝雀跳过、主人放行、进程池），P2-A3 在 14:21 做完，单元测试通过；还差 Codex 审查和最终快照。
- **开发树里已做完、待 Codex 审查和最终快照**：chain.py 的第 8 行（读取估算记录、链 G 系数）和第 9 行（`read-waiting.json`），由 P2C 构建者完成并加了单元测试，开发树上全套 route-B 测试已过（P2C 笔记与进度记录）。另开了工单 P2C-2：重新启动时读取闸门会再套一次，哪怕读取已经花掉一部分。
- **仍然开着的缺口**：A10-3；T_F 长度带只限上限；Q3 只覆盖 ALF。

代码入口：step.py:_freeze、describer.py:describe / screened / clipped、package.py:with_describer、chain.py:read_consent / read_budget / read_estimate_record / evaluate、evaluation.py:consent / release_check / unseal、readout.py:readout

## 9 预算、账本、暂停与恢复

### 9.1 设置
- **一条链一本账**：每次模型调用都要花钱。账本防止“跑飞”，每条链一本：`<run root>/shared/ledger-G` 和 `ledger-D`，各有 `events.jsonl` 和 `state.json`。
  - 一条链的账本停了，另一条链照常跑（登记稿 §9.3）。
  - 账本代码用的是冻结的 coevo5 `Budget`，事件类型有 declare、reserve、settle、refuse、halt、resume、raise、orphan。
- **暂停从不自动恢复**（登记稿 §9.4）：每次暂停都要主人决定。决定只能依据基础设施事实，不能依据分数。

### 9.2 做法：预留、结算、限流
1. **预留**：调用前先按最坏情况预留 4 × (请求字节数 + 512 + B) 个 token。只有当某作用域的已结算 + 进行中 + 这次预留 ≤ 上限时才放行，而且这次调用记账的**每一个**作用域都要满足。放不下时，如果超限的作用域里还有别的调用的预留没结算，就排队等它们结算后再试；只有超限作用域里已经没有进行中的预留、仍然放不下时，才拒绝并进入预算暂停（`BudgetStop`，冻结的 coevo5 `budget.py` `reserve`）。
2. **结算**：
   - 一次调用最多尝试 4 次（1 次加 3 次重试）。带用量回执的那次按回执记；其他失败的尝试按完整上界记账，但在生成前就被拒绝的（4xx 状态或连不上）记 0（coevo5 `ledger.settle`）；
   - 没有回执的调用按整笔预留记账；
   - 所以账本偏保守。cal-1 的例子：账本记了 27.48M，实际计费 17.6M，真实用量 14.0M。
3. **熔断**：回执报告的用量超出了预留时的假设（输入超过请求字节数 + 512，或输出超过 B，记作 `reported_usage_beyond_reservation_bound`），或者账本写入失败被隔离（quarantine）时，**这条链的整本账**停下（halt）。预算不够只是暂停，不是熔断。恢复要主人执行 `resume-ledger`；熔断前已经开始的 attempt 要重做。
4. **限流**：链 G 每次发送至少要预留 4 × (512 + 65,536) = 264,192 token。SB 跑题作用域只有 1.2M，同时最多放得下 4 次发送（请求越长，放得下的越少），其余的排队等待。等待没有超时，也不算暂停。

| 作用域（每条链；`<c>` 是 G 或 D） | 上限 | 说明 |
|---|---|---|
| `overall` | 210M | 两条链合计 420M |
| `<c>:solver` | 180M | = 两步 61.3M + 读取 99M + 重做备用 14.8M = 175.1M，向上取到 5M 的倍数 |
| `<c>:test` | 99M | 测试读取 |
| `<c>:redo` | 14.8M | 重做备用金 |
| `<c>:glm` | 30M | 工程师、考官、研究、描述员等方法角色 |
| `<c>:confirm` | 1.1M | 首次调用确认（第 7 行，P2C 已在开发树做完、全套测试已过，待审查）；这次调用同时记在 `overall` 和 `<c>:solver` 上，和普通格一样（裁定 15:0x） |
| SB 第 1 步：run / examiner / selftest / accept | 1.2 / 3.5 / 2.6 / 8.3M | `<c>:xs:spreadsheetbench:1:<kind>` |
| OQ 第 2 步：run / examiner / selftest / accept | 2.3 / 7.3 / 6.6 / 29.5M | `<c>:xs:officeqa:2:<kind>` |
| 每步每 bench 的角色：engineer / examiner / research | 1.5 / 2.5 / 4.6M | `…:role:engineer`（泄漏裁判和描述员也记在这里）、`…:role:examiner`、`…:role:examiner:research` |

- **上限公式**：1.5 × 最坏排程在高锚点下的花费 + 一笔预留 R（SB 520,192、OQ 389,120、ALF 146,432），向上取到 0.1M（`protocol.py` `STEP_CAPS`，计算稿 T6）。
- **每格成本锚点（低/高）**：SB 2,561/4,273，OQ 5,246/7,927，SQ 1,535/3,400，LM 1,602/3,969，ALF 每局 36,000/45,000；带过程的组再乘 1.25 或 1.6（登记稿 §9.1）。
- **估算**：每条链做题 23.1–85.6M（最坏 103.5M），GLM 3.3–13.8M。
- **一次调用记在哪些作用域上**：
  - 首跑：`overall`、`<c>:solver`、`<c>:xs:<b>:<k>:<kind>`；
  - 重做（attempt N ≥ 2）：`overall`、`<c>:solver`、`<c>:redo` 和 `…:<kind>:attempt-N`，**不再**记在 `<c>:xs:<b>:<k>:<kind>` 上；验收重做时只有被重做的那一块这样记，从没开始过的块仍记在首跑作用域上（`budgets.solver_scopes`）；
  - G_acc：记考官作用域；
  - 读取：`overall`、`<c>:solver`、`<c>:test`；
  - 角色调用：`overall`、`<c>:glm`、`<c>:xs:<b>:<k>:role:…`；
  - 冒烟：用自己的账本 `smoke:solver`、`smoke:glm`（S3 另有 `smoke:glm:s3`），S1 用 `smoke:probe`。

### 9.3 暂停的种类
| 种类 | 什么时候出现 |
|---|---|
| budget | 预留放不进上限（超限作用域里已没有进行中的预留可等） |
| assumption / ledger | 账本熔断后（例如回执超出预留假设），进行中的单元以 assumption 停下 / 账本写入失败、被隔离 |
| configuration、exception、package、consumption、containment | 配置或检查不符、代码异常、包校验失败、同一条链的另一个单元要用已被占用的题、测试读取的临时内容没被关住 |
| sandbox / cleanup | 隔离箱起不来（P4）/ 清理没有确认 |
| infrastructure_incomplete | 跑题单元里某组的基础设施 unknown > 1/10（62 格里 7 格、48 格里 5 格、24 格里 3 格；`rounds.guard`）；测试读取单元超过 10% 也是这个暂停（验收轮里同样的情况走 J5，判未决） |
| acceptance_undetermined | J5 或 J6 不过 |
| awaiting_owner_decision / redo_limit | 暂停的 attempt 还没有主人决定 / 重做次数用完 |
| cap_check | 链 G 成本核对越界（见 9.5） |
| test_read_budget / consent_missing / canary_hit | 读取预算不够 / 没有同意书（第 9 行，P2C 已在开发树做完、全套测试已过，待审查）/ 金丝雀命中 |
| no_qualified_test_items、qualification_paused | SB 测试题的引擎资格出问题 |
| first_call_unconfirmed / first_call_not_confirmed | 链的首次调用确认失败（第 7 行，P2C 已在开发树做完、全套测试已过，待审查）/ 冒烟 S3 里第一次 GLM 回复没确认 |
| child_failed_before_its_attempt | 读取子进程在开出 attempt 前就退出了 |

**从不暂停的情况**：过程故障（P1、P2）、unknown_fault（P3）、第二次调用回退（P5）、超名义长度（P7）和截断，只记录。P6（链 D 推理档不一致）会自动重发；输出超过 B 会让账本熔断。

### 9.4 谁来恢复、怎么恢复（从不自动）
- **重做**：主人决定后，执行 `run_execskill.py recover --attempt <attempt 目录> --decision "<主人原话>"`，写入 `recovery.json` = `{"by": "owner", "date": "YYYY-MM-DD", "decision": "…"}`，再重新启动 `run`，开出新的 `attempt-N+1`。
  - `recover` 只检查目录名是 `attempt-*` 且单元还没完成，**不检查**这个 attempt 是否真的暂停过。
  - `recover` 会拒绝“跑完的验收轮”（第 17 行，P2C 已在开发树做完、全套测试已过，待审查）。
  - 对根目录扫描的 attempt，可以写 `release <哈希>` 放行。
- **其他命令**：熔断的账本用 `resume-ledger` 恢复；终止只能对空闲的链执行；加上限**没有命令行**，要用一行 Python：`Budget(budgets.ledger_root('$PILOT','<c>')).raise_cap('<scope>', <cap>, deviation='…')`。
- **退出码**：`run` 只用 0（完成）和 3（暂停或终止）；5（有暂停的 attempt 在等主人决定）只出现在子进程命令 `step-unit`、`evaluate-unit` 和读数命令 `report` 上（`report` 第一次解封前要扫描运行根目录，命中且在等主人决定时返回 5，其他暂停返回 3；`runcli.py`）；其他退出码（通常是 1）是单元以外的崩溃。

### 9.5 链 G 的成本核对（第 18 行）：如实说明风险
- **核对什么**：链 G 第一个跑题单元结束后，做一次零调用核对（登记稿 §9.3）。
  - 每格成本 = `G:xs:spreadsheetbench:1:run` 的已结算额 / 62，系数 = 每格成本 / 4,273；
  - 链 G 每个作用域（GLM 角色的作用域和首次调用确认的 `G:confirm` 除外）的预测值 = ceil(上限 / 1.5 × 系数)（step.py:386-404）；
  - 结果写进 `G/cap-check-G.json`（主人加上限后重跑、上限变了的再核对另写成 `cap-check-G-<n>.json`，读取闸门取编号最大的一份，chain.py:201-221、312-321），任何一个作用域越界，就以 `Pause("cap_check")` 暂停链 G。链 D 不受影响。
- **加上限解不开**：上限出现在不等式两边，所以这其实只是一个门槛：每格不超过 6,409.5 个账本 token，即 62 格合计不超过 397,389。出路只有两条：终止链 G，或者在新目录里用 v1.1 上限重来。
- **风险多大**：v1 的数据是每格平均 2,762（n = 181）和 3,534（n = 2,255）个账本 token；2,466 次调用里有 6 次打满 65,536，24 次 http_400。
  - 预计系数在 0.65–0.83 之间，大约要出现 ≥3 次按完整上界记账的失败才会触发。
  - 风险低，但不是零。

```json
{"run": "<run id>", "chain": "G", "ok": true, "per_cell": 0.0, "anchor_high": 4273, "scopes": {"G:solver": {"cap": 180000000, "projected": 0}}}
```

### 9.6 输入 / 输出与现状
| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 账本事件日志 | 每条链的 `Budget` 写 `<run root>/shared/ledger-<c>/events.jsonl`；冒烟只有一本 `$SMOKE/shared/ledger/`（`budgets.ledger_root`） | 每行一个事件，都有 `time` 和 `event`：declare（scope、cap）、raise（scope、from、cap、deviation）、reserve（id、amount、scopes、label、owner）、refuse（amount、scopes、label、exceeded；账本已停时为 halted）、settle（id、charged、reserved、overrun、scopes、label、detail，越界时加 breach）、orphan（id、charged、scopes、label、reason）、halt（reason、label；隔离时另有 close）、resume（decision） |
| 账本状态 | 同目录 `state.json`（事件日志的缓存，中断后按日志补齐） | offset、caps（现行上限）、declared（登记上限）、settled（各作用域已结算）、open（进行中的预留）、halted、halts |
| 账本快照 | `monitor` 用 `Budget.snapshot()` 现读，不另存 | 每个作用域 {cap、settled、open}；账本停了时另有 halted |
| 暂停记录 | `…/<unit>/attempt-N/status.json`；代码异常时另有 `diagnostics.log`（traceback） | 记录类型 `unit-status`：status = "paused"、kind、reason、cell |
| 主人的决定 | `…/attempt-N/recovery.json`，由 `recover` 照主人原话写一次 | by = "owner"、date、decision |

```json
{"time": 0.0, "event": "settle", "id": "<uuid>", "charged": 0, "reserved": 0, "overrun": 0, "scopes": ["overall", "G:solver", "G:xs:spreadsheetbench:1:run"], "label": "<调用标签>", "detail": {"error_type": null, "usage": {}, "attempts": []}}
```

- `detail` 只存错误类别、三个用量数和每次尝试的 HTTP 状态或异常类名，不存回复文字（coevo5 `calls._detail`）。
- **现状**：账本本身是冻结的 coevo5 `Budget`，以前的 coevo5 真实链和 cal-1 用过；路线 B 的作用域、上限、暂停和恢复接线已实现、有单元测试，但只用假模型跑过，还没在路线 B 的真实运行（冒烟或试点）里用过；`<c>:confirm` 和链 G 的读取闸门（第 7、8 行）P2C 已在开发树做完、全套测试已过，待 Codex 审查和最终快照。

代码入口：budgets.py:chain_caps / ledger_root / first_call_caps、step.py:cost_projection、chain.py:cap_check / read_budget、units.py:solver_endpoint、scripts/run_execskill.py:recover / resume_ledger

## 10 冒烟测试（裁剪后：S0、S1、S2、S3、S-E6）

### 10.1 设置
- **目的**：在花大钱的试点之前，先用很少的钱确认机器、隔离箱、网关、账本和每个角色都“能跑通”。冒烟只查能不能跑，不查效果好不好。
- **裁剪**：主人在 13:0x 说“是不是其实可以不用做那么多冒烟测试”，于是 S-N1（噪声锚点）和 S4（恢复演练）被去掉。代码里这两个阶段还能跑，但不再是通过条件（`smoke.py` `SMOKE_STAGES`）。
- **顺序与地点**：S0 → S1 → S2 与 S3 并行 → S-E6 → 汇总。冒烟根目录是 `/data/execskill-20261021-pre/smoke`。
- **用什么模型和题**：冒烟的做题模型只用 deepseek，GLM 只在 S3 里作为角色出现。真题只有 SQ 280 道和 ALF 12 局（`protocol.py` `SMOKE_REAL_ITEMS`）：SQ 里 S2 用 20 道；原来划给 S4 的 60 道中，S3 的跑题单元只用前 20 道（`S4_SLICES["run"]`）；其余 40 道和原来划给 S-N1 的 200 道在裁剪后的冒烟里都不发出（共 240 道）。ALF 的 12 局里 S2 用 6 局，另 6 局原属 S-N1，不发出。OQ、LM、SB 各用 20 道手工夹具题（fixture）。

### 10.2 各阶段做什么、怎样算过
| 阶段 | 目的 | 通过条件 | 调用与上限 |
|---|---|---|---|
| S0 | 零调用总检查，14 行：pytest、equivalence（空卡片等价）、exceptions、ledger、sandbox、escape_probe（越狱探针）、measurements、determinism、replay、supply、sheet、registry、codex_fixtures、leftovers | 14 行全过，并量出隔离箱限额 | 0 次调用 |
| S1 | 探测网关和 deepseek 的真实行为，6 行 a–f：确认首个回复、长度测试、M = 16,384、8 路并发、推理档检查（ControlClient）、网关；提示开销 ≤512 | 6 行全过；决定链 D 走分支 E 还是 N：B = 2 × 名义 M（E），或 max(4 × M, ceil(1.5 × 最长输出))（N） | ≤60 次（每个 attempt 41 次），自己的 0.5M 账本 |
| S2 | 用 deepseek 真跑一遍做题路径：组 C、X（夹具包）、P 加孪生格，先跑 1 个确认格 | 格式合格比例 ≥9/10，且 X/P 不比 C 低超过 1/20；≥300 个生产回执、0 次推理泄漏；每个钩子至少一次无故障；账本结清；没有残留；只有夹具里故意的崩溃故障；持有原生引擎槽时不发模型调用 | `smoke:solver` 14M，预计 1.92–5.67M |
| S3 | 第一次真实调用 GLM-5.3 的各个角色：先做泄漏裁判（必须确认成功），再做一步工程师、一次检测器编写和验证、一次 LiveMath 研究加出题（概念 "derivative"，≤8 次调用，≥5 道核对过的题）、一次描述员调用 | 每样都跑通即可，不看好坏 | GLM 上限 2M（`S3_GLM_CAP`；登记稿 §10 写的 0.5M 是估计，裁定 14:3x 定为 2M），超限在发出前就变成预算暂停 |
| S-E6 | 零调用的成本外推：每格成本只取 S2 的格；账本/实际比例的分母是冒烟账本结算过的全部做题格（S2 的格，加上 S3 跑题单元和确认格）；GLM 用 S3 各角色调用的实测 | 两条链的每个做题作用域（含测试读取和重做备用）都要 ceil(每格 × 比例 × 最坏格数 + 下一笔预留) ≤ 上限，下一笔预留 = 4 ×（实测最大请求字节 + 512 + B）；比例 ≤ 1.5；GLM 按每步每类调用的登记最多次数外推（工程师 6、泄漏 6、描述员 3、考官 9、研究 192） | 0 次调用 |

补充说明：
- **S3 的跑题单元**用的是 SQ 题：20 道 × 1 次 = 20 个格，外加本进程的 1 个确认格（`smoke_roles.own_run`）。裁定 14:4x 已明确登记的就是这个数，14:3x 原文里的“约 60”作废。
- **S-E6 的 above_high 标记**（每格成本 > 1.25 × 高锚点）在代码里不会让 S-E6 失败，只有试点运行手册的出发检查会因它停下。
- **S-E6 的估价方式**：链 G 用 deepseek 的每格成本估价，OQ、LM、SB 用夹具题的成本估价，所以只是占位估计。
- **S0 量出的限额**（工单 A5-1）：
  - 进程内存上限 RLIMIT_AS = max(2,048 MiB, 向上取整(2 × VSZ, 256 MiB))，VSZ 是实测的进程虚拟内存；
  - 帧大小 = max(1 MiB, 向上取整(2 × 最大视图, 1 MiB))；
  - 内存守卫要求 ≤ 0.7 × 可用内存，不够时先把每次调用的槽从 4 降到 2，再把活隔离箱从 6 降到 4；原生峰值超过 2 GiB 时，原生槽从 3 降到 2。
  - 已知缺口：每次调用槽和活隔离箱的降档只记在 `s0-limits.json` 里，不会带进运行（清单没有槽位字段，只有原生槽 3→2 会生效，`manifest._slot_sizes`）；守卫也是在降档之后才判。10/22 开发树上的 S0 自测量到守卫余量约 6.8 倍，所以眼下不碍事；真正的冒烟 S0 还没跑。

### 10.3 输入 / 输出
| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 冒烟规格 | `$SMOKE/smoke.json` | 阶段列表、清单哈希；S-N1 不在列表时 `noise_anchor_reason` 记裁剪原因 |
| S0 结果 | `$SMOKE/s0/s0-<行>.json`、`checks.json`、`s0-limits.json`、`$PRE/s0-pins.json`（`{limits, measured}`） | 每行的 passed 与细节；越狱探针记录在 `$SMOKE/s0/s0-escape_probe.json` |
| S1 探测 | 探测根目录 `$PRE/probe` 下的 `attempts/attempt-<n>.json` | 各行结果、分支 E/N、`longest` |
| 阶段记录 | `$SMOKE/stages/<阶段>.json` | stage、spec、result（S-E6 里有 `per_cell`、`ratio`） |
| S2、S3 单元 | `$SMOKE/units/S2/`、`$SMOKE/units/S3/`（S3 另存 `role-calls.json`） | 格、轨迹、角色调用 |
| 汇总 | `$SMOKE/smoke-result.json` | `{spec, passed, required, stages: {S0: "pass", …}}` |

```json
{"spec": "<64 hex>", "passed": true, "required": ["S0", "S1", "S2", "S3", "SE6"], "stages": {"S0": "pass", "S1": "pass", "S2": "pass", "S3": "pass", "SE6": "pass", "SN1": "not_required", "S4": "not_required"}}
```

### 10.4 现状
- **已经做过的**：只有零调用的容器检查（10/22 12:2x）和夹具干跑。S1、S2、S3、S-E6 都还没有真正跑过。
- **已知问题**：`make-manifest` 在不给 `--s0-pins` 时会抛出裸 KeyError（`pins.pop("limits")`），所以 S0 的钉住文件实际上是必需的。
  - 原先的另一个问题（`smoke-runbook.md` 13:01 版过时）已解决：I1 在 14:30–14:42 按裁剪后的五个阶段重写了它，写明 `--control-cells` 和 `--noise-anchor` 都不给。
- **已做完、待审查**：I1 第 2a、2b (a) 阶段（约 14:32、14:57）做完了裁剪后的阶段、表格引擎和 LiveMath WorkerChecker 接入 `services_of`、金丝雀命令、S3 跑题单元、S3 的 2M 上限、S-E6 的 GLM 外推（I1 笔记，单元测试通过）。
- **还没做**：I1 第 2b (c) 阶段：旧的手工 `smoke --stage S2/S3/SE6` 路径只许用于 S0 和 S1、零调用演练用的 `probe --fake`、运行手册第 140 行接受同意书（裁定 15:0x、15:1x）。

代码入口：smoke.py:s0 / s1_probe / run_probe / s2_solver / s3_roles / se6_cost / summary、smoke_roles.py（S3）、s0.py（S0 各行）、scripts/run_execskill.py:smoke-make / smoke-run / probe / smoke-summary / make-manifest

## 11 试点怎么启动和看进度

### 11.1 设置
- **默认试点**：第 1 步 SB，第 2 步 OQ，链 G 和链 D 并行，最后各读一次测试集（登记稿 §11）。
  - 两条链用完全相同的题，各自记在自己的消耗命名空间里，所以两条链的结果是**复现**，不是两份独立证据。
  - 题量就是全部合格题：SB 91 道（跑题 31 + 验收 60），OQ 74 道（跑题 24 + 验收 50）。
- **地点**：在 dl 机器上执行，不需要 `proxy_on`，因为客户端自带网关并设了 `trust_env=False`。
- **主人授权**：主人 13:2x 说“不用，你直接开试点就行”，所以冒烟通过之后，启动不需要主人再动手。
- **常用目录变量**：`SRC=/data/execskill-20261021-source`（代码快照）、`PRE=/data/execskill-20261021-pre`、`SMOKE=$PRE/smoke`、`PILOT=/data/execskill-20261021-pilot`（运行根）、`PM=/data/execskill-20261021-pilot-manifest.json`（清单）、`OPS=/data/execskill-20261021-ops`（操作员文件，权限 700）。

### 11.2 做法：操作顺序（来自 `pilot-runbook.md`；核对时手册已更新到 15:28 版）
1. **出发检查**（零调用）：
   - `$OPS` 权限为 700；`$PM` 还不存在；
   - `smoke-result.json` 显示通过，而且要求的阶段正好是那 5 个；
   - `consent --root $SMOKE` 显示排除同意有效；
   - `leftovers` 干净，`monitor` 正常；
   - `verify-snapshot` 写出 `$OPS/pilot-provenance.json`。

   遇到下列情况要停下来问：有要求的阶段没过；above_high 为真；分支 N 看到超过 B 的输出；有残留。
2. **生成读取估算和钉住文件**：先用 `test-read-estimate --smoke $SMOKE --out $OPS/test-read-estimate.json` 写出读取估算（只写一次）；再写 `$OPS/pilot-pins.json`（用 'x' 模式写，只能写一次），生成器会按同一公式复算估算，并核对它和冒烟清单一致（手册 §3.3–3.4）。
3. **生成清单**：`make-manifest --out $PM --pins … --exclusion-root $SMOKE --s0-pins $PRE/s0-pins.json`（它还会写一次 `$PILOT/shared/test-canaries.json`），然后核对清单里的代码表、环境、隔离箱、客户端、任务卡等 12 项都和冒烟清单相同，上限等于 `budgets.caps()`。
4. **网络检查**：`curl` 经网关、`--max-time 30`。任何 HTTP 状态码都说明线路和 TLS 是通的；超时才是网络故障，不能说明密钥有问题。
5. **启动**：
   - 写好 `$OPS/pilot-run.sh`，先开 tmux 会话 `execskill-pilot-D`；
   - 等到 `$PILOT/D/confirm.json` 出现（链 D 的首次调用确认通过）或 D 的日志出现 EXIT 行，再开 `execskill-pilot-G`（手册 5.2–5.3）；
   - 只有最终快照里没有第 7 行代码时（要登记员同意），才退回旧办法：链 D 的第一个跑题 attempt 出现约 5 分钟后，看 `D:solver` 已结算 > 0、没有熔断、日志里没有 EXIT 行，再开 G。
6. **一次 `run` 依次做的事**（`chain.run`）：
   1. 校验清单（链还没开始时校验不符，就拒绝运行、什么都不写）；
   2. 写 `chain.json`，并在账本上声明上限（含 `<c>:confirm`）；
   3. 首次调用确认：先发一次做题调用，确认拿到登记模型的真实回复，写 `confirm.json`；失败就写 `confirm-failed-<n>.json`，以 `first_call_unconfirmed` 暂停，不开任何单元（`chain.first_call`，第 7 行，P2C 已在开发树做完、全套测试已过，待审查）；
   4. 跑 SB 各单元（持机器级内存锁，G 和 D 的 SB 单元轮流跑）；链 G 在自己的 SB 跑题单元一结束就做成本核对（step.py 调 `chain.cap_check`）；
   5. 跑 OQ（验收分两块，间隔 ≥2 小时）；
   6. F = C 时只写 `test-read.json`（not_read）；否则先查同意书（`read_consent`），再过 1.3 倍预算闸门（`read_budget`），然后读测试集；
   7. 写 `chain-complete.json`。

   每个单元开始前都会重新校验钉住的文件；文件有变化，链就终止（`manifest_mismatch`）。
7. **启动后**：更新 `docs/project-status.md`，用平实的中文向主人报告，不提交、不推送。
8. **盯进度**：每 15–30 分钟从 Mac 发一次 ssh，只看 EXIT 行和 tmux 会话。看到 EXIT 时再跑 `monitor`、账本过滤（LEDGERS）和“等主人决定的暂停 attempt”列表。这些输出都不显示分数。
9. **恢复、重做、终止、加上限**：只在主人做出决定之后执行（§9.4），绝不放进循环里自动做。

| 名称 | 从哪来 / 存在哪（路径模式） | 格式与关键字段 |
|---|---|---|
| 运行日志 | `$OPS/pilot-<c>-run-<n>.log` | START/EXIT 行；结束时的 JSON `{"status": "complete" / "paused" (kind, reason, unit) / "terminated"}`；EXIT 0 表示完成，3 表示暂停或终止，其他（通常是 1）表示单元以外的崩溃 |
| 链状态 | `$PILOT/<c>/chain.json`、`chain-complete.json`、`chain-terminated.json` | 链开始 / 结束 / 终止 |
| 单元与步 | `$PILOT/<c>/s<k>-<bench>/<unit>/unit.json`、`step.json` | 单元完成 / 本步封存 |
| 暂停的 attempt | `…/<unit>/attempt-<N>/status.json`、`diagnostics.log`、`recovery.json` | kind、reason、traceback；主人的决定 |
| 链 G 成本核对 | `$PILOT/G/cap-check-G.json` | ok、per_cell、每个作用域的预测值 |
| 账本 | `$PILOT/shared/ledger-<c>/` | 用 `monitor` 读 |
| 子进程日志 | `$PILOT/shared/host_only/diagnostics/child-*.log` | step-unit 和 evaluate-unit 子进程 |
| 消耗记录 | `/data/execskill-history/consumption/<c>/<bench>.jsonl` | 命名空间 G 和 D |

```json
{"status": "paused", "kind": "budget", "reason": "<原因>", "unit": "G/s1-spreadsheetbench/run"}
```

### 11.3 只有主人能做的事
- **亲手做的只有一件**：写测试读取同意书 `shared/consent.json`。主人已在 10/22 15:01 写好，检查有效（裁定 15:1x）；只有试点换到新目录时才要重写。
- **其余要主人拍板、由主代理照原话记录的决定**：重做、终止、第二次重做、加上限；恢复熔断的账本；链 G 成本核对越界后怎么办；未决的验收轮、金丝雀命中；继续还是停止、正式补充。
- **主人做决定只看基础设施事实**，不看分数。

### 11.4 上限与耗时
- **花费**：两条链合计 overall 上限 420M；预计做题 46.2–171.2M。
- **时间**：全程约 1–2 天；第 1 步大约要翻倍，因为 SB 单元必须轮流跑；每次 OQ 验收 ≥2 小时；ALF 读取每条链 1.8–6.5 小时。

### 11.5 现状
- **试点的东西几乎都还不存在**：运行根目录里只有主人写的 `shared/consent.json`，没有清单，没有账本。两份手册都还没执行过。
  - 运行手册 §2 第 140 行的出发检查（`test ! -e $PILOT || find $PILOT -type f`，14:27 版仍要求运行根不存在、重试时只许有 `shared/test-canaries.json`）要改成也接受 `shared/consent.json`，这是裁定 15:1x 交给 I1 2b (c) 的后续工作，尚未完成。
- **手册与代码的差距**：运行手册 15:28 版已把第 7、8、9、17 行标为“在开发树里由 P2C 关闭”；开发树上全套 route-B 测试 1,183 条已通过（P2C 进度记录），但还要过一轮 Codex 审查并进入最终快照；P2C 另开了工单 P2C-1（单独跑 `step-unit` 会绕过首次调用确认，手册从不这样启动链）和 P2C-2（见 §8.5）。
- **出发前还缺的**：最终快照之前要先完成全套测试、一轮 Codex 审查和提交，还有引擎资格（`$Q23`，任务 #13）。

代码入口：scripts/run_execskill.py:verify-snapshot / make-manifest / consent / run / monitor / recover、chain.py:run_manifest / first_call / cap_check、step.py:learn

## 12 现在做到哪了、已知风险

### 12.1 设置
这一节是按 10/22 约 15:00 的代码和笔记写的清单（核对时又按约 15:30 的构建笔记和运行手册更新过），说明哪些已经能用、哪些只是纸面设计。登记稿事先写明，最可能的结果是两步都什么也没收下（见 §7.8）。

### 12.2 已实现、有单元测试，但只用假模型、假容器跑过
- **已经写完并有单元测试的部分**：跑题、考官、工程师 C1–C9、自测、验收（含重做）、冻结、测试读取、解封、读数、账本、链。
- **已经实际做过的**：10/22 12:2x 的零调用容器检查通过；主人的排除同意书 10/22 09:18 写好并有效（哈希前缀 77872f24418fd20f）；主人的测试读取同意书 10/22 15:01 写好并有效（哈希前缀 2748d886fcb1b207，裁定 15:1x）；几次“用完即弃”的演练（I1 导出、P2-A1 的 23/23 对照、OPS1 干跑）。

### 12.3 从来没有在真实数据上跑过
- **跑题路径**：没有任何真实模型跑过。最早的真实使用是 S3 的跑题单元（20 道 SQ）。
- **第一次真跑要等到试点的部分**：考官的出题策略调用、频段和捷径探针、OQ/SB 出题、研究对半分、G_acc、验收轮、暂停与重做、冻结、描述员、测试读取。
- **第 1 步 SB 的跑题段只有任务卡**：父包是空的，所以那 62 个格不含任何过程。试点里第一批真正带过程的格出现在第 1 步的 5.5/5.6 和第 2 步的跑题段（在这之前，冒烟 S2 的 X/P 组会先用夹具包跑带过程的格）。

### 12.4 正在修和待审查的工单
- **已落地、待一轮 Codex 审查和最终快照**（P2C 在开发树上跑的全套 route-B 测试 1,183 条已包含它们并通过）：PR-C61-2（SB 生成工作簿的 `asset_sha256` 和公式缓存，P2-A1）、PR-C12-1（SB 无工作簿捷径探针，P2-A2）、C7e-1（G_acc 记考官作用域，P2-A2）、PR-F2-1（15 分钟序列，P2-A2）、PR-C31-3（evaluation.py 的金丝雀跳过、主人放行、进程池，P2-A3），以及 I1 第 2a、2b (a) 阶段的冒烟改动（裁剪后的阶段、`services_of` 接入表格引擎和 LiveMath WorkerChecker、金丝雀命令、S3 跑题单元、S3 的 2M 上限、S-E6 的 GLM 外推）。
- **还没做**：I1 第 2b (c) 阶段（见 §10.4）；登记员要求在 P2C 和 2b (c) 都落地后，在新拷贝上跑全套测试和决定性演练（裁定 15:0x）。
- **第 7、8、9、17 行**：首次调用确认、读取估算、`read-waiting.json`、终局轮拦截。P2C（phase-2c 构建者）已在开发树的 protocol.py、budgets.py、chain.py、acceptance.py 和 run_execskill.py 里做完，并加了单元测试；开发树上全套 route-B 测试 1,183 条通过（P2C 进度记录），Codex 审查和最终快照还没做。新开工单 P2C-1、P2C-2 未关。
- **最终快照上的引擎资格**（`$Q23`，任务 #13）：还没做。
- **讲解文档顺带发现的试点缺口（裁定 15:5x，R1–R7）**：写这份文档的六个读代码代理发现了几处会影响 SB → OQ 试点的问题，已交 I1 在新拷贝全套测试之前逐条核实、确认后修复：R1 SB 失败题的参考答案从没传给工程师（`step._references` 只转发 `answer`/`answers`）；R2 到 OQ 那一步，C6 重放旧的 SB 轨迹时不挂载输入工作簿，改 SB 过程必然因 `FileNotFoundError` 失败；R3 SB 上的 `bindings` 钩子仍会附加精确计算邀请，但 SB 从不做计算往返；R4 考官策略里只要有一条非法请求就整份作废，而 SB 上的 `parameter_choice` 天生非法，所以要在请求里写明每个 bench 允许的请求种类；R5 试点里不保存角色的原始回复，改为每个单元写 `role-calls.jsonl`；R6 五个小问题（计算接受 − × ÷、门槛统一用 v2 计分、`recover` 只认真暂停的尝试、`make-manifest` 缺 `--s0-pins` 时给出清楚报错、重做后的成本外推）；R7 工程师预算作用域：一次满尺寸请求预留约 0.97M，1.5M 的作用域只在已结算不超过约 0.53M 时放得下，可能让一步中途暂停。R7 由 P2C 只读计算，登记员再按数字决定。

### 12.5 仍然开着的问题（不挡试点，但要知道）
- **题和读取**：SQ 的验收尾段没接线（step.py），冒烟的 280 道 SQ 里有 240 道在裁剪后的冒烟里不发出（原 S-N1 的 200 道和原 S4 的后 40 道），但已登记为冒烟用题、以后的运行根也不能再用；S0 的金丝雀不跳过与训练题重复的文字，只有读取记录跳过。
- **代码与登记稿的出入**：
  - `sandbox/client.py` 第 94 行的注释说帧上限是最大视图字节的 4 倍，登记的 A5-1 规则和 `s0.limits` 用的是 2 倍（只是注释写错）；
  - ALFWorld 数据准备只数到 6 种任务类型，登记稿写的是 7 种前缀（登记稿本来就要求建设时用代码重数）；
  - SB 上如果有过程实现了 `bindings`，壳会给做题模型加上“可以写 `<calc>`”的邀请，但 SB 的做题路径根本不做计算往返，邀请永远得不到回应（solver.py:387、:650；没找到禁止 SB 用 `bindings` 的检查）；
  - 计算往返的运算符：登记稿写的是 + − × ÷，compute.py 用的是 ASCII 的 + - * / 和 **；
  - 计算稿给 OQ 跑题单元按 96 格估价（C 组每题按 2 次算），代码里 C 组每题只跑 1 次，共 72 格（48 个 S 格 + 24 个 C 格，与登记稿 §5.1 的“跑 1 次”一致），上限有富余。
- **考官一侧**：
  - 进化很薄：没有上一轮策略，检测器库是空的，留出的一半只有 15/12 题，退役规则也没实现；
  - 一条无效请求会作废整个策略，而 SB 上的 `parameter_choice` 永远无效；
  - 研究存储按链存而不是按单元存，`Researcher.record` 从没被调用；
  - 预测效度没接线；重做时会重建 G_acc，但不核对内容。
- **判分**：频段和捷径用 `final.token`，自测和验收用 `judge.v2.token`。两者在 SB 上相同，在 OQ 上可能不同。
- **操作流程**：
  - A5-1 的降档不进清单；
  - `recover` 不检查 attempt 是否真的暂停过；
  - 不给 `--s0-pins` 时 `make-manifest` 会报裸 KeyError（冒烟手册过时的问题已在 14:42 解决）；
  - 重做之后的 `cost_projection` 没测过。
- **其他**：A10-3 未解决，T_F 的长度带只限上限；LiveMath 答案字母的均衡规则只在题数为 5、10、12、13 或 ≥15 时能过（影响正式链，不影响试点）。

### 12.6 已知风险
- **很可能什么都收不下**：即使真实效果有 +5 个百分点，默认试点什么也收不下的概率也约 0.63；30 道题时检验的实际误判率约 12.3%；最小可检出效果是 10–12 个百分点。
- **链 G 的成本核对**（第 18 行）：风险低，但不是零；一旦越界，加上限也解不开。
- **测试读取**：
  - 第 9 行修好之前，同意书晚到会留下最多 10 个暂停的读取 attempt（同意书已于 15:01 写好，默认试点里不会发生）；
  - 重新启动会再套一次 1.3 倍读取闸门；
  - Q3 只有 ALF，检出力约 0.37。
- **OQ 第 2 步的 S_dup**：如果开了 S_dup，会多约 1% 的“未决”概率。
- **两条链同题**：G、D 两条链只是复现，不能当两份独立证据。

代码入口：step.py:UNITS、chain.py:run_manifest、scripts/run_execskill.py（命令总表）、docs/handoff/execskill-build-20261021/pilot-runbook.md §0（阻塞表）

### 12.7 严谨性与局限：最后的测试读取还算不算"留出"

负责人 10/22 15:0x 问："如果我签署了这份同意书，那么最终的评测还是 hold-out 的嘛，我们的实验还符合科研的严谨性质吗"。
这一节把回答和出处写下来，供论文的"局限"部分直接引用。

**一句话**：签同意书不破坏留出。对路线 B 这个方法而言，最后的测试读取是真正的留出评测；需要如实披露的是项目层面的一条：
同一套测试集在协同进化第 1 版时打开过一次分数。

#### 12.7.1 "留出"指什么，同意书为什么不破坏它

"留出"（hold-out）= 测试题在最终评测之前不参与任何决定（学什么、收不收、下一步怎么设计）。读测试集同意书（`shared/consent.json`，
键集合见 §8）只是允许"每条链最后读一次"的钥匙。真正破坏留出的是下面四种做法；登记稿与代码对每一种都有防护：

| 破坏留出的做法 | 本实验的防护 | 出处 |
|---|---|---|
| 提前读 | 学习侧的角色（工程师、考官、查证员）、检测器、出题程序、验收都拿不到测试访问权；只有评测单元在有效同意书下能开测试集；没有同意书，读取单元不开、整条链等待（14:10 附录第 9 行，正在实现；实现前是每个读取单元各自拒绝并暂停）。 | 登记稿 §3.5、§8.1；`evaluation.consent`；`chain.run` |
| 读完回头改再读 | 读之前最终包 F 已封存（内容哈希）；每条链只读一次（负责人决定 #12）；读完不再改 F。 | 登记稿 §8.1；`chain.evaluate` |
| 看分数决定下一步 | 分数先封存：负责人按学习侧报告决定继续/停止 → 正式链增补登记写好并封存（决定 #32）→ 才解封。下一阶段的设计因此不受本次测试分数影响。 | 登记稿 §8.1、§9.4；pilot-runbook §7.3–7.4 |
| 测试题文字混进训练材料 | S0 的两项排除（负责人 10/22 09:18 签的排除同意书）把新训练供给里与测试题重复的题剔掉，只记计数与哈希；读取开始时做测试指纹（只留长度与 sha256 前缀），解封前扫描整个运行目录，命中即暂停（只有负责人能按记录哈希放行）。 | `exclusion.py`；`evaluation.make_read_canaries`、`root_scan`；14:1x 附录 PR-C31-3 |

此外，读哪些组（F、C、P_F、T_F、孪生格）、按什么顺序报告都事先登记（§8.2），不能事后挑组、挑 bench；各组在同一批测试题上同时段交错运行，
组间对比是配对的。

#### 12.7.2 必须如实披露的局限

1. **同一套测试集以前看过分数（项目层面的再使用）。** 路线 B 的五个测试集（SearchQA 400、OfficeQA 172、LiveMath 125、SpreadsheetBench 279、
   ALFWorld 134 道；`protocol.TEST_READ_CELLS`，经冻结的 `coevo5.data.test_panel`）就是协同进化第 1 版、第 3 版用过的那一套。第 1 版四条
   GLM-5.3 链每一步都在这五个测试集上评测，分数 10/19 10:52 经负责人同意打开（[结果账本](../results-and-lessons.md) 10/19 10:52 条；
   [项目状态](../project-status.md) 10/19 条）；第 3 版也做了测试评测，分数一直封存（账本 10/20 条）。第 2 版、第 3 版和路线 B 都是在看过
   第 1 版结果之后设计的。所以：路线 B 从未在测试题上调参或挑选，它的测试读数是留出的；但在整个项目层面，这套题不是"第一次被看"。
   偏差风险小（只打开过一次、路线 B 不是按测试分数选出来的、结果无论好坏按登记报告），但必须写明。
2. **预训练污染。** SpreadsheetBench、OfficeQA、SearchQA 是公开数据，做题模型可能见过；影响绝对分数，组间对比（同一模型）受影响较小。
3. **两条链不是两份独立证据。** 链 G、链 D 做的是同一批题（登记稿 §0 (c)、§11）。
4. **题量决定的把握。** 测试集每个 bench 只能认出约 10 分以上的差别；"相似 bench 也涨"多半只能描述（登记稿 §0 第 4 条、§6.6）。
5. **试点读一次、正式链以后再读同一套题。** 第二次读仍然有效的前提是：正式链的方案在试点分数解封之前封存（决定 #32），因而不可能按试点
   分数调整。这一前提要写进报告。
6. **验收结果只是选择证据。** 验收用的训练题在 SpreadsheetBench、OfficeQA 上以前被别的方法反复用过（登记稿 §3.1：两种口径都是 0 道没用过），
   所以"收下"只说明"在没用过的训练题上胜过父版本"，不是泛化证据（登记稿 §0 第 3 条，负责人决定 #31）。
7. **决定检验在偏斜零假设下会多收。** 单侧 5% 的 t 检验在"均值为零但分布偏斜"时实测误收约 12%–16%（|A\*| = 30），150 题时约 6%–8%；
   整条链 5–9 个决定、至少误收一次约 0.23–0.37（登记稿 §6.4，附录 A 的 T9）。

#### 12.7.3 如果要做到"留出性无可挑剔"（负责人 10/22 15:1x 已决定不做："只要能做到hold-out评测就可以了"）

加一份从未打开过的确认集，只在最后用一次，并在试点分数解封前登记：

- **SearchQA**：10/12 封存的新题块 C、D 共 2,000 道，从未打开；作评测目标最小可测约 1.5–1.9 分
  （[方向建议](direction-recommendation-20261021.md) S21、S61）。只跑最终包 F 与只有任务卡 C 两组，每条链约 0.7–1.8 千万做题 token
  （估计：§9.1 SearchQA 锚点 1,535–3,400 token/格，带过程的组 ×1.25–1.6；账本口径另乘 S-E6 实测比例）。
- **ALFWorld、LiveMath**：可能有未用部分（例如更新的 LiveMath 发布），需另行核实。
- **SpreadsheetBench、OfficeQA**：基本没有余量。

不加确认集时，按现有登记执行，上面的局限照实写入报告。

## 13 术语表
| 代号 | 白话意思 | 详见（不带 § 的数字是第 1 部分的小节） |
|---|---|---|
| 过程（procedure） | 包里的一条小 Python 程序（≤6,000 字节），由工程师写，只能实现几个钩子 | 3.1、§6 |
| 钩子（hook） | 壳在固定时机调用的 6 个函数名之一，名单封闭 | 3.2、§6 |
| `applies` | 判断过程管不管这道题的钩子；它为真，过程才算在这道题上“生效” | §6、§7.2 |
| 包（package） | ≤24 条过程加一个顺序，就是被学习的“技能” | 3.3 |
| 壳（shell） | 固定不学的外壳代码：路由、调用钩子、拼请求、调用做题模型 | 3.4 |
| 隔离箱（sandbox） | 断网、只读、无权限的 Docker 容器，过程只在里面运行 | 3.8 |
| 便条（note） | 过程通过钩子写给做题模型的文字，放在固定字段里 | 3.5、§6 |
| 任务卡（card） | 每个题库一段冻结的说明文字，永不学习 | 3.9 |
| 做题模型（solver） | 真正答题的模型：链 G 用 glm-5.3，链 D 用 deepseek-v4.1-flash-1017 | 2.3 |
| 工程师 / 考官 / 查证员 / 描述员 / 泄漏裁判 | 方法角色，都是 GLM-5.3：改包 / 诊断和出题 / 查证资料 / 把过程改写成文字说明 / 判一次疑似泄漏 | 2.4、§6、§8 |
| 登记员 | 登记规则、做裁定的一方；“登记员代码”指固定不学的检查代码 | §6 |
| 登记稿 / 裁定 / 计算稿 | 三份出处：事先登记的方案、登记员的决定记录、零调用算术 | 读前说明 |
| 第 n 行 | 裁定 14:10 补充（也是试点运行手册阻塞表）里的第 n 行，例如第 18 行是链 G 成本核对 | §9、§12 |
| 工单号 | 构建工单编号，例如 PR-C61-2（SB 生成工作簿）、PR-C12-1（SB 捷径探针）、PR-C31-3（金丝雀与放行）、PR-F2-1（15 分钟序列）、C7e-1/C7e-2（G_acc 作用域、终局轮）、A10-3（无说明过程的文字孪生） | §12.4 |
| 链 G / 链 D | 两条并行流水线，只有做题模型不同，题目相同，所以是复现 | 2.3 |
| SB / OQ / LM / SQ / ALF | SpreadsheetBench 表格题、OfficeQA 报表问答、LiveMath 数学选择题、SearchQA 检索问答、ALFWorld 文字家务 | 2.5 |
| 跑题段（run slice） | 每步开头用父包做的一批训练题，产生失败记录，也是供体来源 | 2.6、5.1 |
| 验收段（acceptance slice） | 每步结尾判候选包用的一批新题，只用一次 | 2.6、§7 |
| 格（cell） | 一道题 × 一个组 × 第几次运行 = 一次作答及其记录 | 3.10 |
| 组（arm） | 同一批题用不同的包去做，每种包是一个组 | §7.3 |
| S | 父包：这一步开始时的当前包，第 1 步为空 | §6 |
| S' | 候选包：S 加上本步存活的改动 | §6 |
| F | 冻结后的最终包，也是测试读取的主组 | §8 |
| C | 只有任务卡、没有任何过程的空包组 | §7.3 |
| S_dup | S 的一份完全相同的拷贝，用来检验同一个包两次跑分是否一致（J6） | §7.3 |
| P_y | 配对安慰剂：改动过的过程只输出配对供体的内容，长度对齐（J2） | §7.2 |
| P_i | 无关文字安慰剂，只描述 | §7.2 |
| P_F / T_F | 测试时的配对安慰剂 / 文字孪生（把过程换成冻结的文字说明） | §8.3 |
| X / P（冒烟） | 冒烟 S2 里的夹具包组 / 安慰剂组 | §10 |
| 供体（donor） | 给 P_y 提供便条内容的旧题，取自父包在跑题段上的轨迹 | §7.2 |
| 孪生格（twin） | `withhold:<p>` 拿掉过程 p、`restore:<p>` 放回 p 再做一遍，用来算单个过程的作用 | §7.2 |
| tau | 由孪生格算出的单个过程的贡献，只描述 | §7.2、§8.3 |
| A / A\* | A = 验收段全部题；A\* = 其中被改动的过程碰到的题，只有 A\* 被真正发出 | §7.2 |
| G_self / G_acc | 考官生成题的两半素材：G_self 给自测，G_acc 在验收时只做描述 | 5.3、§6.3、§7.6 |
| 四道关 | 考官生成题的准入检查：真值、难度频段、捷径、标签 | 5.3 |
| C1–C9 | 工程师改动的固定检查（实际按 10 步顺序执行） | §6.2 |
| 重放测试 | 工程师附带的小测试：在真实轨迹上检查过程的行为 | §6.2 |
| claims_fix / nonvacuity | 重放测试里“声称修好了失败”的标记 / 拿掉过程或变异后测试必须不再成立 | §6.2 |
| engineer-2 / selftest-2 | 自测第一次被拦后，第二轮工程师和自测 | §6.3 |
| J1–J7 | 验收的七条判定规则 | §7.4 |
| L 侧 / H 侧 | 计分时 unknown 算错（S'、孪生格）/ 算对（对照组），故意对 S' 不利 | §7.4 |
| pass / fail / unknown / unknown_fault | 判分结果：通过 / 失败 / 不知道 / 由故障造成的不知道 | §7.4 |
| judge v2 / final | 两种判分读法：v2 用于自测和验收，final 用于频段和捷径 | §12.5 |
| accept / reject / undetermined | 收下 / 否决 / 未决（仪器有问题，本批作废并暂停） | §7.4 |
| not_run_small_astar | A\* 不到 30 道，不跑也不消耗 | §7.2 |
| 终局轮 | 在最后一个格之后才暂停的验收轮，不能重做 | §7.5 |
| P1–P7 | 七类不稳定情况（登记稿 §4.4）：P4（隔离箱不可用）让单元暂停；P6（推理档不一致）先自动重发，只有输出超过 B 时才让账本熔断；其余只记录 | §9.3 |
| M / B | 请求里允许的最大输出 / 账本按多大预留 | §6.5、§9.2 |
| 分支 E / N | S1 决定的链 D 的 B 的取法 | §10 |
| R | 计算上限时多加的一笔预留 | §9.2 |
| 锚点（低 / 高） | 登记的每格成本估计，用来定上限 | §9.2 |
| 账本（ledger） | 每条链一本的 token 账，先预留、后结算 | §9 |
| 作用域（scope） | 账本里的子账户，各有上限，一次调用同时记进好几个 | §9 |
| 熔断（halt） | 回执报告的用量超出预留假设（或账本写入失败）后，整本账停下，要主人执行 `resume-ledger`；预算不够只是暂停，不是熔断 | §9.2 |
| 单元（unit） | 一个小步的工作目录：加锁、按 attempt 执行、结论只写一次 | §6 |
| attempt | 单元的第 N 次执行 `attempt-N`，最多重做 2 次 | §7.5、§9.4 |
| `recovery.json` | 主人对一个暂停 attempt 的决定，只能由 `recover` 照原话写 | §9.4 |
| 消耗账 | 每道训练题被哪条链、为什么用掉的登记簿，只增不改 | 4.12 |
| 成本核对（cap_check） | 链 G 第一个跑题单元后的零调用核对，每格超过 6,409.5 就暂停 | §9.5 |
| above_high | 每格成本超过 1.25 × 高锚点的标记 | §10 |
| 金丝雀（canary） | 从测试题里取出的特征片段，用来查测试题是否混进了别处 | §8.3 |
| 根目录扫描 / 放行 | 解封前扫描整个运行根找金丝雀 / 主人放行已知命中 | §8.3 |
| 解封与标签 | 打开测试分数；标签有 confirmatory、repeated_test_development 等 | §8.3 |
| q1_home / q2_similar / q3_noninferiority | 读数三问：学过的 bench、相似 bench、不相似 bench 是否不变差 | §8.3 |
| 挑选证据 / 泛化证据 | 验收裁决（selection）/ 测试读取（generalization） | §8.1 |
| S0 / S1 / S2 / S3 / S-E6 | 冒烟的五个阶段 | §10 |
| S-N1 / S4 | 被主人裁掉的两个冒烟阶段（噪声锚点、恢复演练） | §10 |
| 夹具（fixture） | 手工准备的工程测试题和包，不是真题 | §10 |
| 清单（manifest） | 钉死代码、模型设置、题池和上限的总清单，每个单元开始前都会重新校验 | §11.2 |
| 钉住文件（pins） | 生成清单用的输入：从冒烟结果和准备阶段收集的固定值 | §10.3、§11.2 |
| 回执（receipt） | 每次模型调用返回的用量凭证，账本按它结算 | §9.2、§10.2 |
| 供给池（supply） | 还没被用掉、可以再切给后面步骤的题 | §8.2 |
| 预测效度 | 生成题上的涨跌能否预测真题上的涨跌；需要 ≥8 轮，试点里无法评估 | §7.6 |
| 主代理 | 按运行手册操作、向主人报告的主会话；只在主人决定后执行恢复等操作 | §11 |
| `$SRC` / `$PRE` / `$SMOKE` / `$PILOT` / `$PM` / `$OPS` | 运行手册里的目录变量：代码快照 / 准备阶段产物 / 冒烟运行根（`$PRE/smoke`）/ 试点运行根 / 试点清单文件 / 操作员文件（钉住文件、启动脚本、日志、读数，永不放进 `$PILOT`）（pilot-runbook.md 第 86–97 行） | §11.2；第 1 部分的根目录表 |
| 构建代理与进度编号 | 正在写代码的代理和它们的笔记编号，例如 P2C（phase-2c 构建者）、I1（集成者，分 2a/2b 阶段）、P2-A1/P2-A2/P2-A3、OPS1 | §12 |

代码入口：protocol.py（全部常量和代号的定义处）

## 附录 文件与记录索引
| 路径模式 | 内容 | 谁写 | 谁读 |
|---|---|---|---|
| `<run root>/<c>/chain.json`、`.runner.lock` | 链的身份和顺序；运行锁 | `chain.run` | 操作员、`monitor` |
| `<c>/s<k>-<bench>/slices.json` | 本步跑题段和验收段的切分 | step | 各单元 |
| `<c>/s<k>-<bench>/<unit>/attempt-N/{started.json, status.json, diagnostics.log}` | 一次执行的开始、暂停原因、traceback | 单元框架 | 操作员、`recover`、主人 |
| `…/attempt-N/recovery.json` | 主人的决定 | `recover`（照主人原话） | 下一次 `run` |
| `…/attempt-N/{cells/, trajectories/, enable_log.jsonl, artifacts/, host_only/}` | 格、轨迹、生效记录、产物 | 单元 | 下游单元、`decide`、读数 |
| `<c>/s<k>-<bench>/<unit>/unit.json` | 单元结论（只写一次） | 单元框架 | 后续单元、step |
| `diagnose/attempt-N/candidates.json`、`generate/attempt-N/research-split.json` | 检测器候选；G_self/G_acc 素材对半分 | diagnose、generate | 考官、自测、验收 |
| `accept/sealed.json`、`accept/attempt-N/decision/decision.json` | 验收封存；裁决记录 | `acceptance.prepare`、`decide` | 每个验收 attempt、结算、主人 |
| `freeze/unit.json`、`<c>/s<k>-<bench>/step.json` | 冻结结论和文字说明；本步记录 | `_freeze`、step | 下一步、测试读取（T_F） |
| `<c>/packages/<sha>.json`、`<c>/procedures/<sha>.json` | 包和过程（按内容哈希命名） | 工程师、冻结 | 所有组 |
| `<run root>/G/cap-check-G.json`（加上限后的再核对为 `cap-check-G-<n>.json`） | 链 G 成本核对 | `chain.cap_check` | 操作员、读取闸门（`chain.latest_cap_check` 取编号最大的一份） |
| `<c>/test-read.json`、`<c>/test/<bench>/`、`<c>/read-waiting.json` | 读取结论；读取单元；等待同意书 | `chain.evaluate`、`read_consent` | 操作员、主人 |
| `<c>/root-scan/attempt-N/{scan.json, status.json}`、`<c>/unsealed.json` | 根目录扫描；解封标签 | `evaluation.unseal` | 主人、读数 |
| `<c>/chain-complete.json`、`chain-terminated.json` | 链结束 / 终止 | `chain.run`、终止命令 | 操作员 |
| `<run root>/shared/ledger-<c>/{events.jsonl, state.json}` | 账本 | `Budget` | `monitor`、主人的决定 |
| `shared/consent.json`、`owner-continuation.json`、`formal-addendum.{md, json}` | 测试读取同意、继续或停止、正式补充 | 同意书由主人亲手写（已于 15:01 写好）；按运行手册 §7.3，继续/停止由主代理照主人原话写一次；正式补充由主代理起草、主人批准内容后写成 `.md`，再用 `seal-addendum` 封成 `.json`（如果登记员认为继续/停止必须由主人亲手写，它就成为第二件亲手做的事） | `read_consent`、`unseal` |
| `shared/test-canaries.json`、`shared/test-read-canaries.json` | 金丝雀（只有长度和哈希前缀） | `make-manifest`、读取开始时 | 扫描 |
| `shared/research/<c>/sources/<sha>.json` | 研究存储：搜索结果和网页，只写一次 | `Sources.keep` | 考官出题、复核 |
| `shared/host_only/diagnostics/child-*.log` | 子进程日志 | `chain._child` | 操作员 |
| `/data/execskill-history/consumption/<ns>/<bench>.jsonl`、`supply/…` | 消耗账和供给池 | registry | 切题、主人 |
| `/data/execskill-slots/*.lock`、`memory-heavy.lock` | 机器级并发槽和内存锁 | slots（内存锁由 `chain.py` 管） | 所有单元 |
| `$OPS/{test-read-estimate.json, pilot-pins.json, pilot-provenance.json, pilot-run.sh, pilot-<c>-run-<n>.log, pilot-readout/readout-<c>.json}` | 操作员文件 | 主代理（读取估算由 `test-read-estimate` 写） | 主代理、主人 |
| `$SMOKE/{smoke.json, stages/, smoke-result.json, manifest.json, s0/, units/S2/, units/S3/, shared/exclusion/}` | 冒烟的规格、阶段记录、结论、清单 | 冒烟命令 | 出发检查、`make-manifest` |
| `$PRE/{s0-pins.json, pools/, fixtures/, texts/texts.json, sheet-runtime.json}` | 准备阶段产物（这里只列路径，不展开题目内容） | 准备阶段的命令（`s0-collect`、`export-pools`、`make-fixtures`、`import-texts`、`sheet-runtime`） | 钉住文件生成器、`make-manifest` |

代码入口：units.py（单元目录与 attempt）、chain.py:run / evaluate、budgets.py:ledger_root、evaluation.py:unseal、scripts/run_execskill.py:monitor


## 附录 B 核对记录（两个核对代理逐条对照代码的修改记录）

### B.1 第 0–5 节的核对记录

**核对了什么。** 第 0 节到 5.3 节里的具体说法约 400 条：路径和路径模式、函数名和文件:行号、记录字段名、常数/上限/条数/种子/阈值、步骤顺序、哪一臂或哪条标准真正做决定（哪些只是描述）、现状、只能主人做的步骤。逐条对照了 dl 构建树里的代码（`skillopt/execskill/*.py`、`skillopt/coevo5/protocol.py`、`skillopt/continual_eval/backends`、`scripts/run_execskill.py`）、登记稿、登记员裁定（到 15:1x）、计算输出 T4/T9、构建员笔记（C7b1、C7c、I1、OPS1、P2-A1、P2-A2、P2C）和冒烟/试点手册；四个格式句的 sha256 前缀重算过，都对得上。全文没有密钥、凭据内容或题池内容；设计和计划没有写成实验结果。

**改了什么（约 50 处，按类）。**
1. 现状过时：测试读取同意书 15:01 已写好（原写「主人还没写」）；第 7、8、9、17 行已由 P2C 建好并有测试，全套测试 1,183 项通过（原写「正在建」「结果未核实」）；PR-C61-2、PR-C12-1、I1-2 的完成时间；14:4x 杀掉 29 个 D3/D14 遗留进程；S3 跑题单元是 20 道 SQ 格 + 1 个确认格（14:4x 裁定取代 14:3x 的「约 60 格」）；2.8 时间表补了 14:4x、15:01 两行，「12:2x 容器检查（快照未核实）」改为 11:2x–11:41 C7b1 在构建树上的零调用实测。
2. 记录格式：做题格记录、壳记录（`route`、`calls`、`procedure_events`、`notes`、`compute`、`sandbox`）、回放测试格式、检测器验证字段、出题关卡和出题器记录、`step.json`、消耗账（`attempt` 是整数，时间带 `+00:00`）都按代码重写了骨架；`describer` 缺省是 `{}` 不是 null；ALF 动作归一化按 `canonical.py` 重写；SB 上裁判 v2 就是 `final`（SB 没有 JSON 补救通道）。
3. 数字和出处：B = 2 × M（M 是单次回答上限，不是「百万」）；线程数 16/6 出自 `units.py`；计算上限 4,096 是二进制位数；0.63 的前提是两步都真有 +5 分；J1 在配对安慰剂明显有害时改用 0.025；ALF 冒烟 12 局 = S2 的 6 局 + 原给 S-N1 的 6 局；补了首次调用上限 1.1M 的来历。
4. 顺序：链 G 的成本核对在它第一个跑题单元之后（不是 SB 一步之后）；起跑先做首次调用确认（错开启动只留作后备）；开读前先查读取同意书、再查预算，链 G 的估计乘以成本核对系数（小于 1 按 1 算）。
5. 命令和路径：`unset OPENAI_API_KEY OPENAI_BASE_URL`；S0 行文件是 `$SMOKE/s0/s0-<行>.json`；磁盘表补了 `confirm.json`、`confirm-failed-<n>.json`、`cap-check-G-<n>.json`、`read-waiting.json`；4.13 和 5.1 补了 `test-read-estimate`、`estimate_test_read`、`first_call`、`read_consent`、`read_budget` 的入口。
6. 术语表补了 F、构建员代号（C7b1、I1、OPS1、P2-A1、P2-A2、P2C）、工单、D2/D3/D14。

**仍未核实。**
1. v3 运行清单里重算的 `timeout_seconds` 实际值（规则不许读 `/data/coevo5-*`；代码默认 120）。
2. ALF 任务类型：空跑数出 6 种，登记稿写 7 种前缀，差在哪里没查清。
3. 1.2M 上限下「约 4 个同时在途请求」只是估算。
4. SB 的 bindings 邀请：`solver.py:_solve_sheet` 调用 `_Shell.before` 后把名字丢掉，代码已确认，等登记员裁定（不是已修好的事）。
5. 清单 `caps` 的具体键和 `pins` 各块的内部结构没有逐项核对。
6. I1 收尾部分（笔记里等 P2C 完成后才做的 (c) 部分）的内容。
7. 时间：各构建员笔记的自标时间有偏差（P2C 自标 16:4x，文件实际写于 15:44），文中时间以裁定和文件修改时间为准；12:50 的导出数字来自演练，正式运行必须复现。

### B.2 第 6–13 节和附录的核对记录
- **核对了什么**：§6–§13 和附录里约 350 条具体说法，包括路径、函数名、文件行号、记录字段、常量和上限、数量、种子、阈值、步骤顺序、哪个组或条件做裁决、哪个只描述、现状，以及只有主人能做的事。每条都对照了代码（`skillopt/execskill`、冻结的 `skillopt/coevo5`、`scripts/run_execskill.py`）、登记稿、登记员裁定（到 15:1x 补充）、计算稿、运行手册 15:28 版、冒烟手册 14:42 版和各构建笔记（P2C、I1、P2-A1/A2/A3 等）。核对时只读代码和文档，没有跑测试，也没有调用模型。
- **改了约 100 处**（都在原处替换），主要有：
  - **数字**：冒烟里不发出的 SQ 题 200 → 240；S3 跑题单元“约 60 格” → 20 格加 1 个确认格；验收测试 25 → 27 条。
  - **结论和方法**：0.63 只在真实效果为 +5 时成立；检出力只算 J1 和 J2；t 检验的均值、方差和自由度；30 道门槛的数字来自精确枚举，不是模拟；孪生格的挑选、P_y 的长度、删掉的过程放回。
  - **账本**：放不下时先排队、后拒绝；一次调用最多试 4 次，生成前被拒的 4xx 记 0；只有回执越界或账本被隔离才熔断；重做和角色记在哪些作用域；`<c>:confirm`；链 G 成本核对不投影 GLM 作用域和确认作用域，再核对写成 `cap-check-G-<n>.json`。
  - **检查**：C4 静态禁词查哪些地方；泄漏查重查哪些对象；SB 和 ALF 只查 8 词片段；自测怎样算 unknown。
  - **冻结和读取**：F 的哈希什么时候变；否决和没跑时消耗多少题；q2 和 q3 怎么读；OQ 的两块测试题连着发；同意书要求 `sheet_test_qualification` 为 true，主人已于 15:01 写好；继续/停止和正式补充由谁写；`report` 也会返回退出码 5。
  - **现状**：第 7、8、9、17 行，以及 PR-C61-2、PR-C12-1、C7e-1、PR-F2-1、PR-C31-3 和 I1 2a/2b (a)，都改成“开发树已做完，全套测试 1,183 条已过，待 Codex 审查和最终快照”；I1 2b (c)、P2C-1、P2C-2 仍未关。
  - **补充**：新增 §9.6（账本的输入/输出表和现状）；术语表补了 P1–P7、熔断、构建代号和目录变量。
- **还没核实或仍有疑问**：
  1. 登记稿写工程师“每步 ≤6 次调用”，代码却按单元计数（engineer-2 另有 6 次，泄漏裁判每个单元最多 6 次）；S-E6 只按每步 6/6/3 外推。没有找到对这一点的裁定。
  2. `protocol.py` 给 SB 定了 G_acc 题数 60，但 v1 在 SB 上不生成 G_acc（step 返回 None）。acceptance.py 模块说明写 G_acc“在 A\* 公开题面上生成”，和代码实际用研究的那一半素材不一致。
  3. 登记员会不会要求主人亲手写 `owner-continuation.json`。
  4. LiveMath 选项平衡和 ALF 的 6 种任务类型只来自读者笔记。按规定不能打开数据，所以没有用数据复核。
  5. 10/22 12:2x 的容器检查早于最终快照；守卫余量 6.8 倍来自开发树上的 S0 自测。
  6. 测试条数是用 grep 数 `def test_` 得到的，没有跑 pytest；“1,183 条通过”取自 P2C 进度记录。
  7. 构建树还在改：Codex 审查、最终快照、I1 2b (c)、运行手册第 140 行出发检查的改动都还没做。这些落地后，相关现状要再更新一次。
