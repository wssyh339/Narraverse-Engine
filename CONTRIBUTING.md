# 贡献指南

感谢你愿意改进叙界推演引擎 / Narraverse Engine。

这是一个本地优先的 AI 长篇小说创作工作室。最有价值的贡献通常会提升可靠性、可追踪性、作者控制权或长篇结构能力。

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

## 适合贡献的方向

- **Agent 工作流**：保持 `creation_star`、`outline_swarm`、`chapter_writing` 三条线相互独立。
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

## Pull Request 检查清单

提交 PR 前请确认：

- [ ] 说明了用户可感知的变化。
- [ ] 提到了变更的 API、数据库模型或提示词文件。
- [ ] 后端相关改动已运行对应测试。
- [ ] 前端相关改动已运行测试或构建。
- [ ] 行为变化已更新 README 或 docs。
- [ ] 没有提交 `.env`、本地数据库、生成导出物或运行 artifacts。

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
