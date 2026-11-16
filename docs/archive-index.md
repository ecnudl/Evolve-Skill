# docs 归档索引（2026-11-02）

按负责人 2026-11-02 10:5x 要求整理 docs 目录：只保留从 README、AGENTS、docs/research-overview.md、docs/project-status.md、
docs/current-workflow.md、docs/results-and-lessons.md、docs/agent-start-here.md、docs/index.md 出发能链到的文件，以及三份通用文件
（contributing.md、review_guidelines.md、guideline.html）。其余文件打包移出仓库，内容一个字节不少；已提交过的文件在 git 历史里也有。

归档位置（仓库外）：`<workspace>/SkillOpt-archive/docs-archive-20261102/`

恢复方法：`tar -xzf <包>.tar.gz -C <repo>`（包内路径以 docs/ 开头）；已提交过的单个文件也可以 `git checkout HEAD -- <路径>`。

**2026-11-16 更正**：下面列出的 14 份协议文档（`coevolution-v3`、`v4`、`v4-research-smoke`、`v5`、`v6`、`v7`、`v9-source`、`v10`、`v11`、`v12`、`v14`、`v15`、`v16`、`v17` 的协议）被冻结研究的代码和测试按路径引用（协议文件的哈希与必需文件清单，其中一项测试在 CI 里），按 AGENTS.md“保留冻结的历史协议”已放回 `docs/`，不再算归档；包里的副本照旧保留。

## notes-top-level-2026-09-10.tar.gz（75 个文件，0.50 MB，其中已提交 19 个）

- docs/coevolution-progress-20260914.md（未提交）
- docs/coevolution-v10-implementation-20260914.md（未提交）
- docs/coevolution-v10-protocol.md
- docs/coevolution-v10-smoke-results-20260914.md（未提交）
- docs/coevolution-v11-formal-results-20260914.md（未提交）
- docs/coevolution-v11-protocol.md
- docs/coevolution-v11-smoke-results-20260914.md（未提交）
- docs/coevolution-v12-analysis-20260915.md（未提交）
- docs/coevolution-v12-protocol.md
- docs/coevolution-v12-public-benchmark-next.md（未提交）
- docs/coevolution-v12-running.md（未提交）
- docs/coevolution-v12-smoke-diagnosis-20260915.md（未提交）
- docs/coevolution-v12-smoke-results-20260915.md（未提交）
- docs/coevolution-v14-analysis-20260915.md（未提交）
- docs/coevolution-v14-design-audit-20260915.md（未提交）
- docs/coevolution-v14-protocol.md
- docs/coevolution-v14-running.md（未提交）
- docs/coevolution-v14-smoke-results-20260915.md（未提交）
- docs/coevolution-v15-protocol.md
- docs/coevolution-v15-running.md（未提交）
- docs/coevolution-v15-smoke-results-20260915.md（未提交）
- docs/coevolution-v15-v16-progress-20260915.md（未提交）
- docs/coevolution-v16-pause-20260915.md（未提交）
- docs/coevolution-v16-protocol.md
- docs/coevolution-v16-sleep-recovery-20260916.md（未提交）
- docs/coevolution-v16-status-analysis-20260917.md（未提交）
- docs/coevolution-v17-analysis-20260917.md（未提交）
- docs/coevolution-v17-plan-and-running-20260917.md（未提交）
- docs/coevolution-v17-protocol.md
- docs/coevolution-v17-results-20260917.md
- docs/coevolution-v17-scientific-audit-20260917.md
- docs/coevolution-v17-smoke-results-20260917.md（未提交）
- docs/coevolution-v18-running-20260917.md（未提交）
- docs/coevolution-v3-protocol-20260909.md
- docs/coevolution-v3-results-20260909.md（未提交）
- docs/coevolution-v3-running.md（未提交）
- docs/coevolution-v4-cross-domain-readiness.md（未提交）
- docs/coevolution-v4-protocol-20260909.md
- docs/coevolution-v4-research-smoke-protocol.md
- docs/coevolution-v4-results-20260910.md（未提交）
- docs/coevolution-v4-running.md（未提交）
- docs/coevolution-v5-implementation.md（未提交）
- docs/coevolution-v5-protocol.md
- docs/coevolution-v5-results-20260911.md（未提交）
- docs/coevolution-v6-implementation.md（未提交）
- docs/coevolution-v6-protocol.md
- docs/coevolution-v6-results-20260911.md（未提交）
- docs/coevolution-v6-running.md（未提交）
- docs/coevolution-v7-implementation.md（未提交）
- docs/coevolution-v7-pause-and-resume-20260911.md（未提交）
- docs/coevolution-v7-protocol.md
- docs/coevolution-v7-results-20260911.md（未提交）
- docs/coevolution-v7-resumed-results-20260912.md（未提交）
- docs/coevolution-v7-running.md（未提交）
- docs/coevolution-v8-running.md（未提交）
- docs/coevolution-v9-coding-readiness.md（未提交）
- docs/coevolution-v9-implementation.md（未提交）
- docs/coevolution-v9-next-study-draft.md（未提交）
- docs/coevolution-v9-progress-20260913.md（未提交）
- docs/coevolution-v9-running.md（未提交）
- docs/coevolution-v9-smoke-results-20260913.md（未提交）
- docs/coevolution-v9-source-protocol.md
- docs/cross-domain-objective-and-evaluation.md
- docs/experiment-summary-brief-20260910.md（未提交）
- docs/overnight-cross-domain-plan.md（未提交）
- docs/research-weekly-progress-20260910-20260916.md（未提交）
- docs/skill-validation-api-recovery-20260920.md（未提交）
- docs/skill-validation-bigmodel-launch-20260922.md（未提交）
- docs/skill-validation-bigmodel-run-20260921.md（未提交）
- docs/skill-validation-stage1-report-20260917.md
- docs/skill-validation-stage2-report-20260918.md
- docs/source-retention-audit.md（未提交）
- docs/source_retention_session_mvp.md（未提交）
- docs/verified400-pairing-audit-20260917.md（未提交）
- docs/verified400-staging-20260915.md（未提交）

## handoff-scripts-and-diffs.tar.gz（41 个文件，0.22 MB，其中已提交 40 个）

- docs/handoff/active-evidence-fixed-parent-20261011.diff
- docs/handoff/active-evidence-learn-from-b-queue-u2-20261012.sh
- docs/handoff/active-evidence-learn-from-b-queue-u3-20261012.sh
- docs/handoff/active-evidence-learn-from-b-queue-u4-20261012.sh
- docs/handoff/active-evidence-learn-from-b-queue-u5-20261012.sh
- docs/handoff/active-evidence-probe-format-fix-20261011.diff
- docs/handoff/benchmark-replacement-queue-z6-20261013.sh
- docs/handoff/benchmark-replacement-queue-z7-20261013.sh
- docs/handoff/benchmark-replacement-queue-z8-20261013.sh
- docs/handoff/cross-bench-selection-queue-w1-20261013.sh
- docs/handoff/cross-bench-selection-queue-w2-20261013.sh
- docs/handoff/extension-livemath-queue-z13-20261014.sh
- docs/handoff/extension-livemath-queue-z13b-20261014.sh
- docs/handoff/extension-livemath-queue-z9-20261013.sh
- docs/handoff/extension-livemath-queue-z9a-20261013.sh
- docs/handoff/extension-livemath-queue-z9b-20261013.sh
- docs/handoff/extension-livemath-queue-z9c-20261014.sh
- docs/handoff/extension-officeqa-queue-z10-20261013.sh
- docs/handoff/extension-officeqa-queue-z11-20261014.sh
- docs/handoff/gate-pooled-replay-candidates-20261014.py
- docs/handoff/generalization-feedback-queue-g1-20261015.sh
- docs/handoff/generated-validation-fixed-parent-20261013.diff
- docs/handoff/generated-validation-queue-v1-20261013.sh
- docs/handoff/generated-validation-queue-z4-20261013.sh
- docs/handoff/generated-validation-stage-tool-20261013.diff
- docs/handoff/master-queue-z1-20261013-u6.sh
- docs/handoff/master-queue-z1-20261013-v1b.sh
- docs/handoff/master-queue-z1-20261013-v1c.sh
- docs/handoff/master-queue-z1-20261013-w3.sh
- docs/handoff/master-queue-z1-20261013-y1b.sh
- docs/handoff/master-queue-z1-20261013-z1.sh
- docs/handoff/overnight-report-20261031.md（未提交）
- docs/handoff/prompt-chain-analyst-profile-20261013.diff
- docs/handoff/prompt-chain-queue-y1-20261013.sh
- docs/handoff/rubric-binding-queue-z18-20261015.sh
- docs/handoff/rubric-exploration-queue-z14-20261014.sh
- docs/handoff/rubric-form-queue-z15-20261014.sh
- docs/handoff/rubric-form-queue-z16-20261014.sh
- docs/handoff/rubric-form-queue-z17-20261014.sh
- docs/handoff/solver-strength-probe-queue-20261015.sh
- docs/handoff/solver-strength-summary-20261015.py

## handoff-feasibility-20261021.tar.gz（55 个文件，1.43 MB，其中已提交 55 个）

- docs/handoff/feasibility-20261021/D1/report.md
- docs/handoff/feasibility-20261021/D10/critic-result.json
- docs/handoff/feasibility-20261021/D10/report.md
- docs/handoff/feasibility-20261021/D10/result.json
- docs/handoff/feasibility-20261021/D11/critic-result.json
- docs/handoff/feasibility-20261021/D11/result.json
- docs/handoff/feasibility-20261021/D12/report.md
- docs/handoff/feasibility-20261021/D12/result.json
- docs/handoff/feasibility-20261021/D13/critic-result.json
- docs/handoff/feasibility-20261021/D13/report.md
- docs/handoff/feasibility-20261021/D13/result.json
- docs/handoff/feasibility-20261021/D2/critic-result.json
- docs/handoff/feasibility-20261021/D2/report.md
- docs/handoff/feasibility-20261021/D2/result.json
- docs/handoff/feasibility-20261021/D3/critic-result.json
- docs/handoff/feasibility-20261021/D4/critic-result.json
- docs/handoff/feasibility-20261021/D4/report.md
- docs/handoff/feasibility-20261021/D4/result.json
- docs/handoff/feasibility-20261021/D5/report.md
- docs/handoff/feasibility-20261021/D5/result.json
- docs/handoff/feasibility-20261021/D6/critic-result.json
- docs/handoff/feasibility-20261021/D6/result.json
- docs/handoff/feasibility-20261021/D7/critic-result.json
- docs/handoff/feasibility-20261021/D7/report.md
- docs/handoff/feasibility-20261021/D7/result.json
- docs/handoff/feasibility-20261021/D8/critic-result.json
- docs/handoff/feasibility-20261021/D8/report.md
- docs/handoff/feasibility-20261021/D8/result.json
- docs/handoff/feasibility-20261021/D9/critic-result.json
- docs/handoff/feasibility-20261021/E1/critic-result.json
- docs/handoff/feasibility-20261021/E1/report.md
- docs/handoff/feasibility-20261021/E1/result.json
- docs/handoff/feasibility-20261021/E10/critic-result.json
- docs/handoff/feasibility-20261021/E10/report.md
- docs/handoff/feasibility-20261021/E10/result.json
- docs/handoff/feasibility-20261021/E2/critic-result.json
- docs/handoff/feasibility-20261021/E2/report.md
- docs/handoff/feasibility-20261021/E2/result.json
- docs/handoff/feasibility-20261021/E3/critic-result.json
- docs/handoff/feasibility-20261021/E3/result.json
- docs/handoff/feasibility-20261021/E4/critic-result.json
- docs/handoff/feasibility-20261021/E4/result.json
- docs/handoff/feasibility-20261021/E5/critic-result.json
- docs/handoff/feasibility-20261021/E5/result.json
- docs/handoff/feasibility-20261021/E6/critic-result.json
- docs/handoff/feasibility-20261021/E6/report.md
- docs/handoff/feasibility-20261021/E6/result.json
- docs/handoff/feasibility-20261021/E7/critic-result.json
- docs/handoff/feasibility-20261021/E7/result.json
- docs/handoff/feasibility-20261021/E8/critic-result.json
- docs/handoff/feasibility-20261021/E8/report.md
- docs/handoff/feasibility-20261021/E8/result.json
- docs/handoff/feasibility-20261021/E9/critic-result.json
- docs/handoff/feasibility-20261021/E9/report.md
- docs/handoff/feasibility-20261021/E9/result.json

## 直接删除

- docs/handoff/__pycache__ 下 7 个 .pyc（可再生成）

## 2026-11-13 清理：旧代码树、上个会话的临时副本

负责人 2026-11-13 批准清理 `<workspace>`。调查、复核和执行记录都在 `<local-scratch>/cleanup-20261112/`：各组调查报告和复核报告、各组清单 `manifest-*.json`、删除前的独立核查 `crosscheck.json`、删除日志 `delete-log-run.json`。下列压缩包和 git 备份在删除之前逐个核对过，每个文件夹里的 `RESTORE.md` 写了还原方法。路径相对于 `<workspace>`。

- `SkillOpt-archive/execskill-trees-20261113/execskill-ub/execskill-ub-worktree-changes.tar.gz`：已删除的本机代码树 `execskill-ub`（ZebraLogic 上限探针 zebra-ub，10/26）里全部改动和未跟踪文件，476 个，7.3 MB，不含缓存，包内路径相对树根；sha256 `fe756cde05e998b74ff9720100cd081db0a9852a1dd0a6cbc9f58a11dc1e1545`；同目录有逐文件 sha256 清单和 RESTORE.md。恢复：克隆 execskill-m9fix，`git checkout -b research/exec-skill-v23 f6e909b`，在树根 `tar -xzf`，再 `shasum -a 256 -c`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-method/execskill-method-worktree-changes.tar.gz`：已删除的本机代码树 `execskill-method`（路线 B v2.25 / main-v9 构建树，11/04 至 11/06）里全部改动和未跟踪文件，1364 个，201.9 MB，不含缓存，包内路径相对树根；sha256 `8114f888f1e740dd84e88853aba3e385a6e5445aa3d99b3f2de9ab2824fca962`；同目录有逐文件 sha256 清单和 RESTORE.md。恢复：克隆 execskill-m9fix，`git checkout -b research/exec-skill-v23 f6e909b`，在树根 `tar -xzf`，再 `shasum -a 256 -c`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-method/execskill-method-refs.bundle`：`execskill-method` 里的带注释标签 route-b-v2.19-frozen-20261102（标签对象 0a1c8dd → 提交 1de2a06，v2.19 冻结点）及这一个提交；前置提交 60af599 在 execskill-m9fix；sha256 `280cfb2ac1bc2f8d179e2170937939b60ffeb278d8e3cefb3eb021d63e122cc9`（三个树的包内容相同）；同一标签仍在 execskill-v29、execskill-base2。恢复：在 execskill-m9fix 的克隆里 `git fetch <包> 'refs/tags/*:refs/tags/*'`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-textskill/execskill-textskill-worktree-changes.tar.gz`：已删除的本机代码树 `execskill-textskill`（v2.24 文本技能 5x5 第一阶段构建树，11/04）里全部改动和未跟踪文件，1331 个，192.0 MB，不含缓存，包内路径相对树根；sha256 `094d396371df3883b0cf8ddc37b899e8c02fedc91edb2556b85e4ff4ce05de2c`；同目录有逐文件 sha256 清单和 RESTORE.md。恢复：克隆 execskill-m9fix，`git checkout -b research/exec-skill-v23 f6e909b`，在树根 `tar -xzf`，再 `shasum -a 256 -c`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-textskill/execskill-textskill-refs.bundle`：`execskill-textskill` 里的带注释标签 route-b-v2.19-frozen-20261102（标签对象 0a1c8dd → 提交 1de2a06，v2.19 冻结点）及这一个提交；前置提交 60af599 在 execskill-m9fix；sha256 `280cfb2ac1bc2f8d179e2170937939b60ffeb278d8e3cefb3eb021d63e122cc9`（三个树的包内容相同）；同一标签仍在 execskill-v29、execskill-base2。恢复：在 execskill-m9fix 的克隆里 `git fetch <包> 'refs/tags/*:refs/tags/*'`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-probe2/execskill-probe2-worktree-changes.tar.gz`：已删除的本机代码树 `execskill-probe2`（卡片分段探针 probe 2，11/03，账本第 203 行引用）里全部改动和未跟踪文件，1250 个，189.7 MB，不含缓存，包内路径相对树根；sha256 `00c45e3c6a3df0e9bc2f1f15ea6e9cf8e0f57d12d57dbaf0c3cfca9ea66020ee`；同目录有逐文件 sha256 清单和 RESTORE.md。恢复：克隆 execskill-m9fix，`git checkout -b research/exec-skill-v23 f6e909b`，在树根 `tar -xzf`，再 `shasum -a 256 -c`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-probe2/execskill-probe2-refs.bundle`：`execskill-probe2` 里的带注释标签 route-b-v2.19-frozen-20261102（标签对象 0a1c8dd → 提交 1de2a06，v2.19 冻结点）及这一个提交；前置提交 60af599 在 execskill-m9fix；sha256 `280cfb2ac1bc2f8d179e2170937939b60ffeb278d8e3cefb3eb021d63e122cc9`（三个树的包内容相同）；同一标签仍在 execskill-v29、execskill-base2。恢复：在 execskill-m9fix 的克隆里 `git fetch <包> 'refs/tags/*:refs/tags/*'`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-v226/execskill-v226-e589b5b-wip-r1-r3.bundle`：已删除的本地代码副本 `execskill-v226` 的 4 个分支（main e589b5b = main-v9 快照 v2.25 工作副本；v226-wip-r1 645eac2、r2 d638df7、r3 8150a57 = v2.26 写作和修复轮），自包含 bundle；也覆盖已删的 execskill-m9read（61b4bae 与 e589b5b 同一棵树）；sha256 `65157e128d23de05a730a9f218bd6897bbd688cd403fba89cc3a17bafbec5ac2`；恢复：`git clone -b main <bundle> execskill-v226`，再叠加同目录的工作区 tar，详见同目录 RESTORE.md。
- `SkillOpt-archive/execskill-trees-20261113/execskill-v226/execskill-v226-worktree-modified-untracked.tar.gz`：`execskill-v226` 删除前全部 45 个已修改 + 67 个未跟踪文件（共 112 个，不含缓存），路径相对于仓库根目录；sha256 `448ad9b86097831ca3daecb3804f99949a14ab375f56d188bc4201f0b21aafbe`；恢复：先按上一行 clone，再 `tar -xzf <tar> -C execskill-v226`。
- `SkillOpt-archive/execskill-trees-20261113/execskill-transfer/execskill-transfer-worktree-modified-untracked.tar.gz`：已删除的 `execskill-transfer`（基于提交 280dd58，在 execskill-m9fix 里）的 6 个未提交文件（T1 ZebraLogic 多选迁移脚本、测试、预注册和两份文档）；sha256 `fc3eb18081d27712be448b18e3553a45afbef3a37d7c7b77b687b85b33f24f78`；恢复：`git clone execskill-m9fix execskill-transfer && git -C execskill-transfer checkout -b research/exec-skill-transfer 280dd58 && tar -xzf <tar> -C execskill-transfer`，详见 RESTORE.md。
- `SkillOpt-archive/execskill-trees-20261113/execskill-t2a/execskill-t2a-1cd8d87.bundle`：已删除的 `execskill-t2a` 的 2 个独有提交：9f5b753（v2.27 sheet-hp-v7，台账引用；也等于已删的 execskill-sheet-hp 的完整工作区）和 1cd8d87（v2.28 alf-fresh-v11）；增量 bundle，前置提交 2c4f764 在 execskill-m9fix 和 <local-scratch>/typed-skills-v2-20261112.bundle 里；sha256 `b6902ba801b12a3388b04cefc8db9d6f0050f8b60009e2c35340898bd476fad4`；恢复：在 execskill-m9fix 的克隆里 `git fetch <bundle> research/exec-skill-alf-fresh:research/exec-skill-alf-fresh`，详见 RESTORE.md。
- `SkillOpt-archive/execskill-trees-20261113/execskill-membase2/execskill-membase2-825bb60.bundle`：已删除的 `execskill-membase2` 的 12 个独有提交（e988197 membase-v1、825bb60 membase-v2，均为台账引用）；增量 bundle，前置提交 46d6d65 在 execskill-m9fix 和 typed-skills-v2-20261112.bundle 里；sha256 `e2c2659deafb2e69ba6c4c91945ea193d5e114fec4c8604bf9d6859fad470092`；恢复：在 execskill-m9fix 的克隆里 `git fetch <bundle> research/exec-skill-membase2:research/exec-skill-membase2`，详见 RESTORE.md。
- `SkillOpt-archive/execskill-trees-20261113/execskill-rescore/execskill-rescore-74f453a.bundle`：已删除的 `execskill-rescore` 的全部 5 个提交（根提交 072e09b = v2.24 冻结快照 128187a 的副本，本机别处没有；另 4 个是格式宽容重评工具和测试），自包含 bundle；sha256 `6fdbe97880796c2e550eb43a075f541544aa2ca20a57c7a3bd44ba14ec188873`；恢复：`git clone -b main <bundle> execskill-rescore`，详见 RESTORE.md。
- `SkillOpt-archive/execskill-trees-20261113/execskill-sister/execskill-sister-4d47775.bundle`：已删除的 `execskill-sister` 的独有提交 4d47775（sister-v1，台账引用）；增量 bundle，前置提交 7aade78 在 execskill-m9fix 和 typed-skills-v2-20261112.bundle 里；sha256 `a594dc3268207b8bfa085987117ae09db8f1d24056ee37b27524a0bccb8f0d45`；恢复：在 execskill-m9fix 的克隆里 `git fetch <bundle> research/exec-skill-sister:research/exec-skill-sister`，详见 RESTORE.md。
- `SkillOpt-archive/session-96e313ec-cold-20261113/old-machine-sync-20261113.tar.gz`（31 个条目：28 文件 + 3 目录，535 MiB，sha256 a2745e5059ec86939bfa84abfaaa4e0be7855374a50fb9751dc1cad3e1ca1ad8）：旧机器 main-v7 运行的三个保留快照 old/sync-20261102-1803、old/sync-20261103-0304、old/sync-20261105-1014（最新最完整），old/*.sh 21 个运维脚本，old/data/old-transfer-1.tar.gz（发给旧机器的输入，含 11 个版本的 write-consent.py 和 probe-data-20261025 划分）；来源 <local-scratch>/session-96e313ec（= <local-scratch>），包内路径相对于它；恢复：`tar -xzf <包> -C <目标目录>`，见同目录 RESTORE.md。
- `SkillOpt-archive/session-96e313ec-cold-20261113/ts-results-20261108-1530.tar.gz`（1 个文件，247 MiB，sha256 259de28282e912f0cc29a79384484b23f222f4b64682249d82e6fee13c7ec1bd）：原样拷贝 session-96e313ec/old/ts-sync/ts-results-20261108-1530.tar.gz，即 v2.24 文本技能 5x5 结果包的 Mac 备份（与 -1134 字节相同，与账本记录的 dl 拷贝 ts-results-20261108-chain-end.tar.gz 同 hash）；恢复：直接拷回 old/ts-sync/ 或 `tar -xzf` 解开内容。
- `SkillOpt-archive/session-96e313ec-cold-20261113/cold-records-20261113.tar.gz`（20,283 个条目：19,113 文件 + 1,170 目录，344 MiB，解开 1,072 MiB，sha256 e2363de8bbc60b3ceaf119eee539c16133031f15a6e90c06d539e813db8b0dcb）：session-96e313ec 的冷记录：v221、v220（除 base-v220）、v223、v222（除 probe-results、v221-base2、execskill-v221.bundle，另含 v221-base2/scripts/card_probe.py）、night（除 tspr、membase-results；含唯一的提交 c97ea76 的 textskill-old.bundle）、audit-frozen 输出、base、m9fix、sheethp、mb2、transfer、arch、diag、draw、fig、sister 等小条目、v226-landed.patch、v226-wip-r1/r2/r3.bundle、根目录散文件和 wait-*.sh；包内路径相对于 session-96e313ec；恢复：`tar -xzf <包> -C <目标目录> [成员路径]`，见同目录 RESTORE.md。

没有单独打包、但内容另有完整副本而直接删除的：`execskill-v28`、`execskill-base`、`execskill-m9read`、`execskill-sheet-hp`、`execskill-v226-land`，以及上个会话临时目录副本里的旧同步快照和旧代码副本。已知仍指向已删文件夹的旧引用：`docs/results-and-lessons.md` 提到 `execskill-probe2`，`docs/current-workflow.md` 提到 `execskill-v28/docs/handoff/v28-20261026/V28-NOTES.md`，`docs/paper/scripts/baseline_synthetic.py` 的 `OTHER_TREE` 指向 `execskill-base`；这些文件在保留的 `execskill-v29` 里有逐字节相同的副本，或在上面的备份里。保留的 `execskill-v29` 和 `execskill-base2` 现在是 v28、v29 交接文档唯一的工作副本，以后清理时不要删。
