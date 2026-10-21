# 验证文本绑定研究：设计与读数规则（2026-10-15 04:30，写于任何结果之前）

## 1 为什么

rubric 形式研究的 OfficeQA 串联（6 块，台账 10/15 03:45 条）给出：形式（宿主执行 vs 模型判定）无差别；四种粒度没有
一种达到事先定的"支持"标准。零调用读封存的提案记录（同一条的追记）：八个臂的 analyst 每块都加几乎同一套章节
（多步统计计算、缺数据、多版本数值），与它收到的验证文本无关；失败小批的推理文字提到验证文本的只有每臂 0–2/18。
所以问题从"哪种 rubric 好"变成"analyst 到底用不用验证文本"。本研究在同一仪器（`rubric_form` 的配对反馈块）里只
多变一件事：**失败小批 analyst 的系统提示**——把验证文本从"可参考"改成"必须逐条回应"。主流程（训练执行 → rubric
反馈 → analyst → 候选 → 选择集）不变，冻结的学习代码不动。

## 2 臂（`skillopt/feedback_study/rubric_binding.py`，协议 `fivebench-rubric-binding-study-v1`）

| 臂 | 反馈 | analyst 系统提示 |
| --- | --- | --- |
| `scalar` | 只有对/错 | v10 的 |
| `default_text` | bench 默认 rubric（v10 现状），模型判定 | v10 的（授权时含 rubric 前言） |
| `default_text_bound` | **与 `default_text` 同一份**封存报告与轨迹 | v10 的 + 绑定前言（仅失败小批） |
| `global_text` | 通用 rubric，模型判定（OfficeQA 上描述性领先的臂） | v10 的 |
| `global_text_bound` | **与 `global_text` 同一份**报告与轨迹 | v10 的 + 绑定前言（仅失败小批） |

绑定臂复用基臂的判定、校准与封存报告（零额外判定调用；`propose_arm(verifier_label=基臂步标签, analyst_binding=…)`
认证的是基臂的报告）。基臂 rubric 在某块未获授权（没有验证文本）时，绑定臂拿到**与基臂完全相同**的提示与反馈，
记 `binding_applied=false`——这对臂在该块只差提案采样。绑定前言（`BINDING["preamble"]`，附在冻结的
`VERIFIER_PREAMBLE` 之后）：

> VERIFICATION NOTES ARE BINDING. Some failed rows end with a verifier note that names specific checks which FAILED
> on that output. Treat every failed check as the primary finding for its row. Before anything else, write the edit
> that would have made that output pass that check -- a reusable rule or procedure in the skill's own terms, never
> the row's values, quotes or entities -- and place these edits FIRST in `edits`, one per distinct failed check. If
> an existing skill rule already covers a failed check, say which rule in `reasoning` instead of adding a duplicate.
> Stay within the edit budget L you are given: when more distinct failed checks remain than L allows, merge checks of
> one kind into one rule and give priority to the checks that failed on the most rows; name in `reasoning` every
> failed check that received no edit and why. Only after every failed check is answered may you add edits motivated
> by your own reading of the failures. A passed check is not a problem to fix.

（登记的文本以 `rubric_binding.BINDING["preamble"]` 为准；Codex 第二轮后同步。）

## 3 设置

- 模板与 rubric 形式研究相同：OfficeQA `oq-v10-z41-gv`（父＝零样本指令 bzero，训练抽样 48 题/块，选择集＝124 道生成题
  / 38 家族）；之后 SearchQA `searchqa-v10gen-b06`（训练 128、选择集 112 家族）。预算沿用 `rubric_form.BUDGETS`。
- 一块一研究串联（队列 z18，快照 z4；`--series` 标签 a…h，OfficeQA 想要 6 块、至多 8 次尝试；SearchQA 想要 6 块、至多
  9 次），事后按块合并（合并脚本同 rubric 形式研究的规则：协议除标签与块数外完全相同、不重复计块、pending 保留不续跑）。
- 每块约 48 次训练求解 + 2×48 次判定 + 5 次提案（各约 10 次调用）+ 6×124 次选择集求解 ≈ 950 次调用，约 35 分钟
  （OfficeQA）；SearchQA 约 128 + 256 + 50 + 6×168 ≈ 1,450 次。

## 4 读数规则（事先定下）

- **主对比**只有两个：`global_text_bound − global_text`、`default_text_bound − default_text`，按块算候选通过数之差，
  只计**绑定实际应用的块**（基臂授权），做精确的块级符号翻转检验（双侧，alpha 0.05，每个主对比各自检验、不作多重
  校正）：6 个信息块同向才"支持"；信息块少于 6 个只作描述。**领头对比**是 `global_text_bound − global_text`
  （OfficeQA 上通用 rubric 六块都授权）；"绑定被支持"指领头对比被支持，`default_text` 那一对是数据集内的复现，
  单独报告、自身不构成结论（它在 OfficeQA 上 6 块里只授权 4 块，很可能只能描述）。
- 其他对比（各臂 − `scalar`、`global_text − default_text`）与位置配对胜负只作描述；**只有主对比可以被标为"支持"**，
  其余对比即使 6 块同向也只是描述（代码里 `supported` 以 `primary` 为前提）。
- **绑定前言与编辑预算**：冻结的 analyst 提示限制每次提案至多 L（=4）条编辑，并会静默截断多余的编辑。前言因此登记了
  合并与优先规则（失败检查多于 L 时按类合并、按失败行数排优先、在 `reasoning` 里点名没有得到编辑的检查），不改
  冻结的更新器。
- **噪声参照**：绑定臂与基臂的差包含提案采样噪声（同一反馈、同一种子下两次独立的 analyst 采样）。rubric 形式研究里
  `compliance_code`（六块都未授权，实为标量反馈）− `scalar` 的按块差为 [−4, +6, +14, +7, −9, −7]——同一反馈下两次提案
  的波动就是这个量级，这就是要求 6 块同向的原因。
- **结论的写法**：若领头对比被支持且为正——"在这些块上，绑定提示提出的候选在选择集上高于不绑定的"，下一步是把它作为
  v10 分析提示的替代候选做预登记的确证（两个数据集）；若支持且为负——绑定提示提出的候选更差（analyst 被低价值检查
  牵着走）；**若不支持——只能写"在这个设计下没有建立候选得分的差别"**，不能写成"绑定无用"或"瓶颈在检查内容"：信息块
  少于 6 时根本不可能显著；6 块时符号翻转检验只看方向（6 块同向即 p＝2/64，与差的大小无关），所以"支持"也不说明
  差有多大——差的大小只由按块的差与合并的位置胜负描述。检验是双侧的：被支持的差也可能为负。
- **提示分配不等于照做**：`binding_applied` 记录的是提示的分配，不是 analyst 是否真的回应了检查；merge/rank 也可能丢掉
  由检查引出的编辑。"analyst 用了验证文本"这一判断只能来自**另一项零调用审计**（读封存的原始提案：绑定臂的前几条编辑
  是否点名了失败的检查、`reasoning` 是否列出未处理的检查），与候选得分之差分开报告。
- 边界同 rubric 形式研究：一个父 Skill、生成题选择集、候选从未过门与留出评测；不是方法效果。

## 5 不做的事

不改 `continual_learning/*`；不读测试题；pending 的研究不续跑；本研究不替换任何正式阶段的分析提示。
