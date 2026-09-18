# Evolve-Skill

基于 [Microsoft SkillOpt v0.2.0](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0) 的研究分支，探索 **Cross-Domain Safe Skill Evolution：面向跨领域稳定性的 Skill 与验证器协同进化**。

我们不追求在每个 benchmark 上都拿最高分，而是希望 Skill 在改善部分任务的同时，尽量不损害其他领域的能力，降低过拟合和负迁移。

## 我们在做什么

- **Skill 进化**：利用任务执行证据和结构化反馈更新 Skill，比较全文更新与“共享核心＋领域局部规则”等表示。
- **Skill 验证**：结合可执行检查、Coding Rubric 与受限资料检索，探索更有效的验证策略；新策略先独立校准，再用于反馈。
- **协同与范围控制**：验证反馈指导下一轮 Skill 更新；候选经过独立验证门决定是否使用，证据不足时限制范围或回退到 No-Skill。

开发、验证器校准、准入确认和最终评测按各实验协议隔离。最终评测前冻结 Skill 与使用策略，同时报告原始 Skill 表现、逐域退化和回退比例，避免把“全部回退”当成泛化成功。

## 当前进展

已实现跨域实验框架、验证器校准与反馈闭环、配对评测，以及带执行回执的断点恢复和离线审计。历史 V18 在 SearchQA 与 MBPP-sanitized 兼容子集上比较全文更新和分层 Skill。

新主线聚焦 **Research 驱动的机制 Rubric 如何改善 Skill 验证与准入**。已建立公开证据／隐藏审计隔离，并接通阶段二的有界 Research 提案、条件化检查、Linux 隔离执行及独立校准／审计工程链路。真实方法效果和新主线的 Skill 准入／更新仍待验证。见[主线说明与运行命令](docs/skill-validation-mainline.md)、[阶段一验收报告](docs/skill-validation-stage1-report-20260917.md)。

最新工程验收见 [阶段二报告](docs/skill-validation-stage2-report-20260918.md)：本地 907 项测试通过、Linux 126 次正常执行，另完成真实 API 接口复测；这些不等于 Research 已提高泛化性能。

目前仍是研究原型：已有局部学习收益，但尚未证明稳定的跨域泛化优势。Research 目前是限定来源的检索与引用核验，并非完整自主 DeepResearch；V18 本轮不新增 Research 干预，两个领域均参与开发，不属于未见领域测试。

## 代码与文档

| 位置 | 内容 |
| --- | --- |
| `skillopt/cross_domain/`、`skillopt/scope_evolution_v2/` | 跨域评测、范围门与负迁移分析 |
| `skillopt/validator_pilot/`、`skillopt/coevolution*/` | 可执行验证、反馈、Skill／验证器进化与版本化实验 |
| `skillopt/skill_validation/` | 新主线：证据隔离、有界 Research、可执行条件检查、独立校准与固定产物回放 |
| `scripts/`、`configs/`、`tests/` | 运行／审计入口、配置与回归测试 |
| [研究索引](docs/research-overview.md) | 阅读顺序、实验边界与复现要求 |
| [V18 协议](docs/coevolution-v18-protocol.md) | 最新实验设计、对照、预算与评价方式 |

保留历史版本是为了支持依赖与冻结实验审计，不代表它们都是推荐的新实验入口。

## 安装与离线测试

使用 Python 3.10+，在独立环境中安装：

```bash
python -m pip install -e ".[dev,searchqa,cross-domain,validator-pilot]"
python -m pytest -q tests/test_coevolution_v18_*.py
python -m pytest -q tests/test_skill_validation_*.py
```

上述测试使用合成数据和模拟接口，不需要 API Key。历史 Coding 实验依赖 macOS 系统沙箱；新主线另有受限的 Linux Docker Python／JSON 执行器，不等同于完整仓库 benchmark 环境。

API 配置参考 [`.env.example`](.env.example)，实际密钥仅放本地 `.env`。仓库不包含密钥、原始调用日志、历史运行缓存及第三方数据快照。**精确复现历史实验还需要匹配的数据版本、父 Skill 和审计材料，不是 clone 后即可一键复现。** 详见[复现边界](docs/research-overview.md#复现与发布边界)。

## 致谢

原始训练框架来自 [Microsoft SkillOpt](https://github.com/microsoft/SkillOpt)，上游使用说明见 [docs/index.md](docs/index.md)。保留原项目 [MIT License](LICENSE)；第三方数据与任务遵循各自授权，不自动适用本仓库许可。
