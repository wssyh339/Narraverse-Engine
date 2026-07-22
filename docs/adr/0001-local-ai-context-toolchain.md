# ADR-0001：采用本地只读的 AI 开发上下文工具链

- 状态：Superseded
- 日期：2026-07-22
- 决策者：项目维护者
- 影响范围：开发期代码检索、架构文档和可移植 AI 上下文；不影响产品运行时

## 背景

项目同时包含 FastAPI、React/TypeScript、SQLite、三条 Agent 产品线、双 API 前缀以及人工审批边界。仅靠逐文件阅读能够确认事实，但在追踪跨语言调用链、路由与影响范围时成本较高。项目又要求本地优先、默认部署简单、用户小说与密钥不外泄，因此不能为 AI coding 引入默认云服务、外部图数据库或会自动写入仓库的工具链。

## 决策

按以下顺序接入三个开发期层次：

1. 使用锁定的 `codebase-memory-mcp 0.9.0` 建立当前仓库独立的本地代码图谱。索引与刷新只能由 `scripts/code-intel.sh` 显式执行，自动索引和 watcher 关闭。
2. 使用 Markdown ADR 与人工审阅的 Mermaid 图记录架构决策。它们是文档事实层，工具推断不能自动改写它们。
3. 使用锁定的 `Repomix 1.17.0` 按需生成可删除的上下文快照，不把它加入产品依赖。

Codex 通过可信项目的 `.codex/config.toml` 连接图谱 MCP，只允许 `search_graph`、`query_graph`、`trace_path`、`get_code_snippet`、`get_graph_schema`、`get_architecture`、`search_code`、`index_status` 和 `detect_changes` 九个只读查询工具。索引、删除项目、ADR 写入、trace 导入、rename、shell、文件写入、任意图写入及跨仓库查询均不暴露给模型。

索引写入 `.codebase-memory/`，Repomix 输出写入 `.ai-context/`；两者都是 Git 忽略的可重建敏感数据。`.cbmignore`、`.repomixignore` 和 `.gitignore` 共同排除密钥、数据库、小说数据、导出、备份、日志、构建产物和工具缓存。

DeepWiki Open 不属于本次启用范围。候选提交保持锁定，但只有前三阶段验收通过且用户再次明确确认后才能在仓库外缓存目录中以可选只读方式运行。

该工具链不得修改产品 API、数据库表、前端页面、默认 Compose 服务、后端 requirements 或前端 package manifest，也不得成为测试、构建或启动前置条件。

## 后果

### 正向影响

- AI coding 客户端可以用受限查询定位符号、调用链、路由和影响范围。
- 人工 ADR 与 Mermaid 保留可审阅、可追溯的设计意图。
- Repomix 提供可移植且可重建的上下文快照。
- 工具缺失、缓存删除或 MCP 关闭时，产品仍可独立开发、测试和运行。

### 成本与风险

- 图谱和快照可能陈旧或解析错误，必须与源码、测试和 `rg` 交叉验证。
- 源码派生数据仍可能敏感，需要多层排除和每次生成后的检查。
- 锁定版本需要人工维护；升级必须重新确认、重建和验收。
- 项目级 MCP 配置只有在 Codex 信任该仓库后才会加载。

## 备选方案

- 仅使用 `rg` 和人工阅读：保留为最终核验手段，但不足以单独降低跨语言调用链的导航成本。
- 默认引入 Neo4j、FalkorDB、Graphiti 或 Backstage：增加服务、数据和部署负担，与当前本地优先及默认双服务 Compose 边界不符。
- 先启用自动 Wiki：自动总结容易被误当作事实，且可能引入远程模型和额外缓存，因此推迟到独立确认。
- 允许 MCP 自动索引或写入：扩大模型权限和后台状态变化，未采纳。

## 验证方式

- 运行 `scripts/verify-ai-context.sh` 检查版本、工具白名单、索引根目录、敏感路径和 Git 忽略状态。
- 至少使用 10 个覆盖 Python、TypeScript、双 API 前缀、三条 Agent 产品线、批量任务和正典审批的问题，将图谱结果与源码及 `rg` 逐项比对。
- 生成 Repomix 快照后记录文件数、字符或 token 规模，并证明敏感路径未进入输出。
- 确认默认后端测试、前端测试与构建、`docker compose config --quiet` 不依赖这些工具。

## 关联

- 相关稳定规则：`scripts/AGENTS.md` 的 `TOOLING-AI-CONTEXT-001`
- 开发指南：`docs/ai-assisted-development.md`
- 架构概览：`docs/architecture.md`
- Codex 官方配置参考：https://developers.openai.com/codex/config-reference#configtoml
- Codex 官方 MCP 说明：https://developers.openai.com/codex/mcp
- 取代的 ADR：无
- 被取代于：ADR-0003
