# 数据来源、许可与处理说明

本目录是 Evolve-Skill 自有实验记录的精选公开摘录，不是完整 benchmark 数据镜像。

- **HumanEval**：OpenAI，[原项目](https://github.com/openai/human-eval)，[原 MIT 许可](https://github.com/openai/human-eval/blob/master/LICENSE)。部分生成代码的 docstring 复述了原公开题面；保留归属并附 [MIT 许可副本](licenses/HumanEval-MIT.txt)。案例 76、141、145 的独立题意概述为本仓库整理，不替代原任务定义。
- **HumanEval+ / EvalPlus**：[EvalPlus](https://github.com/evalplus/evalplus)，本次使用 HumanEval+ v0.1.10。该项目[许可为 Apache-2.0，部分执行代码另遵循 MIT](https://github.com/evalplus/evalplus/blob/master/LICENSE)。本包只提供本实验的生成产物、任务 ID 和执行计数，没有再分发增强测试输入、参考源码或 EvalPlus 软件快照。
- **MBPP / Mostly Basic Python Problems**：Google Research，[数据卡](https://huggingface.co/datasets/google-research-datasets/mbpp)，[项目](https://github.com/google-research/google-research/tree/master/mbpp)，数据卡标注 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。保留任务 643 的公开反馈片段和生成代码，以说明验证盲区；其余最终表仅为任务 ID 与本实验结果，不含完整题库或隐藏断言。

本包所做处理：选择四个 development 说明案例；用中文概述部分题意；按白名单提取实际产物与执行字段；去除服务配置、服务器路径、原始传输内容及隐藏答案材料；将相同 Candidate 别名合并。真实代码、观察值及最终状态未修订。父／候选 Skill 文件仅可能追加展示用末尾换行，原文哈希另存。

研究者的解释、模型生成文本和 benchmark 上游内容的来源不同。不得因仓库根目录使用 MIT，就声称上游 MBPP 数据被重新授权为 MIT；原始任务仍遵循其许可。模型代码是未经部署认证的实验产物，示例入口不执行它。

完整私有原始记录没有随包公开。文件哈希便于检查一致性，不保证原始执行真实性，不保证模型训练时未见过公开题目，也不代表方法效果或安全性认证。
