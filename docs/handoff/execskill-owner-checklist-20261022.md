# 路线 B（fivebench-execskill-v1）需要负责人亲手做的三件事（10/22 早；09:1x 更正第 1 项）

登记稿：`execskill-registration-v1-20261021.md`。所有待决事项已按默认值生效（§14）。下面三件按登记只能由负责人写，我不代签。

## 1. 测试排除的同意书（冒烟第 0 段之前要写好；只写一次）

**已完成**：负责人 10/22 09:18 写入（内容 sha256 前 16 位 `77872f24418fd20f`），只读核对 `consent` 判为有效。

**它授权什么**（登记 §8.1、§3.1、§10 S0；代码 `skillopt/execskill/exclusion.py`）：允许代码在冒烟第 0 段打开 ALFWorld 和
SearchQA 的测试集各一次，只做下面三件事。记录里只有计数和哈希，不打印也不保存任何题面、答案、测试编号或局文件路径。

1. ALFWorld：核实测试集的局全部来自 `valid_unseen`，并且和我们要用来出新验证局的 3,514 个训练局一个都不重合。不满足就停下报告。
2. SearchQA：把新题块里与测试题编号相同或问题文本相同的题剔掉（新题块只有正式链用到）。
3. 从这两个测试集各取几条文本做"金丝雀"指纹（只存长度和哈希前 16 位）。之后每次运行的产物都会被扫描，查有没有混进测试原文。

**为什么单列一份**：冻结的读测试集同意书 `consent.json` 一写就是"允许在测试集上评分"（要求 `test_evaluation = true`），
范围远大于计数核对。所以登记单列这份小同意书，只覆盖这两项排除操作。排除代码只认它，换成别的文件或别的键集合都会拒绝。

**没有它会怎样**（10/22 09:1x 更正；早先写的"只影响冒烟里 ALFWorld 的部分，其余段照常"不准确）：冒烟第 0 段有一行"题源"检查
要用到这两份排除记录，这行过不了，冒烟整体就不能判通过；生成任何运行清单（包括试点）也要先绑定这两份排除记录。所以它是冒烟通过
和试点的前置条件。第 0 段的判定只能写一次，同意书写好之前我不判第 0 段。试点不需要再放第二份：试点清单直接引用冒烟里做出的排除记录。

**文件位置**（开发机）：`/data/execskill-20261021-pre/smoke/shared/exclusion-consent.json`。目录现在还不存在，下面的命令会建。

**内容**：键必须恰好是这四个；`by` 必须是 `owner`；`date` 写签的那天；`note` 可以换成你自己的一句话。

```json
{"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner", "date": "2026-10-22", "note": "同意做测试排除核对，只看计数"}
```

**写法**（登录开发机后粘贴这一行）：

```bash
mkdir -p /data/execskill-20261021-pre/smoke/shared && echo '{"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner", "date": "2026-10-22", "note": "同意做测试排除核对，只看计数"}' > /data/execskill-20261021-pre/smoke/shared/exclusion-consent.json
```

也可以在本机的 Claude Code 里用 `!` 前缀运行同样内容（把 JSON 用 `echo ... | ssh <开发机登录> 'mkdir -p ... && cat > ...'` 送过去）。
写完之后不要再改：两份排除记录都会存下这份内容的哈希，改了就和记录对不上。

**核对**（只读，不碰测试集；我来跑，你也可以跑）：

```bash
cd /data/execskill-dev && /root/continual-alf-prep-20260928/env/bin/python -B scripts/run_execskill.py consent --root /data/execskill-20261021-pre/smoke
```

应输出 `{"exclusion": "valid"}`。这一行 JSON 经本机到开发机的写法已在开发机的临时目录里试过（10/22 09:1x，判为有效，临时文件已删）。

## 2. 读测试集的同意书（试点最后一次读取前才需要；现在不用写）

登记 §8.1：`{"test_evaluation": true, "sheet_test_qualification": true, "multi_arm_arms": ["F","C","P_F","T_F","twins"], "by": "owner", "date": "...", "note": "..."}`，放在试点根目录 `shared/consent.json`。读取前还要先写好并哈希正式链的增补登记（决定 #32 默认：先写增补再解封）。

## 3. 试点的启动（付费，默认方案：两条链 SpreadsheetBench → OfficeQA；做题上限每条链 1.8 亿、合计 3.6 亿 token；GLM 角色合计 6,000 万）

冒烟全部通过后我会把 `smoke-result.json`、费用实测和清单摆好，等你一句"开"。

## 已按默认生效、无需再决定的事（摘录）

试点顺序默认 SB → OQ（我原建议 SB → ALFWorld 未采用）；开发机残留的 31 个空转进程不动（相关检查记"无法判断"）；冒烟只用 deepseek-v4.1-flash（经你给的接口）；正式链两条（GLM-5.3 与 deepseek-v4.1-flash 做题，方法角色都是 GLM-5.3）；"没有可复用的验证集"的措辞（决定 #31）；先写正式链增补再解封试点测试分数（#32）。

> **10/22 13:2x 更新**：负责人授权“冒烟通过后直接开试点”（原话：“不用，你直接开试点就行”）。试点启动不再需要负责人亲手操作；仍需负责人本人做的只剩一件：试点最后读测试集之前写读测试集同意书（`shared/consent.json`），到那一步会暂停等待。

> **10/22 15:01 更新：读测试集同意书已由负责人本人写入**（负责人 15:1x："只要能做到hold-out评测就可以了"）。文件
> `/data/execskill-20261021-pilot/shared/consent.json`（252 字节，内容 sha256 前 16 位 `2748d886fcb1b207`），只读核对
> `run_execskill.py consent --root /data/execskill-20261021-pilot` 判为 `{"test_read": "valid"}`。以后不要改动它（读取时会记下它的哈希）。
> 若冒烟不过、v1.1 把试点换到新目录，需要在新目录再写一次。负责人现在没有待办的手动步骤。
