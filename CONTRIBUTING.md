# 贡献指南

感谢你愿意改进叙界推演引擎 / Narraverse Engine。

这是一个本地优先的 AI 长篇小说创作工作室。最有价值的贡献通常会提升可靠性、可追踪性、作者控制权或长篇结构能力。

开始修改前先阅读根 `AGENTS.md` 的路由表，再完整读取目标目录对应的 `backend/AGENTS.md`、`frontend/AGENTS.md`、`scripts/AGENTS.md` 或 `docs/AGENTS.md`。验证规则层级：

```bash
python3 scripts/verify-agents-guidance.py
```

## 开发环境

后端：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
```

前端：

```bash
cd frontend
corepack enable
corepack prepare pnpm@11.5.1 --activate
pnpm install
pnpm test
pnpm build
```

可选的本地 AI 代码上下文工具：

```bash
./scripts/code-intel.sh install
./scripts/code-intel.sh index
./scripts/build-ai-context.sh --profile tooling
./scripts/verify-ai-context.sh --static
# 修改索引、打包或代理边界后执行
./scripts/verify-ai-context.sh --full
```

这些工具不属于产品运行时。代码图谱的服务端代理固定只提供 `search_graph`、`query_graph`、`trace_path`、`get_code_snippet`、`get_graph_schema`、`get_architecture`、`search_code` 和 `index_status` 八个只读查询工具。默认文件成员来自 Git index，内容来自当前工作树；将成为贡献一部分的新文件必须最终通过 `git add` 进入 index，不要用 `--allow-untracked` 长期或批量绕过版本控制。该参数只用于明确的一次性本地草稿，并且必须给出精确路径，路径会记录在 manifest 中。

图谱输入与 Repomix 输入都生成独立的只读副本和 manifest，不使用指向工作树的硬链接。Repomix 提供 `full`、`backend`、`frontend`、`tooling` 四个 profile，以不可变输入副本构建快照；其独立 package/lock 在隔离目录中通过 `npm ci --ignore-scripts` 干净安装。图谱索引写入 `.codebase-memory/`，快照写入 `.ai-context/`，两者都不得提交。

`--static` 不运行第三方 AI 二进制，用于常规 CI/PR；`--full` 会重建图谱和快照并验证 MCP、manifest、排除规则与查询准确性，用于相关工具行为变更后的手动或定期验收。AI 给出的图谱或 Wiki 结论不是事实源；涉及架构取舍时，应核对源码、测试和当前任务适用的分层规则，并在 `docs/adr/` 中记录人工确认的决策。DeepWiki Open 继续禁用，不得克隆、安装、运行或生成 Wiki 缓存。详细边界见 [AI 辅助开发指南](docs/ai-assisted-development.md)。

## 适合贡献的方向

- **Agent 工作流**：保持 `creation_star`、`outline_debate`、`chapter_writing` 三条线相互独立。
- **提示词目录**：在 `backend/app/prompts/` 下新增可复用提示词，并通过 Prompt Catalog 注册。
- **正典系统**：改进角色、实体、世界事实、图谱、伏笔和连续性检查。
- **前端工作室**：优化长时间写作体验，但不要加入无关 SaaS 功能。
- **导出系统**：新增干净的本地格式或平台模板。

## 设计规则

- 不要绕过 AI 生成内容的“预览 → 确认 → 提交”流程。
- 前端代码不得读取或保存 LLM API Key。
- 不要无来源、无置信度、无更新原因地覆盖用户手写正典。
- 除非路线图明确改变，不要引入登录、云协作、支付或自动发布功能。
- 优先提交小而可测试的改动，避免大规模重写。
- 代码图谱服务端只允许上述八个查询工具；不要暴露索引、删除、ADR 写入或跨仓库查询能力。
- 不要提交 `.codebase-memory/`、`.ai-context/` 或未经人工审阅的自动架构结论。
- DeepWiki Open 保持禁用；不要克隆、安装、运行或生成 Wiki 缓存。

## Pull Request 检查清单

提交 PR 前请确认：

- [ ] 说明了用户可感知的变化。
- [ ] 提到了变更的 API、数据库模型或提示词文件。
- [ ] 已阅读目标路径对应的作用域规则；若规则所有权变化，已更新根路由并运行 `python3 scripts/verify-agents-guidance.py`。
- [ ] 后端相关改动已运行对应测试。
- [ ] 前端相关改动已运行测试或构建。
- [ ] 行为变化已更新 README 或 docs。
- [ ] 没有提交 `.env`、本地数据库、生成导出物或运行 artifacts。
- [ ] 打算纳入本次贡献的新文件都已进入 Git index，没有滥用 `--allow-untracked` 代替版本控制。
- [ ] 若修改了 AI 上下文工具，已运行 `./scripts/verify-ai-context.sh --static`；若涉及索引、打包、运行时、忽略规则或代理边界，也已运行 `--full` 并更新对应验收报告。
- [ ] 若改变了架构边界，已更新 Mermaid 图和对应 ADR。

## Commit 风格

建议使用简短前缀：

- `feat:` 新功能
- `fix:` 修复问题
- `docs:` 文档改动
- `test:` 测试改动
- `refactor:` 不改变行为的内部调整

## 提交 Issue

一个好的 issue 通常包含：

- 具体命令或 UI 路径；
- 预期结果；
- 实际结果；
- 后端或前端日志；
- 是否使用真实 LLM Provider，还是本地 fallback。
