# 文档作用域规范

> 适用于 `docs/**`，并由根路由扩展到 `README.md` 和 `CONTRIBUTING.md`。本文件管理文档事实层与历史资料，不改变源码、测试或正式 schema 所证明的实现事实。

## DOCS-AUTHORITY-001：事实层级

文档与规则的优先关系：

1. 根 `AGENTS.md` 与当前任务适用的作用域 `AGENTS.md`：项目约束。
2. 当前源码、测试、迁移和正式 API schema：实现事实。
3. 已接受 ADR 与人工审阅的 Mermaid：稳定设计意图。
4. README、CONTRIBUTING、架构说明、Prompt Catalog、Roadmap：面向人的同步摘要或计划。
5. 代码图谱、Repomix、自动 Wiki：可重建检索或解释层。
6. archive、superpowers 和既有 test report：历史证据。

较低层不能覆盖较高层。发现冲突时必须修正文档或明确记录实现偏差，不能把自动推断直接提升为规则或 ADR。

## DOCS-MAINTENANCE-001：同步规则

新增或改变功能、依赖、目录、公共接口、数据表或部署方式时，先按 `GLOBAL-CHANGE-GATE-001` 更新规则并确认，然后同步：

- README：用户能感知的能力、安装、启动和配置。
- CONTRIBUTING：开发环境、验证和 PR 检查清单。
- `docs/architecture.md`：稳定边界、所有权和人工 Mermaid。
- ADR：有长期影响或明确取舍的架构决策。
- Prompt Catalog：提示词、工作流、输入输出契约。
- 测试或验收报告：无法仅由自动测试证明的结果。

文档必须避免：

- 把 Studio 1.0 目标能力写成当前 `1.0.0` 版本。
- 在同一活跃文档混合互相冲突的 MVP 与当前约束。
- 重复修订编号或引用易漂移的“第 N 节”；跨文件引用使用稳定规则 ID 和文件路径。
- 描述已删除的路由、目录、组件、CLI 或历史大纲入口。
- 把 Qdrant、Redis、Postgres、DeepWiki 或其他可选服务写成默认启动条件。
- 把真实 LLM 手工验收写成默认测试。
- 把未经核验的代码图谱、Wiki 或模型总结写成已实现事实。

## DOCS-ADR-001：ADR

- ADR 使用四位顺序编号，包含背景、决策、后果、备选方案、验证和关联。
- 状态只有 `Proposed`、`Accepted`、`Superseded`、`Rejected`。
- 用户明确确认并已实现的决策才可标为 `Accepted`。
- 决策变化时新增 ADR，并把旧 ADR 标为 `Superseded`；不改写历史决策正文。
- “关联规则”必须写稳定规则 ID 与作用域文件路径，不再只写章节号。
- 图谱、快照或 Wiki 不能自动创建、接受、修改或替代 ADR。

## DOCS-ARCHITECTURE-001：架构与 Mermaid

- Mermaid 只保存 Markdown 文本图源，不新增产品前端运行时包。
- 架构图必须由人工审阅，并与当前源码所有权一致。
- 自动生成图片、图谱关系和 Wiki 页面不是架构源。
- 拓扑图不得恢复为历史大纲产品组件。
- 跨层调用链优先表示稳定所有权和审批边界，避免复制所有实现细节。
- 当前 Creation Star 正式 session 由 `StudioService` 编排，旧 draw/commit 才委托 `CreationStarAgentService`；相关架构文档不得混淆。

## DOCS-AI-CONTEXT-001：AI 开发文档

AI 上下文的工具版本、权限、缓存和 DeepWiki 状态由 `scripts/AGENTS.md` 的 `TOOLING-AI-CONTEXT-001` 所有。

- `docs/ai-assisted-development.md` 说明安装、升级、卸载、隐私和故障处理，不得形成另一套权限规则。
- `docs/architecture.md` 只记录人工审阅的上下文层结构。
- `docs/test-reports/` 记录当次工作树和工具版本下的验收证据；新状态使用新报告，不回写旧报告冒充当时事实。
- DeepWiki Open 当前未启用，文档不得提供会被误解为已授权执行的默认运行步骤。

## DOCS-HISTORY-001：历史资料

- `docs/archive/legacy-agents-before-2026-07-04-cleanup.md` 与其他 archive 文件只用于追溯。
- `docs/superpowers/` 中的旧计划和规格不再约束当前开发。
- 既有 test report 只证明报告日期和当时工作树，不自动证明当前状态。
- 历史文件可以保留旧术语、旧章节号和当时的单文件 `AGENTS.md` 描述；不要批量改写历史。
- 活跃文档引用历史资料时必须明确标注“历史”，不能把它当恢复已删除实现的依据。

## DOCS-VERIFY-001：文档验证

文档或规则变更至少运行：

```bash
python3 scripts/verify-agents-guidance.py
rg -n '第 1[5] 节|AGENTS\.md.*1[3]\.1' README.md CONTRIBUTING.md docs \
  --glob '!archive/**' --glob '!superpowers/**' --glob '!test-reports/**'
```

若命中活跃文档，改为稳定规则 ID；若命中历史目录则保留历史原文。涉及用户启动流程时还应运行 README 中对应命令或 `docker compose config --quiet`。
