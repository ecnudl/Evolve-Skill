# 五 bench 协同进化第 1 版：五个测试集上的逐步分数

> Evolve-Skill · 五 bench 协同进化 · 协议 `fivebench-coevolution-v1` · 做题模型 GLM-5.3 · 运行 2026-10-18 12:38 至 10-19 07:16 ·
> 测试分数 10-19 10:52 经负责人同意打开 · 本页整理于 10-19 11:15。同样内容的网页（本地文件）：[coevo5-v1-results-20261019.html](coevo5-v1-results-20261019.html)。

## 结论

- 学完五个 bench 后，五个测试集的平均分：**指令（I-glm）66.7**，SkillOpt-glm 66.0，E-glm 63.7，GEPA-glm 63.5；不用 Skill（空白）是 58.6。
- **平均分最高的是没有学进任何东西的指令。** I-glm 五步一条规则都没收下，它的分数就是起点指令的分数。它和 SkillOpt-glm 只差 0.6 点（指令减 SkillOpt 的 95% 区间 [−2.3, +3.4]），分不出高低。
- 真正在“进化”中提高最多的是基线 SkillOpt-glm：比空白高 7.4 点（[+4.5, +10.3]）。
- 我们的方法 E-glm 比空白高 4.9 点（[+2.0, +7.8]），但比指令低 2.8 点（[−5.5, −0.1]），比 SkillOpt-glm 低 2.4 点（[−5.4, +0.5]）；后一项按事先登记的“不差于”检验算“不确定”。
- 提高几乎都在 SearchQA 和 OfficeQA：每一份 Skill（包括指令）都让这两个 bench 提高 13–21 点。E-glm 只学了两条“答案写短”的 SearchQA 规则，OfficeQA 也提高了约 20 点，和其他 Skill 差不多，说明这部分提高主要来自作答写法，而不是针对 OfficeQA 学到的东西。LiveMath、ALFWorld 看不出变化。学来的 Skill 让 SpreadsheetBench 下降 2–8 点（只有 GEPA-glm 的区间整个在 0 以下），指令则提高约 9 点。

## 1 实验设置

目标：让做题模型的 Skill 从做题经验里自己长出来。Skill 是放进做题模型系统提示里的一段文字说明书。理想的样子是：学完一个数据集，相似的数据集也变好，不相似的不变差。

**五个数据集（按学习顺序，一个叫一个 bench）**

| 步 | bench | 内容 | 测试题数（分母） |
|---|---|---|---:|
| 1 | SearchQA | 带检索结果的知识问答（类似《危险边缘》节目的线索题） | 400 |
| 2 | OfficeQA | 读美国财政部公报里的表格回答问题 | 172 |
| 3 | LiveMath | 数学选择题 | 125 |
| 4 | SpreadsheetBench | 按要求修改 Excel 表格。登记 279 道，其中 75 道的参考答案无法在判分引擎里核实，开跑前按规则排除 | 204 |
| 5 | ALFWorld | 文字版家务游戏，要一步步操作完成任务 | 134 |

**参加比较的五份 Skill**

| 名称 | 是什么 | 起点 |
|---|---|---|
| 空白 Skill | 参照，等于不用 Skill | — |
| E-glm | 我们的方法（主结果） | 空白 Skill |
| I-glm | 我们的方法 | 五份任务说明指令：只看任务说明写出的做题要求，约 12 KB |
| SkillOpt-glm | 基线：别人的方法，代码冻结不改 | 空白 Skill |
| GEPA-glm | 基线：别人的方法，代码冻结不改 | 空白 Skill |

名字后面的“-glm”表示做题模型是 GLM-5.3（智谱）。原计划再用 deepseek-v4-flash 做一遍（E-ds、I-ds），因为账号额度用完没有开。

## 2 方法：每一步怎么学、怎么评

1. 用当前 Skill 把这个 bench 的训练题做一遍。
2. 看做错的题，提出 5 条候选规则（叫“提案”）。
3. 每条规则要过一道“门”才收下：
   - **进门**：规则针对的那类错题（叫“触发题”）至少要有 4 道，还要过泄漏检查（规则里不能写进具体答案）。
   - **初筛**：在触发题上要比原 Skill 做对得多，也要比“随便加一段无关文字”好；同时在以前学过的 bench 上各抽 60 道“回归题”，不能变差太多。
   - **复核**：再做一遍，确认不是运气。
4. 收下的规则加进 Skill。

两条基线按它们自己的规则学：每一步由它们自己的挑选决定改不改 Skill。

**评测**：每一步学完，用当前 Skill 把五个测试集全部做一遍，每道题做 1 次。如果这一步 Skill 没变，就直接沿用上一步的分数、不重测。

## 3 结果：五个测试集上的分数

### 3.1 平均分随步数的变化

平均分是五个测试集各自正确率的简单平均（%），每个测试集权重相同。“（沿用）”表示这一步 Skill 没变、沿用上一步的分数。

| 步 | E-glm | I-glm（指令） | SkillOpt-glm | GEPA-glm |
|---|---:|---:|---:|---:|
| 0 起点 | 58.6 | 66.7 | 58.6 | 58.6 |
| 1 SearchQA | 63.7 | 66.7（沿用） | 64.3 | 63.5 |
| 2 OfficeQA | 63.7（沿用） | 66.7（沿用） | 64.3（沿用） | 63.5（沿用） |
| 3 LiveMath | 63.7（沿用） | 66.7（沿用） | 66.0 | 63.5（沿用） |
| 4 SpreadsheetBench | 63.7（沿用） | 66.7（沿用） | 66.0（沿用） | 63.5（沿用） |
| 5 ALFWorld | 63.7（沿用） | 66.7（沿用） | 66.0（沿用） | 63.5（沿用） |

### 3.2 学完五步后，各测试集的分数

每格是正确率（%）和“对的题数/可判题数”；加粗是这一列最高的。

| Skill | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | 平均 [95% 区间] |
|---|---:|---:|---:|---:|---:|---:|
| 空白 Skill（参照） | 72.5（290/400） | 29.1（50/172） | 40.0（50/125） | 62.8（125/199） | 88.8（119/134） | 58.6 [55.6, 61.6] |
| 指令（I-glm）（我们的方法，没收下规则） | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | **72.1（142/197）** | 88.8（119/134） | **66.7 [63.8, 69.7]** |
| SkillOpt-glm（基线） | 86.8（347/400） | **50.0（86/172）** | **42.4（53/125）** | 60.5（121/200） | **90.3（121/134）** | 66.0 [63.1, 68.9] |
| E-glm（我们的方法） | 85.3（341/400） | 49.4（85/172） | 40.8（51/125） | 56.6（112/198） | 86.6（116/134） | 63.7 [60.7, 66.8] |
| GEPA-glm（基线） | **89.0（356/400）** | 48.3（83/172） | 38.4（48/125） | 55.4（108/195） | 86.6（116/134） | 63.5 [60.5, 66.5] |

### 3.3 和空白 Skill 比，每个测试集变了多少

单位是百分点，方括号里是 95% 区间。↑ 表示区间整个在 0 以上，↓ 表示整个在 0 以下，没有箭头表示分不出。

| 相对空白 Skill | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | 平均 |
|---|---:|---:|---:|---:|---:|---:|
| 指令（I-glm） | +14.8 [+11.0, +18.5] ↑ | +20.4 [+12.1, +29.2] ↑ | −4.0 [−11.2, +3.2] | +9.2 [+2.6, +16.0] ↑ | 0.0 [−4.5, +4.5] | +8.1 [+5.2, +11.0] ↑ |
| SkillOpt-glm | +14.3 [+10.3, +18.3] ↑ | +20.9 [+14.1, +27.7] ↑ | +2.4 [−6.4, +11.2] | −2.0 [−9.6, +5.5] | +1.5 [−3.0, +6.0] | +7.4 [+4.5, +10.3] ↑ |
| E-glm | +12.8 [+8.8, +17.0] ↑ | +20.4 [+12.2, +28.5] ↑ | +0.8 [−7.2, +8.8] | −7.2 [−14.7, 0.0] | −2.2 [−6.0, +0.8] | +4.9 [+2.0, +7.8] ↑ |
| GEPA-glm | +16.5 [+12.8, +20.5] ↑ | +19.2 [+11.5, +27.3] ↑ | −1.6 [−9.6, +5.6] | −7.8 [−15.3, −0.5] ↓ | −2.2 [−7.5, +2.2] | +4.8 [+1.9, +7.7] ↑ |

### 3.4 我们的方法：逐步数据

**E-glm（从空白 Skill 出发）**

| 步 | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | 平均 [95% 区间] | 这一步的 Skill |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 起点 | 72.5（290/400） | 29.1（50/172） | 40.0（50/125） | 62.8（125/199） | 88.8（119/134） | 58.6 [55.6, 61.6] | 起点：空白 Skill（三条链共用） |
| 1 SearchQA | 85.3（341/400） | 49.4（85/172） | 40.8（51/125） | 56.6（112/198） | 86.6（116/134） | 63.7 [60.7, 66.8] | 收下 2 条规则 |
| 2 OfficeQA | 85.3（341/400） | 49.4（85/172） | 40.8（51/125） | 56.6（112/198） | 86.6（116/134） | 63.7 [60.7, 66.8] | 没有收下规则，沿用 |
| 3 LiveMath | 85.3（341/400） | 49.4（85/172） | 40.8（51/125） | 56.6（112/198） | 86.6（116/134） | 63.7 [60.7, 66.8] | 没有收下规则，沿用 |
| 4 SpreadsheetBench | 85.3（341/400） | 49.4（85/172） | 40.8（51/125） | 56.6（112/198） | 86.6（116/134） | 63.7 [60.7, 66.8] | 没有收下规则，沿用 |
| 5 ALFWorld | 85.3（341/400） | 49.4（85/172） | 40.8（51/125） | 56.6（112/198） | 86.6（116/134） | 63.7 [60.7, 66.8] | 没有收下规则，沿用 |

**I-glm（从指令出发）**

| 步 | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | 平均 [95% 区间] | 这一步的 Skill |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 起点 | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | 72.1（142/197） | 88.8（119/134） | 66.7 [63.8, 69.7] | 起点：五份指令 |
| 1 SearchQA | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | 72.1（142/197） | 88.8（119/134） | 66.7 [63.8, 69.7] | 没有收下规则，沿用 |
| 2 OfficeQA | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | 72.1（142/197） | 88.8（119/134） | 66.7 [63.8, 69.7] | 没有收下规则，沿用 |
| 3 LiveMath | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | 72.1（142/197） | 88.8（119/134） | 66.7 [63.8, 69.7] | 没有收下规则，沿用 |
| 4 SpreadsheetBench | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | 72.1（142/197） | 88.8（119/134） | 66.7 [63.8, 69.7] | 没有收下规则，沿用 |
| 5 ALFWorld | 87.3（349/400） | 49.4（85/172） | 36.0（45/125） | 72.1（142/197） | 88.8（119/134） | 66.7 [63.8, 69.7] | 没有收下规则，沿用 |

### 3.5 基线：逐步数据

空白 Skill 的分数就是下面两张表的第 0 步，和 E-glm 共用同一次评测。

**SkillOpt-glm**

| 步 | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | 平均 [95% 区间] | 这一步的 Skill |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 起点 | 72.5（290/400） | 29.1（50/172） | 40.0（50/125） | 62.8（125/199） | 88.8（119/134） | 58.6 [55.6, 61.6] | 起点：空白 Skill（三条链共用） |
| 1 SearchQA | 88.0（352/400） | 47.7（82/172） | 35.2（44/125） | 58.8（114/194） | 91.8（123/134） | 64.3 [61.4, 67.2] | 更新了 Skill |
| 2 OfficeQA | 88.0（352/400） | 47.7（82/172） | 35.2（44/125） | 58.8（114/194） | 91.8（123/134） | 64.3 [61.4, 67.2] | 输入超长停下，沿用上一步 |
| 3 LiveMath | 86.8（347/400） | 50.0（86/172） | 42.4（53/125） | 60.5（121/200） | 90.3（121/134） | 66.0 [63.1, 68.9] | 更新了 Skill |
| 4 SpreadsheetBench | 86.8（347/400） | 50.0（86/172） | 42.4（53/125） | 60.5（121/200） | 90.3（121/134） | 66.0 [63.1, 68.9] | 学完，没改，沿用 |
| 5 ALFWorld | 86.8（347/400） | 50.0（86/172） | 42.4（53/125） | 60.5（121/200） | 90.3（121/134） | 66.0 [63.1, 68.9] | 学完，没改，沿用 |

**GEPA-glm**

| 步 | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld | 平均 [95% 区间] | 这一步的 Skill |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 起点 | 72.5（290/400） | 29.1（50/172） | 40.0（50/125） | 62.8（125/199） | 88.8（119/134） | 58.6 [55.6, 61.6] | 起点：空白 Skill（三条链共用） |
| 1 SearchQA | 89.0（356/400） | 48.3（83/172） | 38.4（48/125） | 55.4（108/195） | 86.6（116/134） | 63.5 [60.5, 66.5] | 更新了 Skill |
| 2 OfficeQA | 89.0（356/400） | 48.3（83/172） | 38.4（48/125） | 55.4（108/195） | 86.6（116/134） | 63.5 [60.5, 66.5] | 学完，没改，沿用 |
| 3 LiveMath | 89.0（356/400） | 48.3（83/172） | 38.4（48/125） | 55.4（108/195） | 86.6（116/134） | 63.5 [60.5, 66.5] | 学完，没改，沿用 |
| 4 SpreadsheetBench | 89.0（356/400） | 48.3（83/172） | 38.4（48/125） | 55.4（108/195） | 86.6（116/134） | 63.5 [60.5, 66.5] | 学完，没改，沿用 |
| 5 ALFWorld | 89.0（356/400） | 48.3（83/172） | 38.4（48/125） | 55.4（108/195） | 86.6（116/134） | 63.5 [60.5, 66.5] | 学完，没改，沿用 |

### 3.6 两两比较

**事先登记的读数**

| 比较（五个测试集平均分之差） | 差（点） | 95% 区间 | 结论 |
|---|---:|---:|---|
| E-glm 学完 − 空白（我们的方法的学习增益） | +4.9 | [+2.0, +7.8] | 成立 |
| SkillOpt-glm 学完 − 空白 | +7.4 | [+4.5, +10.3] | 成立 |
| GEPA-glm 学完 − 空白 | +4.8 | [+1.9, +7.7] | 成立 |
| I-glm 学完 − 指令（超过指令了吗） | 0.0 | [0.0, 0.0] | 未建立（一条规则都没收下） |
| E-glm − SkillOpt-glm（第 5 步；P1，“不差于”要求区间下端高于 −3） | −2.4 | [−5.4, +0.5] | 不确定 |
| E-glm − GEPA-glm（第 5 步；P2） | +0.3 | [−2.7, +3.1] | 按登记顺序未检验（P1 没成立） |
| E-glm − 指令（从空白学到指令的水平） | −2.8 | [−5.5, −0.1] | 不确定 |

**事后补算，只描述（不是登记的检验）**

| 比较 | 差（点） | 95% 区间 | 结论 |
|---|---:|---:|---|
| 指令 − SkillOpt-glm（第 5 步） | +0.6 | [−2.3, +3.4] | 区间含 0，分不出 |
| 指令 − GEPA-glm（第 5 步） | +3.2 | [+0.3, +6.0] | 前者高 |
| SkillOpt-glm − GEPA-glm（第 5 步） | +2.4 | [−0.4, +5.2] | 区间含 0，分不出 |
| 指令 − 空白 Skill | +8.1 | [+5.2, +11.0] | 前者高 |

区间按测试题重抽 10,000 次算出（OfficeQA 按出处文件成组重抽），只反映“换一批测试题”带来的不确定。每条链只跑了一次，没有反映重跑一次的随机变化。

### 3.7 迁移读数

事先登记的合并迁移判据（E-glm）：自身 Q1 +2.6 [+1.8, +3.4]；相似 Q2 +4.1 [+2.4, +5.7]；其余 Q3 −0.6 [−1.3, +0.2]，按数字算“成立”。但这几乎全部来自第 1 步那两条“答案写短”的 SearchQA 规则把 OfficeQA 从 29.1% 提到 49.4%；同样幅度的提高在指令和两条基线上都有（见 3.3），所以这是作答写法的作用，不能当作学到的迁移能力。E-glm 第 2–5 步没有收下规则，这几步的变化都是 0；“相似位置”一次也没用上。

## 4 训练过程（我们的方法）

“训练题做对”是这一步开始时，原 Skill 在这个 bench 训练题上做对的次数。

| 链·步 | 训练题做对 | 提案 | 进门 | 过初筛 | 过复核 | 收下 | 泄漏拦下 / 触发题不够 |
|---|---:|---:|---:|---:|---:|---:|---:|
| E 1 SearchQA | 259/393（66%） | 5 | 2 | 2 | 2 | **2** | 2 / 1 |
| E 2 OfficeQA | 83/148（56%） | 5 | 4 | 0 | – | 0 | 0 / 1 |
| E 3 LiveMath | 77/200（38%） | 5 | 4 | 2 | 0 | 0 | 1 / 0 |
| E 4 SpreadsheetBench | 45/90（50%） | 5 | 4 | 0 | – | 0 | 0 / 1 |
| E 5 ALFWorld | 102/114（89%） | 5 | 0 | – | – | 0 | 0 / 5 |
| I 1 SearchQA | 311/392（79%） | 5 | 4 | 0 | – | 0 | 1 / 0 |
| I 2 OfficeQA | 89/148（60%） | 5 | 3 | 0 | – | 0 | 0 / 2 |
| I 3 LiveMath | 83/200（42%） | 5 | 4 | 2 | 0 | 0 | 1 / 0 |
| I 4 SpreadsheetBench | 65/91（71%） | 5 | 2 | 0 | – | 0 | 0 / 3 |
| I 5 ALFWorld | 101/114（89%） | 5 | 0 | – | – | 0 | 0 / 5 |
| **合计** |  | 50 | 27 | 6 | 2 | **2** | 5 / 18 |

没进门的 23 条里，5 条被泄漏检查拦下，18 条凑不够 4 道触发题。

**学不动的主要原因（训练侧证据）**

- **学到的就是指令里写着的**：E-glm 第 1 步收下的两条规则，在同一批训练题上让 E 做对 319/392 次，I-glm 的起点指令也是 319/392。
- **门太“吵”**：同一个原 Skill 把同一批题做两次就能差 2–3.5 题，比“至少多对 1 题”的要求还大。LiveMath 上过了初筛的 4 条规则，复核时全部没过。
- **错题少，诊断分不清类型**：ALFWorld 成功率 89%，10 条提案都凑不够触发题；LiveMath 的 35 道错题全被归成“其他”。
- **空白起点吃亏**：某个 bench 的分区里只要有任何文字（哪怕无关），成绩就会变好；E 在没收下规则的 bench 上一直缺这段“架子”。
- **有几个环节没起作用**：考官修改评分细则 8 次，6 次因字段超长被整份作废；上网查证 8 次全无结论。

**基线每一步改没改 Skill**

| 链 | 1 SearchQA | 2 OfficeQA | 3 LiveMath | 4 SpreadsheetBench | 5 ALFWorld |
|---|---|---|---|---|---|
| SkillOpt-glm | 改了 | 没改（输入超长停下，沿用上一步） | 改了 | 没改 | 没改 |
| GEPA-glm | 改了 | 没改 | 没改 | 没改 | 没改 |

## 5 时间线与花费

| 时间 | 事件 |
|---|---|
| 10/17 23:43 | 第一次冒烟（小规模试跑），用 deepseek 做题 |
| 10/17 23:55 | deepseek 免费通道回“额度用完”，冒烟停下，没有花 GLM 的钱 |
| 10/18 11:49 | 按负责人的选择改用 GLM-5.3 冒烟 |
| 10/18 12:16 | 冒烟查出一个问题：考官修改评分细则的合格回复被误判作废；已修好 |
| 10/18 约 12:30 | 冒烟通过，花约 196 万 tokens。2 道 SearchQA 训练题 GLM 每次都拒答，记为“未知”，不算答错 |
| 10/18 12:38–12:58 | 四条链陆续开跑，确认第一批真实回答正常 |
| 10/19 01:01 | GEPA-glm 跑完 |
| 10/19 03:30 | SkillOpt-glm 跑完 |
| 10/19 05:00 | I-glm 跑完 |
| 10/19 07:16 | E-glm 跑完，四条链全部完成，全程没有暂停 |
| 10/19 09:11–10:20 | 第 2 版的设计与代码：Codex 设计审查、代码审查各一轮，意见全部改完 |
| 10/19 10:33 | 第 2 版开跑前准备开始，代码快照记下全部文件哈希 |
| 10/19 10:52 | 经负责人同意，生成并打开第 1 版的测试分数报告 |

**花费**（GLM-5.3 tokens，token 是模型读写文字的计量单位）：四条链共 172,244,798，其中 E-glm 36,125,058，I-glm 60,339,685，SkillOpt-glm 59,596,851，GEPA-glm 16,183,204。加上开跑前的文字和冒烟 1,972,795，一共 174,217,593，占 14.4 亿总上限的 12%。全程没有暂停，没有提高上限。

基线学习时按设计占住 10 个并发里的 8 个，约 10 小时里其他链只能用 2 个，所以前半程很慢；两条基线跑完后明显加快。

## 6 第 2 版与现在的情况

第 2 版（协议 `fivebench-coevolution-v2`）在打开上面这些测试分数之前就已定稿：代码快照 10:33 上传开发机并记下全部文件哈希，测试分数 10:52 才打开。第 2 版不会因为这些分数再改。

**第 2 版改了什么**

- **链**：E-glm 改从固定的“空架子”出发（五个分区标题，没有规则）；I-glm 仍从指令出发；新加 NoSkill-glm（真正空白，只测第 0 步当参照）。两条基线不重跑，所以第 2 版不和基线比较。
- **找该学的**：错题按一张固定的错误类型表分类；提案必须引用具体错题，并给“相似 bench”留名额。
- **判断学到了没有**：门在触发题上多做几遍（问答类 4 遍，表格和 ALFWorld 2 遍）；回归题上原 Skill 做 2 遍。
- **其他**：考官字段长度上限放宽、逐条检查，不再因为一处问题整份作废；泄漏检查遇到“某个单词碰巧和答案一样”时看证据再判；查证资料加入 50 页 LibreOffice 函数说明。
- **预算**：总上限 12 亿 tokens（14.4 亿减去第 1 版已花的，再给第 1 版的 deepseek 复现留 0.58 亿）。

**现在（10/19 11:00 前后）**

- 10:33 开跑前准备开始：开发机上离线测试 669 项通过；新的查证资料库 71 份；SpreadsheetBench 判分引擎认证通过，训练侧资格检查 120 道里 91 道合格（和第 1 版一样）。
- 10:35 GLM-5.3 冒烟开始（只用训练数据）：SearchQA 一步的训练和准备已完成，正在初筛；到 10:57 共花约 96 万 tokens。
- 冒烟通过后：生成启动清单 → 零调用检查 → 写同意记录 → 开 NoSkill-glm、E-glm、I-glm，并确认第一批真实回答。
- deepseek 免费通道 10:56 仍回“额度用完”，第 1 版的 E-ds、I-ds 还没开。两个 key 属于同一个账号，需要充值或换一个账号的 key。

## 附录

### 附录 A 最终 Skill 文本

**E-glm 学到的全部内容（第 1 步收下的 2 条 SearchQA 规则）**

1. `s1-r1` Put ONLY the short answer inside <answer>...</answer> — just the single word, name, number, or phrase the question asks for (typically 1–3 words). Never include explanations, definitions, background, dates, parentheticals, or restatements of the question inside the tag.
2. `s1-r2` Answer with the minimal identifying form: a surname alone when the reference likely uses only a surname (e.g. a person commonly known by one name), the shortest common name of a place or thing, and no middle names, initials, honorifics, or appositive expansions unless they are essential to identify the entity.

<details>
<summary>SkillOpt-glm 最终 Skill（第 1、3 步更新）（15,174 字节）</summary>

```text
## Answer formatting for exact-match / Jeopardy-style short-answer tasks

These tasks (search QA, trivia/clue-style questions) are graded by exact string match against a short canonical answer. Failures here almost never come from wrong knowledge — they come from returning the right entity in the wrong form. After identifying the answer entity, apply this procedure:

### Identify what is actually being asked
1. Parse the clue as a statement with a missing answer slot; determine which noun phrase fills it. If the clue says "this French thief, novelist & playwright", the expected answer is the surname alone. If it says "these mountains", answer with the range's common short name. If the clue is built around a quoted title, the answer is often the missing word of the quote or the work's source/inspiration — not a summary of the topic. If the question is just two names with no question word, it asks for the single shared attribute connecting them; answer with that attribute alone.
2. **Match the question's granularity exactly.** If the clue describes a category ("this organization", "this dessert", "one of these", "this site"), answer with the common name of the category/generic term or the specific entity the slot demands — not a brand, subtype, building, or broader installation unless the clue demands it. If the clue lists several items, determine the single shared entity they point to and answer with that one entity.
3. If the context includes a Jeopardy-archive-style snippet showing "Clue | Answer", the answer is the short term after the divider.

### Choose the canonical form
- **Prefer the shortest commonly used name form**, and prefer the exact surface form used in the provided context or by the majority of sources.
  - People: surname or the most commonly used form (e.g., "Fragonard", not "Jean-Honoré Fragonard"); include a title/regnal name only if customary or the source consistently uses it. Do not expand with middle names, suffixes ("Jr."), honorifics, or descriptors ("President", "of France") unless the source form includes them.
  - Titles/organizations: prefer the widely used short form (the part before a subtitle, the brand without corporate suffixes like "Inc."). If the question already quotes a partial phrase, the expected answer is often the quoted-adjacent core term, not the full official title.
- **Match number and surface form to the clue and source:** check singular vs plural against the supporting passage's usage; mirror the source's dominant form (capitalization, generic roles like "the editor", honorifics like Sir/Dr./Saint) rather than substituting your own variant.

### Format the answer
- **Output ONLY the bare entity** — one name or short noun phrase. Do NOT add: parentheticals or aliases ("X (also called Y)"), alternate spellings, chemical formulas, acronym expansions, subtitles, dates, trailing category words ("Party", "Mountains", "Company") unless part of the standard short name, or any explanatory sentence or justification. Write `X`, not `X (Y)` or `X — the Y of Z`. Any reasoning belongs outside the answer, never inside it.
- **No game-show phrasing.** Never wrap answers in "What is ...?" or "Who is ...?" — output the content only.
- **Articles:** drop leading "A"/"An" for proper nouns and category terms; keep "the" only when the expected answer is a fixed expression or common-noun role that idiomatically requires it.
- Do not restate or explain the clue; the answer fills the gap, it doesn't describe the topic. For blank-fill clues (e.g., "___ & Wagnalls"), fill only the blank with the smallest complete unit.
- **Disambiguation priority:** the expected answer is the entity satisfying ALL of the clue's stated constraints (especially quoted/emphasized descriptors) and is usually the more famous/common name — not a secondary candidate that merely appears in supporting documents.

### Self-check before finalizing
Try deleting each word from your draft answer; if a shorter string still fully and unambiguously answers the question, use it. If your draft contains parentheses, a comma-qualifier, a relative clause, or more than ~5 words, trim it to the core noun phrase. Then verify the final string (or its singular/plural variant) appears in the supporting passage, and mentally substitute it back into the clue's gap.

## Retrieval procedure for SearchQA-style tasks (retrieved documents + clue-style question)

These tasks provide a bundle of retrieved documents (`[DOC] [TLE] ... [PAR] ...`) plus a short, often Jeopardy-style clue (e.g., "this author", "this neighborhood", "it's the cry of..."). The answer is a single short entity; apply the formatting rules above, and use this procedure to find it:

1. **Determine the answer type and all constraints first.** Use the clue's determiner or phrasing to identify the slot ("this playwright" → a person's name; "this city" → a place; "the number of..." → a bare numeral; translation clues "means X in English" → the translated term). Extract every distinguishing constraint (dates, nationality, role, relationships, quantities, quoted nicknames, superlatives like "first"). The entity named in the clue is usually the *input*; the answer is the other side of the relationship. If the clue asks for one part of a name, give exactly that part.
2. **Scan for the clue text itself first.** The clue is often paraphrased or restated near-verbatim in one passage; the missing piece of that sentence is the answer. Quiz/flashcard/trivia-archive sources frequently pair the clue text directly with its answer (e.g., `category | clue | answer` with the answer after a pipe) — treat that pairing as strong evidence, but sanity-check it fits the clue. Otherwise, match the clue's distinctive anchors (proper names, dates, numbers, quoted phrases) and find the entity co-occurring with them; use doc titles as a fast filter, since many retrieved docs are irrelevant noise.
3. **Match ALL constraints, not just one keyword.** The correct passage co-occurs with multiple clue terms; distractor documents share surface keywords but satisfy only a subset of constraints (unrelated word senses, coincidental years, wrong entity of the right category). Discard any candidate that fails an explicit constraint.
4. **Prefer corroboration and authoritative sources.** Candidates supported by multiple independent documents are strong confirmation. Encyclopedic/factual passages outrank forum replies, game-show recaps, or contestant guesses (which are often wrong answers deliberately included as distractors). If candidates conflict, pick the one satisfying every attribute with more/stronger supporting passages.
5. **Self-verify before finalizing.** Substitute the candidate back into the clue and confirm every constraint holds according to the supporting passage(s). Confirm the answer is the described entity itself, not a related one mentioned alongside it (e.g., if the clue asks for the parent, don't answer the child). If any constraint fails, search the docs again; only fall back on general knowledge if no snippet states the answer.

### Output format
- Respond with ONLY the concise entity wrapped in `<answer>...</answer>` tags — no preamble or explanation. Preserve capitalization/hyphenation and articles only when part of the standard name (e.g., "Winnie-the-Pooh", "The Outsiders"); common nouns are lowercase. Answers are typically 1–3 words; give a fuller phrase only when the clue explicitly asks for one (e.g., a quoted "3-word phrase").

## Procedure for research-level multiple-choice math tasks ("strongest provable / equivalent statement" questions)

These tasks present a specialized mathematical setup (definitions, hypotheses) quoted from a research-level area, plus 4–5 lettered options (A–E) that share a common core and differ in fine details; the question asks which is the *strongest statement that holds or can be proved*, which statement is *equivalent* to a given theorem, or what is *exactly characterized*. One option is often a **meta-option**: "One of the remaining options is correct, but a stronger result can be proven." Do not answer from plausibility or first impressions — apply this procedure:

### Reason before choosing
1. **Write out a derivation in your reasoning text before naming a letter.** Restate the question's demand in one line (strongest provable? exact equivalence? a specific constant/regularity?), then check every option against it. A bare letter with no derivation is a guess; the correct option is usually a subtle variant of a distractor.

### Parse and diff the options
2. **Diff near-identical options token by token.** Options in this family are near-copies differing in one detail: numerical constants, exponents (1/n vs 1, $k^{-\alpha}$ vs constant), strict vs non-strict inequality (including `lim` vs `limsup`/`liminf`), endpoint inclusivity of parameter ranges (q < c vs q ≤ c), index shifts (n vs n+1), quantifier order ("there exist signs such that for every n" vs "for every n there exist signs"), an added converse clause or structural conclusion (uniqueness, periodicity), regularity indices, uniformity of constants in parameters vs dependence on them, smooth/linear vs arbitrary coefficients, whole domain vs bounded subinterval, sup-norm vs L¹ convergence, presence/absence of a `+ε` term, or presence/absence of an extra hypothesis. The answer is determined solely by these differences — not by which option reads most impressively, is longest, or comes first; do not anchor on option A. Eliminate any variant containing a sub-clause you cannot independently justify.

### Recognize standard distractor transformations
3. Treat these as the likelier wrong choices:
   - **Overstated:** adds an unjustified specific — a claimed mechanism ("obtained from a conjugacy"), sharper regularity, a strengthened quantifier ("every such...", "only finitely many"), or a clause not implied by the hypotheses.
   - **Understated:** weakens the true conclusion (subsequential instead of full convergence, non-sharp bound when a sharp constant is known) — correct but non-strongest, so loses when "strongest" is requested.
   - **Near-miss:** changes one quantifier, modulus, exponent, or arithmetic condition (divisor of m vs of 2m, n ≥ 10 vs n ≥ 9).
   - **Hypothesis tampering:** silently adds extra assumptions not given, or drops a needed one.

### Rank options by logical strength
4. **Build an explicit partial order among the concrete options.** Option X is stronger than Y iff X implies Y but not conversely: an extra conclusion, a sharper constant or exponent, a two-sided (matching lower+upper) bound vs an upper bound only, a wider or closed parameter range, an iff characterization vs a one-way existence statement, equality of structures vs a coarser invariant (group isomorphism vs equality of invariants), exact value vs inequality, uniform-in-time vs single-time. Discard options strictly weaker than another surviving option. The correct answer is the maximal element among options that are actually TRUE — a stronger false option and a weaker true option are the two standard traps.

### Audit each strengthening clause for provability
5. **Reconstruct the theorem, then test the marginal claim of each option on its own merits.** Re-derive the critical quantity from the problem's own definitions (check scaling/homogeneity, limiting/special cases like n=1, n=2, smallest prime, and boundary inclusions) rather than pattern-matching to a familiar theorem. Common over-reach traps: upgrading an upper bound to a two-sided bound when only a weaker lower bound is proven, upgrading numerical equality of invariants to an isomorphism, claiming constants uniform in a parameter when they depend on it, strengthening o(·) to an exact constant, closing an interval endpoint, or reversing a quantifier. If any single added clause is false or unproven, reject the whole option even if its core is correct. Options making *incomparable* claims must each be checked independently. Use every stated hypothesis as a signal: an unused hypothesis suggests a strengthening is available.

### Treat the meta-option seriously
6. **The meta-option is a first-class candidate, not a throwaway.** It asserts (a) some concrete option is correct as far as it goes, AND (b) the true theorem proves strictly more. After identifying the strongest provable concrete option, explicitly ask whether the actual result from the literature is strictly stronger on any dimension — sharper constants or exponents, an exact closed-form where options give only bounds, uniqueness or an added structural/classification conclusion, weaker hypotheses, or broader scope. If any concrete option still understates the known result, the meta-option is correct; in these tasks it is very frequently the intended key, and option sets are often built from a real theorem plus deliberately slightly-weakened concrete variants. Conversely, if the strongest concrete option exactly reproduces the source theorem (matching constants, exponents, quantifier pattern, and exceptional cases), the meta-option is a trap. Do not reflexively pick a concrete option because it looks detailed, and do not pick the meta-option reflexively either.

### Equivalence / "exactly characterized" questions
7. **Check both directions.** For "which statement is equivalent to P", verify P ⇒ option AND option ⇒ P. Reject options that are merely necessary consequences of P, sufficient-but-stronger conditions not implied by P, or that change the quantifier structure. The correct option is often the weakest/softest statement that is still bidirectionally equivalent (e.g., a plain inequality with an unrestricted positive constant rather than a contraction constant < 1). When the question asks what is *exactly characterized*, the answer is the option stating a full biconditional — not a one-way implication, not an averaged/Hamming-style surrogate, and not a coarser equivalence (equality up to permutation is strictly weaker than exact tuple equality when exact equality is characterizable).

### Self-check
8. Before finalizing, restate the chosen option's claim in your own words and confirm every quantifier and constant against the recalled theorem. For each rejected option, name the single feature that makes it fail (too weak — misses a provable strengthening — or false at the specific delta you identified); try a counterexample against the chosen option. Check you have not confused "strongest provable statement" with "most detailed-sounding option". If you chose a concrete option over a present meta-option, articulate exactly why no stronger statement holds (e.g., the option already matches the known-sharp constant or full biconditional); if you cannot, prefer the meta-option. If you cannot confirm a specific exponent, constant, or endpoint, prefer the weaker option.

**Output format for these tasks:** respond with ONLY the single option letter wrapped in `<answer>...</answer>` tags (e.g., `<answer>B</answer>`), no preamble, derivation, or explanation inside the tags, unless the task explicitly requests the full statement.
```

</details>

<details>
<summary>GEPA-glm 最终 Skill（只在第 1 步更新）（4,325 字节）</summary>

```text
You are answering Jeopardy!-style trivia questions. Each input gives a clue (the "question") and a set of retrieved context documents. Your job is to produce the correct Jeopardy "answer" (the response the contestant would give).

Input format:
- question: the Jeopardy clue, sometimes with a parenthetical letter count like "(4)" indicating the number of letters in the expected answer.
- context: a list of [DOC]/[TLE]/[PAR] blocks (title and paragraph text from web pages). Relevant facts are usually buried in one or two of these; many blocks are irrelevant noise.

Procedure:
1. Read the clue carefully and determine exactly what entity is being asked for. Jeopardy clues are precise: identify the specific noun (a person, place, thing, or term) the clue points to.
2. Scan the context for sentences that directly confirm the answer. Prefer authoritative sources (Wikipedia, Britannica, encyclopedia entries) over crossword-clue aggregators or fan pages, but note that crossword/flashcard aggregator pages (StudyStack, Fikkle Fame, jService) sometimes contain the literal expected answer string — if you find the exact clue text in such a block, the answer usually follows it verbatim.
3. Match the specificity of the expected answer to the clue:
   - If the clue asks "this city", answer with the city name only (e.g., "Richmond", not "Richmond, Virginia").
   - If the clue asks for a river, answer with the river's common name (e.g., "the Amazon", not "the Amazon River").
   - If a clue asks "these animals" and multiple are listed but one is the primary/most commonly cited answer, give the single most prominent one.
   - If a clue asks "this structure", give the generic structure name, not an elaborated description with extra details like ship names.
   - If the clue gives two names of the same category (e.g., two kings), the answer is often the shared category/country.
4. CRITICAL — match the determiner used in the clue to the article in your answer:
   - When a clue says "...one of these", the expected answer typically starts with the indefinite article: e.g., a clue about a chair back shaped like "one of these" expects "a balloon", not "hot air balloon". Strip modifiers and give the bare category noun with "a"/"an".
   - When a clue says "this [category noun]" and the category noun itself is a compound whose head word is what's really being asked for (e.g., "this market that features a lengthy period of price drops"), the expected answer is often the head noun alone with the definite article ("the bear"), not the full compound ("bear market").
   - Conversely, when the clue names a specific entity ("this city", "this state", "he's the woodcarver who..."), give the proper name with no article (e.g., "Buffalo", "Pennsylvania", "Geppetto").
   - When in doubt between a longer descriptive phrase and a short generic noun, prefer the shorter generic noun that still uniquely fits the clue.
5. If the clue contains a parenthetical letter count like "(4)", count the letters of your candidate answer (ignoring spaces/punctuation) and verify it matches exactly. Use wordplay (rhymes, alliteration, overlapping words in the clue) if applicable.
6. Self-verify: re-read the clue and check that your answer directly substitutes into it. Check every stated constraint (dates, distances, events, letter counts). Then check your answer's article and length against rule 4 one final time.

Output format — CRITICAL:
- Respond with ONLY the answer inside <answer></answer> tags.
- The answer must be SHORT: typically one to three words. Give exactly the entity the clue asks for, with no additional explanations, descriptions, context sentences, or qualifiers that were not requested.
- Do NOT list multiple alternatives or hedge. Pick the single best answer.
- Do NOT add state/country qualifiers to city names, vessel names to generic structures, or comparisons when the clue expects one category word.
- Include an article ("a balloon", "the bear") only when the clue's phrasing ("one of these", "this [compound noun]") calls for it, per rule 4.

Examples of correct answer style (format only):
- City clue → <answer>Edmonton</answer>
- Person clue → <answer>Geppetto</answer>
- "One of these" clue → <answer>a balloon</answer>
- "This market" head-noun clue → <answer>the bear</answer>
```

</details>

<details>
<summary>I-glm 的起点指令（也是它的最终 Skill）（12,154 字节）</summary>

````text
## SearchQA
- Read the question first and note its type (person, place, date, number, title, etc.) so you know what form the answer should take.
- Scan all snippets, not just the first: the answer may appear only in a later snippet, and early snippets are often irrelevant.
- Snippets are noisy: ignore SEO text, navigation fragments, and off-topic content. Use only what directly answers the question.
- Prefer an answer that appears verbatim in the snippets over one you synthesize; the metric is exact match, so the exact surface form from the context is safest.
- If snippets disagree, favor the most authoritative, specific, or repeated source; consider whether the question's phrasing (e.g., "Jeopardy!"-style clue) implies a well-known fact.
- Answer with the minimal entity or value requested, not a full sentence: e.g., a name, a date, a title, a number.
- Match the question's expected unit and granularity: if asked "how many", give just the number (unless the source shows a unit is part of the canonical answer).
- If the question asks for one of several (e.g., "which city"), return only that item, not a list, unless the question explicitly asks for multiple.
- Watch for near-miss distractors in the snippets (similar names, different dates, related works); verify the snippet actually matches all constraints in the question.
- Handle titles and proper nouns carefully: include articles that are part of a title (e.g., "the great gatsby" keeps "great gatsby"), since normalization only strips articles ambiguously — keeping the source's wording avoids risk.
- If no snippet contains the answer, still give your best short guess from the context or general knowledge; an empty answer scores zero.
- Output the final answer inside `<answer>...</answer>`, ensuring that the last such tag in your reply contains exactly the concise answer text.

## OfficeQA
### Guidance for U.S. Treasury Bulletin Questions (OfficeQA, one-call)

- Read the **question first** to identify the exact quantity sought (a date, a single value, a percentage change, a sum/ratio across line items, etc.) — this determines what to hunt for in the context and whether a calculation is needed.
- Search the supplied **context** for the relevant table or passage. Treasury Bulletin pages mix running text with tables rendered as text; match on row/column labels, table titles, footnote markers, and period labels (e.g., fiscal-year vs. calendar-year, month, quarter) before trusting any number.
- **Use only the supplied context.** Do not fill gaps from memory of Treasury data, and do not "correct" numbers that look odd — the reference answer is derived from these pages.
- Watch for **units and scaling**: tables may state "millions of dollars", "percent", or "billions" in headers or notes. If the answer must be in a specific unit, convert carefully; the normalization removes the words million/billion/dollars/nominal, so the *digits* you emit must already reflect the intended magnitude.
- Pay close attention to **row and column alignment** in flattened tables: parsed text can misalign headers, so verify a candidate value by checking neighboring values that you can cross-check against totals or subtotals in the same table.
- If a computation is required (difference, sum, growth rate, share of total), show the work in your reasoning, then perform it **exactly** with the figures as printed — round only if the question or table conventions clearly imply it (e.g., "percent change to one decimal").
- Be careful with **signs and negatives**: values in parentheses typically mean negative; the normalization keeps '-', so include it when the answer is negative.
- Distinguish similar series that commonly appear together (e.g., fiscal year-to-date vs. monthly, assets vs. liabilities, holdings vs. transactions, different maturities or instrument types) — a one-word mismatch in the label usually means the wrong figure.
- If the context is cut off or the needed figure is genuinely absent, pick the best-supported answer from what is present rather than guessing wildly; prefer a value from the same table over one inferred from text.
- Format the final answer to survive normalization: **emit the bare number (or short string) inside `<answer>...</answer>`**, without commas, currency symbols, or units if the reference is a pure number; keep '%' only if the answer is a percentage. Avoid thousand separators, since commas are stripped anyway but any extra words will break exact match.
- If multiple `<answer>` tags appear, only the **last** one is scored — so place exactly one final tag at the end with your definitive answer.
- Keep the answer **concise**: a number, a short label, or a date in the form most likely used by the reference (e.g., "12345.6" rather than "12,345.6 million dollars").

## LiveMath
- The question is built from a theorem in a recent arXiv paper, so expect precise, technical mathematical content; read the statement carefully for quantifiers, hypotheses, and exact constants.
- Do not assume the theorem is one you know from classical literature; it may be a recent refinement, so verify each option against the statement rather than against memory of older results.
- Parse the "question" field completely before looking at the choices: identify what is being asked (a value, an inclusion, a yes/no decision, a completion of a sentence).
- Examine all five options; distractors are typically near-misses such as swapped quantifiers, weakened/strengthened hypotheses, wrong constants or dimensions, or plausible but false generalizations.
- Check edge cases and boundary conditions: strict vs. non-strict inequalities, open vs. closed sets, equality vs. containment, "for all" vs. "there exists".
- Beware of options that are true statements in general but do not answer the specific question, or that hold only under additional assumptions not present in the question.
- Use only the supplied public information; do not rely on external knowledge of the specific paper, but standard mathematical reasoning and background are fine.
- If two options look close, translate both into precise mathematical language and test them against simple examples or limiting cases consistent with the hypotheses.
- Eliminate clearly wrong options first; among the remainder, prefer the option that matches the theorem's exact formulation rather than a paraphrase that changes meaning.
- When the question asks to "complete" a statement, ensure grammatical and logical continuity with the stem; a choice may be correct only when read in the full sentence.
- Decide on exactly one letter; if uncertain, choose the most defensible option after elimination rather than leaving the answer ambiguous.
- Return only a single letter (A–E) inside `<answer>...</answer>`, with nothing else in the tag, as the final part of your reply; the last such tag is what gets scored.

## SpreadsheetBench
- Write a single, self-contained Python program in exactly one ```python code block; use openpyxl (the standard tool for this benchmark) and nothing requiring network access.
- The program must read `input.xlsx` (hardcode this path or read it from the supplied JSON's `input_path`) and save to `output.xlsx`; do not rename sheets or move data unless the instruction explicitly says so — only the cells named in `required_answer_position` are compared.
- Inspect the `workbook_preview` carefully: note sheet names (including exact spelling, spaces, and capitalization), dimensions, and the first rows/columns. Formulas appear as formulas in the preview, so the stored cell values may differ from what is shown; if the preview shows formulas, expect the real workbook to contain them and handle them via openpyxl's formula-preserving mode (`load_workbook(path, data_only=False)` is the default).
- Decide whether the answer position should contain literal values (computed in Python) or formulas. Safest: write literal values that equal the recalculated reference result, unless the instruction explicitly asks for formulas. If you do write formulas, they must recalculate to the correct values when the grader recalculates the workbook.
- When reading values, remember `data_only=True` returns cached results (None if the file was never recalculated by Excel) and `data_only=False` returns formula strings. Load twice (once each way) if you need both formulas and cached values.
- Match data types exactly where the comparison is value-based: numbers as numbers (not strings), dates as datetimes, and beware of text that looks like numbers. Preserve number formats only if the instruction concerns formatting; otherwise prefer writing plain values.
- Locate the target cells robustly: the answer may span a range (e.g. `Sheet1!B2:D5`) or multiple sheets. Ensure every cell in the range is written, including empty strings/None where the reference is empty, if that's plausible from the instruction.
- Handle merged cells, hidden sheets, and sheets beyond the 20-sheet preview limit — the actual workbook may be larger than the preview, so iterate dynamically rather than assuming preview bounds.
- Avoid operations that depend on Excel itself (no xlwings/win32com); openpyxl cannot evaluate formulas, so compute any derived results in Python rather than relying on cached formula values unless verified present.
- Keep runtime well under the 300-second limit: avoid O(n²) scans over huge ranges; operate only on the relevant sheets and columns.
- Wrap risky operations defensively: if a sheet or column mentioned in the instruction might not exist, check and fall back sensibly rather than raising. A raised error means zero credit.
- After writing the required cells, save the workbook with `wb.save("output.xlsx")` and ensure the program exits cleanly; verify the save path matches `required_output_path`.

## ALFWorld
- Always emit exactly one action per reply, wrapped in `<action>...</action>`; anything outside the tag is ignored, and a missing tag causes the whole reply to be executed, which almost always fails.
- The action must be one of the strings listed in `admissible_commands` — copy it character-for-character rather than paraphrasing, since the environment only accepts the listed commands.
- Before acting, re-read `initial_observation` to keep the goal in mind; it states both the task type (e.g., heat/cool/clean/examine an object, or place two objects somewhere) and the specific objects and receptacles involved.
- Parse the task into a concrete subgoal sequence, e.g., "find object → pick it up → find the required appliance (basin, fridge, microwave, etc.) → use it → move to the destination receptacle → put the object down".
- Use navigation commands (`go to X`) to explore locations named in the room description; `admissible_commands` reveals which receptacles and locations currently exist, so use it as a map of what is reachable.
- When you need an object's location, check the likely receptacles listed in the room description one at a time (e.g., `go to countertop 1`, `open drawer 1`, `examine X`) until you find it.
- Keep your physical state in mind: you can hold at most two objects (hands are used in commands like `take A from B`); note what you took from `recent_history` since it is not restated each turn.
- For cleaning tasks you need a sinkbasin; for heating a microwave; for cooling a fridge. Put the object in/on the appliance (e.g., `put A in/on sinkbasin 1`, `heat A with microwave 1`), then take it back out before delivering it to the final receptacle.
- Prefer efficient exploration: plan multi-step routes (e.g., go directly to a likely receptacle rather than re-visiting ones already seen as empty in `recent_history`).
- Watch `observation` after each action for success/failure feedback — "Nothing happens" or an error message usually means the action was inapplicable; adjust rather than repeating it.
- Do not emit empty actions or replies over 1000 characters; keep the action short and exact.
- Track progress against the 50-step limit: if a plan stalls, fall back to systematically exploring all receptacles named in the room description rather than wandering.
````

</details>

### 附录 B 数据来源与读法

- 运行 `7e91d88f…`：启动清单 `/data/coevo5-20261017-run-manifest.json`，运行目录 `/data/coevo5-20261017-run`，代码快照 `/data/coevo5-20261017-source-e`（开发机）。
- 报告 `/data/coevo5-20261019-v1-report/`（report.md sha256 `0103fb13…`，[原文副本](coevo5-v1-report-20261019.md)；report.json sha256 `a4a71bcd…`）：10:51–10:52 生成，零模型调用，代码与启动清单一致。3.3 和 3.6 里“事后补算”的差值用同一套代码与重抽设置另算（[脚本](coevo5_v1_compare_20261019.py)、[结果](coevo5-v1-compare-20261019.json)），不是登记的检验。
- 正确率口径：没做完算错；SpreadsheetBench 少数产物判不了的题（每格 4–10 道）不计入分母。把它们全算错或全算对，平均分最多变 0.6 点。
- 每条链只跑了一次；所有区间只反映测试题抽样。
