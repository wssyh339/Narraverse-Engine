# 开源准备清单

本文档说明叙界推演引擎 / Narraverse Engine 开源发布时应该表达什么，以及为什么这样表达。

## README 必须回答的问题

README 的前几屏应该回答：

1. 这是什么项目？
2. 它面向谁？
3. 它和通用 AI 写作工具有什么不同？
4. 我能不能几分钟内在本地跑起来？
5. 支持哪些模型供应商？
6. 架构在哪里解释？
7. 如何参与贡献？

## 当前推荐定位

推荐定位：

> 本地优先的 LangGraph 多 Agent 长篇小说创作工作室，包含正典图谱、大纲 Swarm、人工审查和可导出写作流程。

竞争点不是“AI 能写 prose”，而是：

- 长篇小说状态工程；
- 正典优先生成；
- 人工确认式 AI 变更；
- Prompt Catalog 和模型供应商无关；
- 本地掌控手稿和 API Key。

## 开源文件清单

- [x] `README.md`
- [x] `LICENSE`
- [x] `CONTRIBUTING.md`
- [x] `CODE_OF_CONDUCT.md`
- [x] `SECURITY.md`
- [x] `CHANGELOG.md`
- [x] `docs/architecture.md`
- [x] `docs/prompt-catalog.md`
- [x] `docs/roadmap.md`
- [x] `.env.example`
- [x] `docker-compose.yml`
- [x] `.github/ISSUE_TEMPLATE/`
- [x] `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] demo 截图或短 GIF
- [x] `examples/` 示例项目输入

## README 内容策略

README 用来承载：

- 项目定位；
- 技术优势；
- 架构图；
- 快速启动；
- 模型供应商配置；
- 测试命令；
- 贡献入口。

内部信息放到 docs：

- 详细项目约束；
- 旧验收报告；
- 前端构建体积分析；
- Prompt Catalog 细节；
- 路线图和版本范围。

## 应强调的技术优势

1. 三条独立 Agent 线。
2. 正典优先工作流。
3. LangGraph 和 langgraph-swarm 编排。
4. 预览-确认-提交的安全模型。
5. OpenAI 兼容的供应商无关 LLM Client。
6. 用本地 SQLite 模拟图结构，避免重型外部图数据库依赖。
7. Prompt Catalog 作为扩展点。
8. CLI 和 Web UI 并存。

## 下一步开源打磨

1. 增加真实截图：
   - 创作 Star 世界观抽卡；
   - 大纲 Swarm active-agent 图；
   - 正文工作台和设定侧栏。
2. 增加更完整的示例项目输出。
3. 增加一个小型 no-key demo 脚本。
4. 增加 `make dev`、`make test` 或 `justfile`，简化命令。
