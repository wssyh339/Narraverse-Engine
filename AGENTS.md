# 叙界推演引擎 / Narraverse Engine 项目规范

> 本文档是本项目后续所有开发会话的最高优先级项目约束。任何新增功能、依赖、目录、接口、数据表或部署方式，必须先更新本文档并获得确认。

## 0. 1.0 正式版修订（2026-06-03）

本节覆盖旧 MVP 阶段中与 1.0 目标冲突的约束。旧文档中“暂不做 EPUB/PDF/全流程自动化/版本分支/完整时间线”等限制，仅适用于 MVP，不再限制 1.0 正式版。

### 0.1 1.0 产品边界

1.0 是本地优先的 AI 小说创作工作室，必须同时提供：

- FastAPI 后端服务。
- React + TypeScript Web 前端。
- Python CLI 入口。
- LangGraph 多 Agent 编排。
- SQLite 本地数据库。
- 动态设定集、角色卡、剧情实体、世界观事实与关系图谱。
- Agent 运行轨迹、版本快照、diff、回滚与分支。
- 批量生成、摘要、伏笔、风格学习、事实核查、导出。

### 0.2 锁定技术栈

| 层级 | 技术 | 锁定版本 |
|---|---:|---:|
| 后端 | Python | 3.10+，本机验证 3.13.13 |
| Web 框架 | FastAPI | 0.136.3 |
| Agent 编排 | langgraph | 1.2.4 |
| Swarm 编排 | langgraph-swarm | 0.1.0 |
| Deep Agent | deepagents | 0.6.10 |
| LangChain | langchain | 1.3.9 |
| LangChain Core | langchain-core | 1.4.7 |
| LangChain OpenAI | langchain-openai | 1.2.2 |
| LangSmith | langsmith | 0.8.15 |
| LLM SDK | openai | 2.40.0 |
| ORM | SQLAlchemy | 2.0.50 |
| 数据校验 | pydantic | 2.13.4 |
| 配置 | python-dotenv | 1.2.2 |
| Markdown 导出 | Markdown | 3.10.2 |
| 前端 | React | 18.3.1 |
| 前端语言 | TypeScript | 5.9.3 |
| UI 组件 | Ant Design | 5.27.6 |
| Chat UI | @assistant-ui/react | 0.14.14 |
| 路由 | react-router-dom | 6.30.2 |
| 状态管理 | Zustand | 5.0.8 |
| HTTP | Axios | 1.13.2 |
| Markdown 编辑器 | @uiw/react-md-editor | 4.0.8 |
| 图谱 | ECharts | 6.0.0 |

### 0.3 AI Provider

后端必须通过统一 LLM Client 支持：

- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=deepseek`
- `LLM_PROVIDER=qwen`
- `LLM_PROVIDER=openrouter`
- `LLM_PROVIDER=siliconflow`
- `LLM_PROVIDER=moonshot`
- `LLM_PROVIDER=zhipu`
- `LLM_PROVIDER=ollama`
- 通用 OpenAI 兼容 `LLM_BASE_URL` + `LLM_API_KEY`

Agent 配置中心允许为每个可视化工作流中的每个 Agent 保存显式模型覆盖。解析优先级为：请求体 `model` → `agent_model_configs` 中的 `workflow_id + agent_name` 覆盖 → Provider 专属默认模型 → `LLM_MODEL`。该能力只做人工显式配置，不做多模型自动路由优化。

API Key 只能来自环境变量。缺少 API Key 时，工作流允许本地降级生成可验证草案，但必须在配置和模型调用结果中标明未调用远程模型。真实 API 验收必须设置 `LLM_REQUIRE_REMOTE=true`，此时缺少 API Key 或远程调用失败不得本地降级。

### 0.4 11 个 Agent

1. 总策划 Agent：世界观、人物、三卷大纲和全局一致性。
2. 章节规划 Agent：章节标题、POV、事件、冲突、转折、钩子。
3. 情节叙事 Agent：章节主干、行动链、选择与代价。
4. 人物对话 Agent：自然对话、潜台词、人物语气。
5. 环境描写 Agent：氛围、感官细节、空间压力。
6. 审核修改 Agent：逻辑、人物、节奏、文笔问题。
7. 风格统一 Agent：按风格样本和 style_guide 润色。
8. 事实核查 Agent：历史、科学、技术、地理、文化与内部规则。
9. 整合输出 Agent：合并终稿并生成章节摘要。
10. 设定整理 Agent：更新角色卡、实体、世界观事实、图谱和连续性问题。
11. 创作 Star Agent：在正式写作前进行频道、类型、标签、世界观、主角人设、项目总设定表和世界观规则表的抽卡式立项；所有结果必须经用户确认后才写入正式设定集。

### 0.5 LangGraph 工作流

- 初始化项目：总策划 Agent → 设定整理 Agent。
- 旧独立章节规划工作流已删除；章纲只能由大纲议事流逐章确认后写入。章节规划 Agent 仅在单章正文链路中读取已确认章纲，生成章节卡和场景细纲输入。
- 单章正文：构建 `canon_context` → 情节叙事 Agent → 人物对话 Agent → 环境描写 Agent → 整合输出 Agent 生成 `integrated_draft` → 审核修改 Agent → 事实核查 Agent → `quality_gate` → 必要时进入修订回路 → 风格统一 Agent → 设定整理 Agent。
- 批量生成：按章节循环运行单章正文工作流，并保存版本快照与 Agent 轨迹。

所有创作 Agent 生成前必须读取 `canon_context`，其中至少包含 project、story_bible、核心角色、相关实体、world_facts、graph 子图、连续性问题和前文摘要。

质量门必须检查审核结果和事实核查报告；出现 `blocking/error` 时先修订，不得直接定稿。设定整理 Agent 输出的低置信度新增设定必须进入 `candidate_canon_updates`，由服务层保留来源、置信度和更新原因。

### 0.6 新增核心数据表

1. `characters`
2. `story_entities`
3. `world_facts`
4. `graph_nodes`
5. `graph_edges`
6. `generation_jobs`
7. `agent_runs`
8. `agent_messages`
9. `generation_outputs`
10. `continuity_issues`
11. `foreshadowing_items`
12. `style_profiles`
13. `prompt_templates`
14. `agent_model_configs`
15. `runtime_settings`
16. `deep_agent_sessions`
17. `deep_agent_tool_calls`
18. `langsmith_trace_links`
19. `version_snapshots`
20. `export_jobs`
21. `user_feedback`

MVP 阶段已有表继续保留；1.0 通过运行时 SQLite 轻量迁移补齐旧库缺失列。

### 0.7 新增 API

后端同时提供 `/api` 与 `/api/v1` 前缀。1.0 前端默认使用 `/api`。

核心路由：

- 项目：`POST/GET /api/projects`，`GET/PUT/DELETE /api/projects/{id}`，`POST /api/projects/{id}/duplicate`
- 状态：`GET/PUT /api/projects/{id}/state`
- Story Bible：`GET/PUT /api/projects/{id}/story-bible`，`POST /api/projects/{id}/story-bible/generate`
- 章节：`POST /api/projects/{id}/chapters`，`GET /api/projects/{id}/chapters`，`GET/PUT /api/projects/{id}/chapters/{chapter_id}`，`POST draft/rewrite/partial-rewrite`，`POST /api/projects/{id}/chapters/{chapter_id}/chat/stream`
- Agent：`GET /api/agents`，`GET /api/agents/{agent_name}`，`PUT /api/agents/{agent_name}/prompt`，`/api/agents/templates`
- LLM 模型：`GET /api/llm/models`，`GET/PUT /api/agent-model-configs`，`DELETE /api/agent-model-configs/{workflow_id}/{agent_name}`
- Deep Agent：`GET/PUT /api/deep-agent/config`，`POST/GET /api/projects/{id}/deep-agent/sessions`，`GET /api/projects/{id}/deep-agent/sessions/{session_id}`，`POST /api/projects/{id}/deep-agent/sessions/{session_id}/chat/stream`，`POST /api/projects/{id}/deep-agent/tool-calls/{tool_call_id}/approve`，`POST /api/projects/{id}/deep-agent/tool-calls/{tool_call_id}/reject`
- LangSmith：`GET /api/langsmith/status`，`GET /api/langsmith/runs/{job_id}`，`POST /api/langsmith/prompts/push`，`POST /api/langsmith/prompts/pull-preview`，`POST /api/langsmith/evals/run`
- 任务：`POST /api/write/generate`，`POST /api/write/batch-generate`，`POST pause/resume/cancel`，`GET /api/jobs`，`GET /api/jobs/{job_id}`，`GET /api/jobs/{job_id}/agent-runs`
- 版本：`GET /api/versions`，`POST /api/versions/compare`，`POST rollback/branch`
- 图谱/设定集：`GET/POST /api/projects/{id}/characters`，`GET/PUT/DELETE /api/projects/{id}/characters/{character_id}`，`GET/POST /api/projects/{id}/entities`，`PUT/DELETE /api/projects/{id}/entities/{entity_id}`，`GET/POST /api/projects/{id}/world-facts`，`PUT/DELETE /api/projects/{id}/world-facts/{fact_id}`，`GET /api/projects/{id}/graph`，`GET /api/projects/{id}/canon/context`
- Agent 辅助生成设定：`POST /api/projects/{id}/settings/generate`，支持 `target=characters/entities/world_facts/all`；前端默认传 `preview_only=true` 仅生成候选预览，不写入角色/实体/世界观事实和图谱，用户确认后再调用对应创建接口正式入库。
- 创作 Star：`GET /api/creation-star/options`，`POST /api/projects/{id}/creation-star/draw`，`POST /api/projects/{id}/creation-star/commit`
- 工作流结构：`GET /api/workflows`，返回初始化、大纲议事、单章正文、批量生成等当前可视化节点和边；不得再暴露旧独立章节规划工作流。
- 伏笔：`GET/POST /api/projects/{id}/foreshadowing`，`PUT/DELETE /api/projects/{id}/foreshadowing/{item_id}`，`POST /api/projects/{id}/foreshadowing/{item_id}/payoff`
- 工具：summary、foreshadowing、cliffhanger、fact-check、consistency-check、learn-style、query-knowledge
- 导出：`POST /api/export`，`GET/POST /api/export/templates`
- WebSocket：`/ws/progress`，`/ws/jobs/{job_id}`

`POST /api/tools/foreshadowing` 只返回 Agent 伏笔建议，不直接写入正式伏笔表；用户确认后必须调用伏笔创建接口。

伏笔记录必须包含 `planted_chapter_id`、`planned_payoff_chapter_id`、`actual_payoff_chapter_id`、`payoff_status`、`importance_level`、`importance_score`、`related_character_ids`、`related_entity_ids` 和 `source`。回收伏笔时必须将 `payoff_status` 置为 `paid_off` 并同步图谱关系。

### 0.8 仍然不做

1. 不做用户登录注册、权限、组织空间或云端多人协作。
2. 不做支付、订阅、额度、账单或商业授权系统。
3. 不做在线发布平台、自动投稿或平台账号托管。
4. 不默认引入 Neo4j 或复杂向量数据库；1.0 用关系型表模拟图结构。
5. 不做移动端原生 App、Electron 桌面端、浏览器插件。
6. 不做本地模型训练、微调平台或多模型自动路由优化。
7. 不允许前端直接读取或调用 LLM API Key。
8. 不允许无来源覆盖用户手动设定；AI 自动设定必须保留来源、置信度和更新原因。

### 0.9 专业创作工作室修订（2026-06-05）

前端必须从“多个彼此割裂的管理页面”升级为统一创作工作室。参考成熟小说编辑器的工作流，但不得复制第三方源码、视觉皮肤、品牌文案或会员能力。

统一工作室采用：

- 项目级顶部导航：作品、正文、设定、大纲、笔记。
- 正文工作区三栏布局：左侧卷章目录与创作资源，中间正文编辑器，右侧 AI 协作助手。
- 项目内页面共享当前项目、当前章节、当前卷和当前上下文，不得要求用户在功能间重复选择项目。
- 支持专注写作、亮暗主题、自动保存、字数统计、智能排版、高频词、查找替换和版本恢复。
- AI 编辑操作必须遵循“生成提案 → 展示差异 → 用户确认 → 应用前快照 → 写入正文”的流程；不得直接无确认覆盖用户正文。
- 章节 Chat 协作必须采用 `assistant-ui` 前端外壳 + 自建 FastAPI SSE/streaming 接口；选区修改流程为“选中文本 → 输入修改要求 → 流式生成建议 → 用户点击应用到选区 → 自动保存并保留快照”，不得在流式生成阶段直接写入正文。
- 设定更新必须遵循“候选变更 → 用户审批 → 写入设定集”的流程。
- 本地备份、恢复、导入和导出属于 1.0 范围；云同步、平台账号托管和自动发布仍属于非目标。
- 项目顶部导航第一个入口必须是“创作 Star”，位于“作品”左侧；正文工具栏不再重复放置该入口。
- 创作 Star 用于抽卡式立项。流程为：基本信息与标签选择 → 世界观抽卡 → 主角人设抽卡 → 项目总设定表/世界观规则表 → 创建书名 → 用户确认后写入作品信息和设定集。
- 项目首页的“创建新项目”必须进入创作 Star 流程：先创建本地草稿项目，再打开创作 Star 向导，最后由用户确认写入正式标题和设定。

新增本地工作室数据：

1. `volumes`：分卷名称、卷纲、顺序和状态。
2. `notes`：目录化写作笔记、灵感卡和可引用上下文。
3. `editor_proposals`：AI 编辑提案、原文、建议稿、diff、审批状态。
4. `chapters` 补充 `sort_order`、`deleted_at`、`is_locked`，用于排序、回收站和锁定。

新增核心 API：

- 分卷：`GET/POST /api/projects/{id}/volumes`，`PUT/DELETE /api/projects/{id}/volumes/{volume_id}`
- 目录：`POST /api/projects/{id}/chapters`，`POST /api/projects/{id}/chapters/reorder`，`GET /api/projects/{id}/chapters/trash`，`POST trash/restore`
- 笔记：`GET/POST /api/projects/{id}/notes`，`PUT/DELETE /api/projects/{id}/notes/{note_id}`
- 快照：`POST /api/projects/{id}/chapters/{chapter_id}/snapshot`
- AI 编辑提案：`POST /api/projects/{id}/chapters/{chapter_id}/proposals`，`GET /api/projects/{id}/proposals`，`POST apply/reject`
- 章节 Chat：`POST /api/projects/{id}/chapters/{chapter_id}/chat/stream`，返回 `text/event-stream` 事件 `meta`、`delta`、`result`、`done`
- 本地备份：`GET /api/projects/{id}/backup`

### 0.10 提示词库驱动 Agent 重构（2026-06-10）

用户已确认将粘贴的长篇小说生产提示词拆分为 `backend/app/prompts/00_*.md` 到 `31_*.md`，并作为 1.0 Agent 重构的正式提示词库。

2026-06-15 补充：创作 Star 世界观抽卡从总提示词中拆出为 `backend/app/prompts/32_creation_worldview_draw_prompt.md`，`prompt_id=creation_worldview_draw`。主角人设抽卡从总提示词中拆出为 `backend/app/prompts/33_creation_protagonist_draw_prompt.md`，`prompt_id=creation_protagonist_draw`。书名与包装抽卡从总提示词中拆出为 `backend/app/prompts/34_creation_title_packaging_prompt.md`，`prompt_id=creation_title_packaging`。这三个提示词只服务候选卡片生成，不属于新增正式 Agent 角色；世界观只生成 `conflict_engine_seed`（冲突发动机种子），主角只生成 `conflict_seed`（主角侧冲突种子），书名包装只生成可编辑的标题、广告句、核心卖点、读者期待、平台风格和风险提示，不得在抽卡阶段强行生成 `core_conflict_system` 或 `novel_constitution`。用户选定世界观、主角、书名包装并确认立项种子后，才由 `chief_architect` 进入核心矛盾系统与小说宪法流程。

重构原则：

- 提示词是可复用模板，Agent 是角色职责，Workflow 决定调用顺序；不得把 `00`-`31` 正式提示词库或 `32`/`33`/`34` 创作 Star 专用补充提示词机械扩展为独立正式 Agent。
- `creation_star` 不得默认绑定 `core_conflict_system` 与 `novel_constitution`；世界观抽卡必须单独调用 `creation_worldview_draw`，主角人设抽卡必须单独调用 `creation_protagonist_draw`，书名与包装抽卡必须单独调用 `creation_title_packaging`，并记录专用 Agent 运行名，便于 Agent 栏追踪实际应用。
- 保留 0.4 中的 11 个正式 Agent 作为对外稳定角色；新增“核心矛盾、小说宪法、章节卡、叙事账本、结构体检”等能力优先实现为 workflow node 或 prompt task。
- 后端必须提供统一 Prompt Catalog，记录 `prompt_id`、文件名、所属工作流、默认 Agent 和标题。
- `/api/workflows` 必须同时保留既有工作流结构，并新增“立项与小说宪法、全书与分卷规划、单章生产闭环、连载维护与体检、专项增强”五条提示词驱动工作流。
- 提示词驱动工作流中的 00-31 节点必须标记为 `node_subtype="prompt_agent"`，并为每个节点暴露独立输入 schema、输出 schema、必需输入和产物字段；这些节点不是 32 个新增正式 Agent。
- 所有创作 Agent 调用前仍必须读取 `canon_context`；单章生成至少使用小说宪法、当前卷/章纲、叙事账本、上一章摘要和相关正典上下文。
- 正文生成链路必须遵循“章节卡 → 场景细纲 → 正文 → 自检 → 改写 → 章后叙事账本更新”的闭环；质量门出现 `blocking/error` 时不得直接定稿。
- 叙事账本、伏笔、人物关系和世界规则更新默认进入候选变更，用户确认后才能写入正式设定集。

文档版本：2026-06-10

### 0.11 创作 Star 解耦流程修订（2026-06-11）

创作 Star 是唯一前台立项入口，但不得继续由单个大步骤混合承担抽卡、小说宪法和正式入库责任。1.0 正式流程拆为：

```text
基本信息
  -> 世界观逐卡加载
  -> 主角人设逐卡加载
  -> 书名与包装方向逐卡加载
  -> 立项种子确认
  -> 核心矛盾系统
  -> 小说宪法
  -> 小说宪法压力测试
  -> 正典候选预览
  -> 用户确认入库
```

职责边界：

- `creation_star` 只负责世界观、主角、书名与包装卖点的候选抽卡；所有输出在用户确认前均为候选。
- `chief_architect` 负责把已确认的立项种子收敛为 `core_conflict_system` 与 `novel_constitution`。
- `reviewer` 负责 `constitution_review`，状态必须为 `passed`、`passed_with_notes`、`needs_revision` 或 `blocked`。
- `canon_curator` 负责把立项种子、核心矛盾、小说宪法和压力测试映射为 `canon_candidates`，并在用户最终确认后写入正式设定集。

新增本地数据表：

1. `creation_sessions`：保存创作 Star 分步会话、基础信息、当前步骤、候选卡片、已选项、核心矛盾、小说宪法、压力测试、正典候选与最终提交状态。

新增核心 API：

- `POST /api/projects/{id}/creation/sessions`
- `GET /api/projects/{id}/creation/sessions/{session_id}`
- `POST /api/projects/{id}/creation/sessions/{session_id}/worldviews`
- `POST /api/projects/{id}/creation/sessions/{session_id}/protagonists`
- `POST /api/projects/{id}/creation/sessions/{session_id}/market-position`
- `POST /api/projects/{id}/creation/sessions/{session_id}/seed`
- `POST /api/projects/{id}/creation/sessions/{session_id}/core-conflict`
- `POST /api/projects/{id}/creation/sessions/{session_id}/constitution`
- `POST /api/projects/{id}/creation/sessions/{session_id}/constitution-review`
- `POST /api/projects/{id}/creation/sessions/{session_id}/canon-preview`
- `POST /api/projects/{id}/creation/sessions/{session_id}/commit`
- `POST /api/projects/{id}/creation/basic-suggestions`

会话式接口补充约束：

- 创作 Star 基本信息页 01 基本定位与 02 读者规模的预设选项必须集成在下拉栏中，不再以独立预设按钮占用表单下方空间。
- 创作 Star 基本信息页 03 初始想法与抽卡约束必须支持通过统一 LLM Client 生成可反复刷新的标签/灵感建议；这些建议只能作为候选应用到初始想法或额外约束输入，不得直接写入正式设定集。
- 逐卡加载接口默认 `count=1`，前端每次点击按顺序追加本轮新增卡片；当用户点击刷新时，前端只在本批第一张请求传 `replace_existing=true`，后端必须同步清空当前步骤候选与全部下游候选、已选项、立项种子、核心矛盾、小说宪法、压力测试和正典候选，避免前后端状态漂移。
- `canon-preview` 和 `commit` 必须执行小说宪法质量门：`constitution_review.status` 只能在 `passed` 或 `passed_with_notes` 时继续；`needs_revision` 或 `blocked` 不得预览正典或写入正式设定集。
- `commit` 请求必须支持 `approved_canon_sections`，新版前端提交时必须显式携带 `project`、`story_bible`、`characters`、`entities`、`world_facts`、`graph` 六个审批项；后端对缺失审批项返回校验错误。旧客户端未传该字段时暂按全量审批兼容。

旧版 `POST /api/projects/{id}/creation-star/draw` 与 `POST /api/projects/{id}/creation-star/commit` 暂时保留兼容，但新版前端默认走 `creation/sessions` 分步接口。

### 0.12 大纲议事拓扑记录修订（2026-06-21）

大纲工作室的大纲生成入口统一收敛为“回合制实时议事”。旧大纲生成接口、旧生成弹窗和旧推演图组件已删除，不得重新挂载。

接口约束：

- `POST /api/projects/{id}/outline/debate/sessions` 创建议事会话。
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/{phase}/run` 与同路径 `stream` 运行 `book`、`volumes`、`chapters` 阶段。
- 议事运行请求继续支持 `use_topology_inference: boolean`，但该开关只影响 `phase_run.outline_topology` 的解释组织方式，不再切换到旧生成流程。
- 每个 `phase_run` 必须保存 `turns`、`decisions`、`artifacts`、`outline_topology` 和结构化 `result`。
- `outline_topology` 至少包含 `mode`、`nodes`、`edges`、`events`、`artifacts` 和 `metrics`，用于解释 Agent 交接、候选产物、审查、阻塞、确认和正典写入来源。

前端约束：

- 大纲页不得再提供旧“生成大纲/批量生成章纲”弹窗入口。
- 前端只能通过 `OutlineDebatePanel` 展示议事流、逐字流式输出、用户加入讨论、`@` 指定角色、打断和确认。
- 拓扑信息作为议事流的结构化证据展示，不得恢复旧推演图组件或旧前端推演步骤回退链。

### 0.13 结构拆分与三线架构合并约束（2026-06-14）

本节合并旧规范文档中仍然有效的结构约束。若本节与 0.10、0.11、0.12 的新版流程冲突，以更新日期更晚的 0.10-0.12 为准；本节主要约束兼容入口、文件归属和防止功能继续堆叠。

后端 API 路由按领域放在 `backend/app/api/v1/endpoints/`：

- `backend/app/api/v1/endpoints/project_studio.py`：项目、状态、故事圣经、章节读写和项目工作室入口。
- `backend/app/api/v1/endpoints/agents.py`：Agent、创作 Star、提示词模板和工作流图。
- `backend/app/api/v1/endpoints/knowledge.py`：角色、实体、世界观事实和图谱。
- `backend/app/api/v1/endpoints/foreshadowing.py`：伏笔预埋、编辑、删除和回收。
- `backend/app/api/v1/endpoints/writing.py`：写作任务、批量任务、暂停恢复取消和 Agent 轨迹。
- `backend/app/api/v1/endpoints/versions.py`：版本列表、diff、回滚和分支。
- `backend/app/api/v1/endpoints/canon.py`：canon context 与正典刷新入口。
- `backend/app/api/v1/endpoints/tools.py`：摘要、事实核查、一致性检查、风格学习和知识查询。
- `backend/app/api/v1/endpoints/exporting.py`：导出和导出模板。
- `backend/app/api/v1/endpoints/websockets.py`：WebSocket 进度和任务连接。

`backend/app/api/v1/router.py` 只负责挂载路由，不写业务分支。`backend/app/api/v1/endpoints/studio.py` 仅作为 legacy compatibility facade 保留；新增 API 不得继续添加到该文件。

前端大纲工作台必须保持薄页面编排：

- `frontend/src/pages/OutlineStudioPage.tsx` 只负责 URL 参数、React Query、选择状态、mutation 编排和子组件组合。
- `frontend/src/pages/outline/OutlineDirectory.tsx` 负责大纲目录、卷章层级、删除和批量删除。
- `frontend/src/pages/outline/OutlineEditorPanel.tsx` 负责总纲、卷纲、章节、章纲编辑区。
- `frontend/src/pages/outline/OutlineDebatePanel.tsx` 负责实时议事流、用户加入讨论、`@` 角色插话、打断、逐字输出、分阶段运行与确认。
- `frontend/src/pages/outline/scalePlan.ts` 负责从项目规模字段构建可传入议事流的 Scale Planner 参数。
- 旧正典辅助面板已删除，不得重新堆回 `OutlineStudioPage.tsx` 或作为大纲生成入口。

结构拆分原则：功能入口增加时优先新增小组件或领域 endpoint；只有共享状态和跨组件编排可以留在页面级文件。若单文件超过约 450 行，继续开发前必须先评估拆分。

`backend/app/agents` 与服务层必须按三条独立产品线组织：

- `backend/app/agents/creation_star/`：抽卡式立项，只生成候选设定，用户确认后写入正式项目；抽卡与提交编排由 `creation_star/service.py` 承担。
- `outline_debate`：大纲生成与世界构建统一走 `backend/app/services/outline_debate_service.py` 与 `backend/app/api/v1/endpoints/outline_debate.py`；旧 `backend/app/agents/outline_swarm/` 已删除，不得恢复。
- `backend/app/agents/chapter_writing/`：章节正文生成，使用稳定 LangGraph StateGraph 和质量门修订循环；真实 `AgentWorkflow` 必须归属本目录。

共享能力放入 `backend/app/agents/shared/`，包括 canon context、trace、prompt loader 和 lane contract。`backend/app/agents/workflow.py` 仅作为 `chapter_writing.workflow` 的旧导入兼容转发；旧 `outline_workflow.py`、`outline_models.py`、`outline_storage.py` 与 `outline_agents.py` 已删除，不得恢复。

大纲生成线必须消除示例故事硬编码。世界观、势力、物品、地点、秘密、角色和规则必须来自用户输入、项目正典、数据库上下文或 LLM 结构化输出，不得在代码中写死类似“龙骨能源”“最后真龙封印”“帝国能源署”等样例内容。

项目内大纲工作台必须走议事接口：先创建 `outline_debate session`，再按 `book`、逐卷 `volumes`、逐章 `chapters` 阶段运行、确认和写入。旧两段式大纲生成、章纲批量生成接口和 `POST /api/projects/{id}/chapters/plan` 均已删除，不得恢复。

卷纲生成不得固定套用 5 Phase 或 50 章模板。每卷必须先选择 `rhythm_model`，可在三幕推进、五段升级、单元案串联、多线群像、战役推进、地图探索、规则试炼、权谋拉扯、情感递进、真相逐层揭示等模型中动态选择，并说明 `why_this_model`、`phase_count` 和 `chapter_distribution`。五段升级只是可选模型之一。

### 0.14 旧 13-Agent 大纲流程删除边界（2026-06-22）

旧规范文档中的 13-Agent 长篇大纲推演不再作为兼容能力保留。旧 CLI 本地 `StoryState` 大纲流程、旧 `/chapters/plan` API、旧 `outline_generation` workflow、旧 `outline_swarm` 包、旧 `PlanChaptersRequest` schema、旧独立 `run_chapter_plan` 工作流和旧大纲模块文件已删除。正式大纲生成只能通过 `outline_debate` 议事流完成。

正典完整性规则仍然有效：

- 多问为什么：关键设定、行动、冲突、危机、高潮必须说明为什么现在发生、为什么必须由此人经历、为什么不能逃避、为什么会增加代价、为什么读者在意、为什么推动主线、为什么不破坏已有设定。
- 不确定不硬编：无法确认的设定、规则、动机、因果或时间线必须创建不确定项或待确认候选。
- 重要实体必须补全：新增角色、事件、物品、势力、地点、规则、秘密、资源、制度等实体必须判断是否入正典库。
- S/A 级实体未补全，不允许进入正式大纲；若只能降级生成，必须在输出中标明缺失字段和风险。
- 剧情节点必须带戏剧功能：说明改变了什么、增加了什么压力、制造了什么新问题、如何逼近危机和高潮。

### 0.15 Deep Agent 与 LangSmith 管理修订（2026-06-14）

Deep Agent 是工作室总管层，不替代 0.4 的 11 个正式 Agent，也不得绕过 0.5 的质量门和人工确认流程。Deep Agent 只负责理解用户长期目标、拆解任务、调用现有工作流工具、生成建议、创建待审批工具调用和候选变更。

权限边界：

- 默认 `DEEP_AGENT_ENABLED=false`，此时仅运行本地 advisory 模式，不调用 deepagents 远程或长程执行 harness。
- `DEEP_AGENT_ALLOW_WRITE=false` 时，所有工具调用必须进入 `deep_agent_tool_calls.status=pending_approval`，用户审批前不得写入正文、设定集、章节、伏笔或版本。
- 即使 `DEEP_AGENT_ALLOW_WRITE=true`，AI 编辑和设定更新仍必须遵循“提案/候选 → 用户确认 → 快照 → 写入”的既有流程。
- Deep Agent 工具白名单限定为读取项目上下文、读取 canon context、列章节、启动既有工作流、创建编辑提案、创建候选正典、创建版本快照和查询任务状态；不得开放任意 SQL、文件系统写入、shell 执行或前端直连 API Key。

LangSmith 是可选观测与 Prompt/Eval 管理层：

- 默认 `LANGSMITH_TRACING=false`，未配置 `LANGSMITH_API_KEY` 时不得尝试远程写入。
- 隐私模式必须支持 `off`、`metadata_only`、`redacted`、`full`，默认 `metadata_only`；`metadata_only` 不得上传小说正文、提示词全文、用户私密设定或章节草稿。
- 本地 `generation_jobs` 与 `agent_runs` 可保存 `langsmith_run_id`、`langsmith_url`、`trace_mode`，但不得把 LangSmith 作为唯一运行轨迹来源。
- Prompt 管理以本地 `backend/app/prompts` 与 `prompt_templates` 为主，LangSmith Prompt Hub 只做手动 push/pull-preview；pull 结果必须预览并由用户确认后才能覆盖本地提示词。
- Eval 先提供本地评测报告，包含 schema 合法性、提示词占位符残留、工作流状态和用户评分占位；远程 LangSmith dataset 写入只在用户配置并显式触发时进行。

新增 Deep Agent 子代理职责：

1. `deep_story_director`：总管，决定下一步调用哪条既有工作流。
2. `continuity_investigator`：连续性审计，只输出问题和证据。
3. `structure_doctor`：大纲/十章/单卷结构体检。
4. `prompt_engineer`：提示词修改建议，只生成待确认方案。
5. `canon_curator_advisor`：把发现转为候选正典，不直接入库。

前端 Agent 配置中心必须展示：

- Deep Agent 当前模式、是否允许写入、会话列表、待审批工具调用。
- LangSmith 配置状态、隐私模式、Prompt 同步策略和 job trace 链接。
- 任意会上传正文或完整提示词的操作必须显示隐私模式，并且只能由后端执行。

文档版本：2026-06-14
- 严格区分危机、高潮、结果：危机是不可逆选择，高潮是执行选择，结果是承担后果。
- 每次 Agent 输出后必须经过实体抽取、正典候选、正典合并和连续性检查；不得直接覆盖已完成正典。

旧本地 JSON 正典导出不再作为前台或公开 API 大纲生成路径。新版持久化应优先写入 SQLite 表、正典文件树、版本快照、Agent 轨迹和候选正典审批流。

文档版本：2026-06-14

### 0.16 统一正典文件树完整闭环修订（2026-06-14）

设定工作台必须从“只读聚合页面”升级为可维护的统一正典文件系统，包含：

- 自定义文件夹创建、节点移动、排序和归档；前端支持拖拽移动，后端持久化到 `canon_nodes.parent_id`、`sort_order` 和 `metadata_json`。
- 字段锁定：每个正式设定要素可锁定字段列表，存储在 `canon_nodes.metadata_json.locked_fields`；非人工显式审批的 Agent 写入不得覆盖锁定字段，只能创建候选变更。
- 影响范围分析：任何角色、实体、世界事实或伏笔都能查询关联章节、版本、候选、图谱关系、伏笔和引用设定。
- 重复项队列：后端可扫描同名/近似名/同类型重复项，生成 `operation=merge` 的 `canon_change_proposals`；用户审批后合并目标项、归档来源项，并分别创建版本记录。
- 候选变更审批支持 `create/update/archive/merge`；审批通过时必须记录版本、同步 `canon_nodes` 与图谱，驳回时保留审计记录。
- 正典包导出：按文件树导出 JSON 和 Markdown，内容必须包含作品资料、故事圣经、角色、实体、世界事实、伏笔、关系图谱、版本索引、候选审计与健康度。

新增或补充 API：

- `POST /api/projects/{id}/settings/folders`
- `PATCH /api/projects/{id}/settings/nodes/{node_id}/move`
- `PUT /api/projects/{id}/settings/{ref_type}/{ref_id}/locks`
- `GET /api/projects/{id}/settings/{ref_type}/{ref_id}/impact`
- `POST /api/projects/{id}/settings/duplicates/scan`
- `POST /api/projects/{id}/settings/proposals/{proposal_id}/approve` 支持 create/update/archive/merge
- `GET /api/projects/{id}/settings/export?format=json|markdown`

文档版本：2026-06-14

### 0.17 启动配置收口修订（2026-06-15）

本地开发和 Docker Compose 必须以项目根目录 `.env` 作为启动配置的单一来源。新增或修改启动参数时，必须同时更新 `.env.example`、README 和本节环境变量清单。

- 本地后端官方启动入口为 `scripts/dev-backend.sh`，脚本读取 `.env` 后按 `BACKEND_HOST`、`BACKEND_PORT` 启动 `uvicorn --app-dir backend app.main:app`。
- 本地前端官方启动入口为 `scripts/dev-frontend.sh`，脚本读取 `.env` 后启动 `pnpm dev`，前端 Vite 配置必须从根目录 `.env` 读取 `FRONTEND_HOST`、`FRONTEND_PORT` 和 `VITE_API_BASE_URL`。
- 默认本地 SQLite 路径统一为 `DATABASE_URL=sqlite:///./data/novel_agent.db`；`backend/data/` 仅保留历史测试库和手动指定路径，不再作为 README 默认启动路径。
- 默认任务产物目录统一为 `JOB_ARTIFACT_DIR=artifacts/runs`。
- 前端默认 API 地址统一为 `VITE_API_BASE_URL=http://localhost:8000/api`；不得在文档或脚本中重新默认到 `/api/v1`。
- Docker Compose 可以映射宿主机端口，但不得无条件覆盖 `.env` 中的 `DATABASE_URL`、`JOB_ARTIFACT_DIR`、`FRONTEND_ORIGIN` 或 `VITE_API_BASE_URL`。
- `VITE_*` 变量属于前端构建期配置；Docker 模式下修改后必须重新 build。

文档版本：2026-06-15

### 0.18 大纲线角色与设定候选生成修订（2026-06-15）

大纲线允许在总纲、卷纲或章纲推演发现缺口时调用候选补全 Agent，但该能力只属于大纲线，不作为设定工作台、正文生成或创作 Star 的全局入口。

- `CharacterGeneratorAgent` 生成大纲所需候选角色档案卡，必须标记 `activity_status=candidate`、`first_needed_in`、`story_function`、`relationship_hooks`、`duplicate_check` 与 `canon_write_suggestion.requires_user_approval=true`；这里的审批点等同于用户确认对应总纲、卷纲或章纲候选。
- `SettingGeneratorAgent` 生成大纲所需候选设定档案，覆盖世界规则、组织、地点、物件、事件、制度、资源或禁忌，必须标记 `activity_status=candidate`、`first_needed_in`、`conflict_utility`、`foreshadowing_utility`、`continuity_check` 与 `canon_write_suggestion.requires_user_approval=true`；这里的审批点等同于用户确认对应总纲、卷纲或章纲候选。
- 两个 Agent 不得在讨论发言阶段自行写入 `characters`、`story_entities`、`world_facts`、`graph_nodes` 或 `graph_edges`；用户确认对应大纲候选后，服务层必须把未冲突的角色/设定候选物化为正式角色、实体或世界事实，并同步正典文件树与版本审计。
- 大纲主持链必须优先判断是否复用已有角色/设定；只有现有正典无法承担剧情功能时才生成新候选。
- `outline_topology` 必须保留 `character_candidate` 与 `setting_candidate` 事件，前端可展示其来源 Agent、首次需要位置、重要度、冲突用途、确认审批范围和物化结果。

文档版本：2026-06-17

### 0.19 大纲议事引擎修订（2026-06-15）

大纲线只保留“议事引擎”作为交互式编排方式，用于把大纲生成拆成三个互相独立、可重跑、可追踪的讨论阶段：

1. 讨论总纲：围绕全书核心承诺、终局方向、主线压力、读者体验和长期伏笔形成总纲候选。
2. 讨论卷纲：围绕分卷功能、节奏模型、阶段目标、卷末钩子和卷间因果形成卷纲候选。
3. 讨论章纲：围绕章节范围、场景推进、危机/高潮/结果区分、章末钩子和连续性风险形成章纲候选。

议事引擎约束：

- 后端必须提供会话式接口，保存每个阶段的 `turns`、`decisions`、`artifacts`、`outline_topology` 和最终候选结果；阶段之间可以读取上游结果，但必须允许独立运行和刷新。
- 前端必须展示实时 Agent 讨论流，不得用纯前端假动画替代后端事件；流式事件至少包含 `meta`、`turn`、`decision`、`artifact`、`done`。
- 议事中的角色生成与设定生成仅限大纲线，输出为 `character_candidate` 与 `setting_candidate` artifact，并标记 `status=candidate`、`source=outline_debate`、`requires_user_approval=true`；讨论生成阶段不得直接写库，用户确认对应总纲、卷纲或章纲候选后必须由服务层同步物化。
- 议事结果确认写入仍复用既有两段式“生成候选 → 用户确认 → commit 写入”边界；对角色/设定候选而言，确认总纲/本卷/本章即为审批点，但服务层仍必须执行重复项扫描、设定锁定保护、来源记录和正典版本审计。
- `/api/workflows` 和 Agent 轨迹只能暴露 `outline_debate` 大纲议事线；旧 `outline_swarm` 动态推演线已删除，不得继续展示或调用。

文档版本：2026-06-17

### 0.20 回合制实时议事体验修订（2026-06-16）

大纲议事引擎必须从“一次性生成后回放”升级为回合制实时议事。该能力属于 `outline_debate`，并替代旧 `outline_swarm` 和旧两段式大纲生成入口，但不得绕过正典审批边界。

交互约束：

- 前端必须提供“加入讨论”开关。关闭时按当前阶段自动连续推演；开启时每个 Agent 发言后进入暂停状态，等待用户继续、发表意见、打断或形成阶段结论。
- 用户意见必须作为会话消息保存，可通过 `@` 指定讨论角色；被指定角色应在下一轮优先回应，除非该角色不属于当前议事角色白名单。
- “打断发言”必须终止当前流式请求并把会话/阶段标记为 interrupted 或 paused，不得继续生成阶段产物。
- “发表意见”只影响后续议事上下文，不直接改写 Story Bible、Volumes、Chapters、角色、实体、世界事实或图谱。
- “形成阶段结论”必须由主持链根据已有 turns、用户意见和阶段目标生成 `decisions`、候选产物与 `outline_topology`，仍需用户确认后才能 commit 写入。

后端接口补充：

- 现有 `POST /api/projects/{id}/outline/debate/sessions/{session_id}/{phase}/stream` 在 `join_discussion=true` 时必须按单轮推进并返回 `pause` 事件；`join_discussion=false` 保持自动连续完成阶段。
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/messages` 保存用户意见、`target_agent_name` 和解析后的 mentions。
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/interrupt` 标记会话中断，并返回最新 session。
- 流式事件至少包含 `meta`、`turn`、`pause`、`user_message`、`interrupt`、`decision`、`artifact`、`done`、`error`。`pause` 事件必须携带最新 session、phase 和 next_agent 候选。

实现边界：

- 第一版采用 SSE + 控制 POST，不引入 WebSocket 新协议；如未来支持多人同时在线，再新增 WebSocket 议事通道。
- 会话状态优先保存在现有 `generation_jobs.result_json` 中，不新增表；若后续需要跨设备长期检索，再评估独立 `outline_debate_sessions` 表。
- 前端可复用 `assistant-ui`、Ant Design `Mentions` 和现有 SSE 读取器；不得恢复旧大纲生成图组件或引入新的聊天 UI 重依赖。

文档版本：2026-06-16

### 0.21 分层大纲议事候选确认修订（2026-06-16）

大纲议事生产线必须把总纲、卷纲、章纲拆成三个可独立展示、可重跑的候选阶段；其中总纲仍为阶段级确认，卷纲与章纲必须进一步拆成逐卷、逐章确认。议事讨论阶段仍只产出候选；用户确认某一卷或某一章后，服务层可以立即写入对应正式 `volumes` / `chapters` 记录，并同步 `canon_nodes` 与 `canon_versions`，形成“单项确认 → 单项正典更新”的闭环。

阶段门禁：

- `book` 阶段产出 `book_outline_candidate`，状态初始为 `pending_confirmation`。
- 用户确认 `book_outline_candidate` 后，`volumes` 阶段才允许生成。
- `volumes` 阶段每次只讨论一个目标卷，运行请求必须支持 `target_volume_no`，产出该卷的 `volume_outline_candidates` 条目，条目状态初始为 `pending_confirmation`。
- 用户确认某个 `volume:{volume_no}` 后，必须写入或更新对应 Volume，并把该 Volume 同步为正典文件树节点与正典版本；已确认的该卷才允许进入对应章纲讨论。
- `chapters` 阶段每次只讨论一个目标章，运行请求必须支持 `target_volume_no` 与 `target_chapter_no`，产出该章的 `chapter_outline_candidates` 条目，条目状态初始为 `pending_confirmation`。
- 用户确认某个 `chapter:{chapter_no}` 后，必须写入或更新对应 Chapter，并把该 Chapter 同步为正典文件树节点与正典版本。
- 重跑或刷新 `book` 阶段时，已存在的 `volumes` 与 `chapters` 候选必须标记为 `stale`。
- 重跑或刷新某个 `volume:{volume_no}` 时，只能移除该卷的已确认候选；相关 `chapters` 候选必须标记为 `stale`。
- 重跑或刷新某个 `chapter:{chapter_no}` 时，只能移除该章的已确认候选，不得冲掉其他已确认章。

新增确认与提交桥接接口：

- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/book/confirm`
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/volumes/confirm`
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/chapters/confirm`
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/commit`

确认接口必须支持可选 `item_key`。`book/confirm` 标记总纲候选为已确认，并把本阶段未冲突的角色/设定候选物化入正式正典；`volumes/confirm` 与 `chapters/confirm` 必须确认单个 `item_key`，将结构化结果写入议事 session 的 `confirmed_candidates`，立即写入对应正式 Volume/Chapter 与正典版本，并把本阶段未物化的角色/设定候选同步入库。重复确认不得重复创建同名正式记录。

提交接口用于最终整理已确认候选，必须同时满足总纲、所有已生成卷纲条目、所有已生成章纲条目均已确认。提交时只能从 `book_outline_candidate`、已确认 `volume_outline_candidates` 和已确认 `chapter_outline_candidates` 直接写入 Story Bible、Volumes、Chapters 与正典引用；角色候选、设定候选和世界观正典变更应已在各确认点物化，提交不得重复创建。

议事运行请求允许 `local_preview=true`，用于前端快速本地推演和浏览器闭环验证。该模式必须返回与远程模型一致的事件、候选包和确认/提交流程，但每个 Agent turn 的 `_llm.source` 必须标记为 `local_fallback`，不得伪装为远程模型调用。

文档版本：2026-06-16

### 0.22 创作 Star Scale Planner 修订（2026-06-17）

创作 Star 第一页“02 读者与规模”必须加入 Scale Planner，作为长篇规模的唯一前台输入源。

- 前端必须提供 `volume_count`、`chapter_count`、`chapter_word_min`、`chapter_word_max` 四个可编辑输入。
- `target_words` 不允许手动填写，必须由 `chapter_count * chapter_word_target` 自动计算；`chapter_word_target` 默认取 `chapter_word_min` 与 `chapter_word_max` 的中位数。
- `chapters_per_volume` 必须由 `ceil(chapter_count / volume_count)` 自动计算，允许作为结构化参数传递，但不得要求用户在创作 Star 第一页手动填写。
- 创作 Star 会话的 `basic_info` 必须保存 `scale_plan`，至少包含 `target_words`、`volume_count`、`chapter_count`、`chapters_per_volume`、`chapter_word_target`、`chapter_word_min`、`chapter_word_max`。
- 用户确认创作 Star 入库时，项目表必须同步保存 `planned_volume_count`、`planned_chapter_count`、`chapters_per_volume`、`chapter_word_target`、`chapter_word_min`、`chapter_word_max` 与 `target_words`，旧 SQLite 库通过运行时迁移补齐新增列。
- 大纲议事不得再用当前目录已有卷数或当前卷已有章节数推断长篇规模；必须优先读取项目 Scale Planner，并在运行请求中显式传入 `scale_plan`、`target_words`、`volume_count`、`chapters_per_volume`、`chapter_word_target`、`chapter_word_min` 和 `chapter_word_max`。
- 议事 Agent 的 turn context 必须包含 `scale_plan`，用于约束总纲、卷纲和章纲的节奏密度、卷章分配和单章字数范围。

文档版本：2026-06-17

### 0.23 批量正文异步队列修订（2026-06-17）

批量正文生成必须服务 100 万字级长篇，不得继续作为单个同步 HTTP 请求执行。

- `POST /api/write/batch-generate` 必须立即创建并返回 `job_type=batch_generate` 的 parent job，状态为 `queued` 或 `running`，前端通过 `/api/jobs/{job_id}` 轮询或后续 SSE/WebSocket 查询进度。
- 批量正文生成只能读取已存在且未归档的正式章节；缺少章节时必须返回校验错误，提示用户先确认章纲/创建章节，不得自动创建“批量生成占位章节规划”或绕过章纲确认。
- `GET /api/jobs` 必须支持按 `project_id`、`job_type` 和 `limit` 查询最近任务，用于批量页恢复不是当前页面创建的长任务。
- parent job 的 `progress_json` 必须记录总章数、已完成章数、当前章节、当前状态消息；当正在执行单章正文子流程时，还必须记录 `child_job_id`、`child_current_step`、`child_total_steps` 和 `child_completed_steps`。`result_json` 必须记录已完成章节、失败章节、请求范围和可恢复信息。
- 后台执行必须逐章运行单章正文工作流；每章使用独立数据库会话和事务提交，成功一章提交一章，失败时保留已完成结果并允许针对失败/未完成部分重试。
- 暂停、恢复、取消只允许在章节边界生效；恢复或重试时必须重新入队 parent job，并跳过已成功完成的章节。
- 前端批量页必须基于项目真实章节范围生成默认值，不得默认固定 1-3 章；没有可生成章节时必须禁用入口并引导用户先确认章纲。
- 前端必须展示可恢复任务状态、进度、当前章节、失败原因、已完成章节列表，以及暂停、恢复、取消、重试控制。

文档版本：2026-06-17

### 0.24 旧兼容死代码清理修订（2026-06-17）

旧 MVP 目录树中未挂载、未实现或已被新版领域路由替代的兼容 stub 不再保留。当前已删除：

- `backend/app/api/v1/endpoints/chapters.py`：未挂载旧章节规划 endpoint；正式大纲入口统一走 `outline/debate/sessions/*` 议事流。
- `backend/app/api/v1/endpoints/jobs.py`：未挂载旧任务 endpoint；正式入口统一走 `writing.get_job` 与 `writing.get_agent_runs`。
- `backend/app/api/v1/endpoints/memory.py`：未挂载且仅返回 404 的旧记忆概览 stub。
- `backend/app/api/v1/endpoints/runtime.py`：未挂载且仅返回 404 的旧章节追踪 stub。
- `backend/app/services/chapter_service.py`：仅供已删除旧 endpoint 使用的早期章节规划服务。
- `backend/app/services/generation_service.py`：仅供已删除旧 endpoint 使用的早期任务读取服务。
- `backend/app/services/memory_service.py` 与 `backend/app/services/state_service.py`：未实现且无人引用的旧 MVP 空服务。
- `backend/app/schemas/memory.py` 与 `backend/app/schemas/runtime.py`：仅供已删除旧 stub 使用的空查询模型。
- `frontend/src/api/memory.ts` 与 `frontend/src/api/runtime.ts`：未实现且无人引用的空前端 API 模块。

仍需保留的兼容边界：

- `/api` 与 `/api/v1` 双前缀仍属于 1.0 API 合约，不得删除。
- `/api/creation-star/*` 仍作为旧创作 Star 客户端兼容入口保留，新版前端默认走 `creation/sessions`。
- 旧正典辅助公开路由和前端入口已删除；正式持久化优先写入 SQLite、正典文件树和版本审计。
- `backend/app/api/v1/endpoints/studio.py` 仍仅作为 legacy compatibility facade，不得继续新增业务分支。
- `backend/app/agents/workflow.py` 仍按 0.13 作为章节正文 workflow 旧导入兼容转发；旧大纲 workflow 文件不得恢复。

文档版本：2026-06-17

## 1. 项目概述

项目名称：叙界推演引擎 / Narraverse Engine

当前版本：0.2.0

一句话描述：一个面向长篇小说创作者的本地优先 AI 写作工作台，用结构化故事状态、大纲议事、记忆检索和人工审稿来辅助持续创作。

目标用户：

- 网络小说作者
- 长篇类型小说作者
- 需要维护世界观、人物关系、章节连续性的 AI 辅助写作者

核心功能：

1. 项目与故事圣经管理：维护题材、受众、世界观、主线冲突、叙事视角、风格约束和禁用元素。
2. 章纲确认与正文生成：基于故事圣经、人物设定、已确认章纲、已有章节和用户指令生成正文草稿。
3. 记忆检索与生成审计：把故事设定、角色、章节摘要和用户笔记写入记忆库，并记录每次 AI 生成任务、模型调用和结果状态。

## 2. 技术栈表

| 层级 | 技术 | 锁定版本 | 说明 |
|---|---:|---:|---|
| 前端运行时 | Node.js | 24.14.0 | 本机已验证版本 |
| 前端包管理器 | pnpm | 11.5.1 | 统一使用 pnpm，不使用 npm/yarn |
| 前端框架 | React | 19.2.7 | 单页应用 |
| 前端构建工具 | Vite | 7.2.7 | 本地开发与构建；使用 Rollup WASM 覆盖规避 macOS native binding 签名限制 |
| 前端语言 | TypeScript | 6.0.3 | 严格类型检查 |
| React 插件 | @vitejs/plugin-react | 5.1.2 | Vite React 插件 |
| 前端请求状态 | @tanstack/react-query | 5.100.14 | API 请求、缓存、轮询 job 状态 |
| 前端校验 | zod | 4.4.3 | 表单与接口数据校验 |
| 前端图标 | lucide-react | 1.17.0 | 统一图标库 |
| 前端 Chat UI | @assistant-ui/react | 0.14.14 | 章节局部修改 Chat 外壳与组合 primitives |
| 后端运行时 | Python | 3.13.13 | 本机已验证版本 |
| 后端框架 | FastAPI | 0.136.3 | REST API 与 OpenAPI 文档 |
| ASGI Server | uvicorn | 0.48.0 | 本地开发服务 |
| 数据校验 | pydantic | 2.13.4 | 请求体、响应体、配置模型 |
| ORM | SQLAlchemy | 2.0.50 | SQLite 数据访问 |
| 迁移工具 | Alembic | 1.18.4 | 数据库迁移 |
| HTTP 客户端 | httpx | 0.28.1 | 调用 OpenAI 兼容 API |
| LLM SDK | openai | 2.40.0 | 使用 OpenAI 兼容协议接入通义千问与 DeepSeek |
| Agent 编排 | langgraph | 1.2.4 | 章节生成、审稿、重试和状态流 |
| Swarm 编排 | langgraph-swarm | 0.1.0 | 依赖版本锁定保留；旧 `outline_swarm` 大纲线已删除，当前大纲生成只走 `outline_debate` 议事引擎 |
| Agent 基础框架 | langchain | 1.3.9 | deepagents 与 langgraph-swarm 运行依赖 |
| Agent 基础库 | langchain-core | 1.4.7 | 消息、工具、提示模板基础类型 |
| 配置加载 | python-dotenv | 1.2.2 | 本地 `.env` |
| 关系数据库 | SQLite | 3.51.2 | MVP 阶段唯一关系数据库 |
| 向量数据库 | Qdrant | v1.18.1 | 记忆检索 |
| Python 向量库客户端 | qdrant-client | 1.18.0 | 后端访问 Qdrant |
| AI/LLM 默认 Provider | 通义千问 OpenAI 兼容 API | qwen-plus | 默认文本生成模型；模型快照如需固定，必须先更新本文档 |
| AI/LLM 备选 Provider | DeepSeek OpenAI 兼容 API | deepseek-v4-flash / deepseek-v4-pro | 可通过环境变量切换，不替代默认 Provider |
| Embedding | 通义千问 Embedding | text-embedding-v4 | 默认向量化模型 |
| 部署 | Docker Compose | 2.40.3 | 本地与 MVP 演示部署 |

## 3. 目录结构

```text
.
├── AGENTS.md
├── README.md
├── .env.example
├── docker-compose.yml
├── scripts
│   ├── dev-backend.sh
│   ├── dev-frontend.sh
│   ├── migrate.sh
│   └── inspect-job.sh
├── frontend
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src
│       ├── main.tsx
│       ├── App.tsx
│       ├── styles
│       │   └── index.css
│       ├── api
│       │   ├── client.ts
│       │   ├── projects.ts
│       │   ├── jobs.ts
│       │   └── studio.ts
│       ├── components
│       │   ├── ProjectNav.tsx
│       │   ├── ChapterEditor.tsx
│       │   ├── ContextInspector.tsx
│       │   ├── JobStatusPanel.tsx
│       │   └── QualityReportPanel.tsx
│       ├── pages
│       │   ├── ProjectListPage.tsx
│       │   ├── WorkspacePage.tsx
│       │   ├── OutlineStudioPage.tsx
│       │   ├── ChapterEditorPage.tsx
│       │   ├── MemoryPage.tsx
│       │   └── JobDetailPage.tsx
│       ├── stores
│       │   └── editorStore.ts
│       └── types
│           └── api.ts
└── backend
    ├── pyproject.toml
    ├── requirements.txt
    ├── alembic.ini
    ├── app
    │   ├── main.py
    │   ├── core
    │   │   ├── config.py
    │   │   ├── ids.py
    │   │   ├── json.py
    │   │   └── responses.py
    │   ├── db
    │   │   ├── session.py
    │   │   └── models.py
    │   ├── migrations
    │   │   └── versions
    │   ├── schemas
    │   │   ├── common.py
    │   │   ├── project.py
    │   │   ├── story_bible.py
    │   │   ├── chapter.py
    │   │   ├── job.py
    │   │   ├── outline.py
    │   │   └── studio.py
    │   ├── api
    │   │   └── v1
    │   │       ├── router.py
    │   │       └── endpoints
    │   │           ├── projects.py
    │   │           ├── story_bible.py
    │   │           ├── project_studio.py
    │   │           ├── writing.py
    │   │           ├── workbench.py
    │   │           ├── knowledge.py
    │   │           └── studio.py
    │   ├── prompting
    │   │   ├── registry.py
    │   │   ├── renderer.py
    │   │   ├── output_parser.py
    │   │   └── templates
    │   │       ├── chapter_plan.jinja2
    │   │       ├── chapter_draft.jinja2
    │   │       ├── chapter_review.jinja2
    │   │       ├── chapter_revise.jinja2
    │   │       └── state_settle.jinja2
    │   ├── runtime
    │   │   ├── chapter_runtime.py
    │   │   ├── context_package.py
    │   │   ├── rule_stack.py
    │   │   ├── quality_gate.py
    │   │   ├── finalization.py
    │   │   └── trace.py
    │   ├── memory
    │   │   ├── banks.py
    │   │   ├── chunker.py
    │   │   ├── embeddings.py
    │   │   ├── retriever.py
    │   │   └── vector_store.py
    │   ├── jobs
    │   │   ├── runner.py
    │   │   ├── artifacts.py
    │   │   └── cancellation.py
    │   ├── services
    │   │   ├── project_service.py
    │   │   ├── studio_service.py
    │   │   ├── workbench_service.py
    │   │   ├── canon_service.py
    │   │   └── outline_debate_service.py
    │   ├── agents
    │   │   ├── workflow.py
    │   │   ├── contracts.py
    │   │   └── nodes
    │   │       ├── draft_chapter.py
    │   │       ├── review_chapter.py
    │   │       ├── revise_chapter.py
    │   │       └── settle_state.py
    │   ├── workers
    │   │   └── jobs.py
    │   └── artifacts
    │       └── .gitkeep
    └── tests
        ├── test_projects_api.py
        ├── test_chapters_api.py
        ├── test_jobs_api.py
        ├── test_context_package.py
        ├── test_prompt_output_parser.py
        ├── test_memory_retriever.py
        └── test_chapter_runtime.py
```

## 4. API 接口定义

所有接口统一以 `/api/v1` 开头。所有响应必须使用第 5 节的统一响应格式。

请求体中的 `model` 字段必须是当前 `LLM_PROVIDER` 或模型目录支持的模型名。`LLM_PROVIDER=qwen` 或 `dashscope` 时默认使用 `qwen-plus`；`LLM_PROVIDER=deepseek` 时默认使用 `deepseek-v4-flash`，需要更高质量时可显式传 `deepseek-v4-pro`；OpenRouter、SiliconFlow、Moonshot、智谱和 Ollama 均走 OpenAI 兼容调用层。不得继续新增 Provider 专用业务 API 路径。

### 4.1 创建项目

`POST /api/v1/projects`

请求体：

```json
{
  "title": "星海遗民",
  "genre": "科幻",
  "target_reader": "喜欢群像、文明冲突和长期伏笔的中文网文读者",
  "premise": "一名失忆舰长在废弃星门中醒来，发现自己可能是旧帝国覆灭的关键责任人。",
  "style_guide": "第三人称有限视角，节奏偏紧，避免过度解释设定。",
  "language": "zh-CN",
  "planned_chapter_count": 80,
  "chapter_word_target": 3000
}
```

成功响应 `data`：

```json
{
  "project": {
    "id": "prj_01JZ0000000000000000000000",
    "title": "星海遗民",
    "genre": "科幻",
    "target_reader": "喜欢群像、文明冲突和长期伏笔的中文网文读者",
    "premise": "一名失忆舰长在废弃星门中醒来，发现自己可能是旧帝国覆灭的关键责任人。",
    "style_guide": "第三人称有限视角，节奏偏紧，避免过度解释设定。",
    "language": "zh-CN",
    "planned_chapter_count": 80,
    "chapter_word_target": 3000,
    "status": "draft",
    "created_at": "2026-06-02T13:00:00Z",
    "updated_at": "2026-06-02T13:00:00Z"
  },
  "story_bible": {
    "id": "bib_01JZ0000000000000000000000",
    "project_id": "prj_01JZ0000000000000000000000",
    "version": 1,
    "world_setting": "",
    "main_conflict": "",
    "themes": [],
    "narrative_pov": "third_person_limited",
    "forbidden_elements": [],
    "continuity_rules": [],
    "created_at": "2026-06-02T13:00:00Z",
    "updated_at": "2026-06-02T13:00:00Z"
  }
}
```

### 4.2 更新故事圣经

`PUT /api/v1/projects/{project_id}/story-bible`

请求体：

```json
{
  "world_setting": "人类文明在星门网络崩塌后三百年分裂为多个城邦舰队。",
  "main_conflict": "主角必须查清旧帝国覆灭真相，同时阻止新星门战争。",
  "themes": ["身份", "责任", "文明记忆"],
  "style_guide": "少用解释性旁白，多通过行动和对话暴露设定。",
  "narrative_pov": "third_person_limited",
  "forbidden_elements": ["机械降神式反转", "无铺垫复活", "章节结尾口号化"],
  "continuity_rules": [
    "角色已知信息不得超过其亲历或被告知的信息。",
    "每章新增设定必须能追溯到故事圣经或章节事件。"
  ]
}
```

成功响应 `data`：

```json
{
  "story_bible": {
    "id": "bib_01JZ0000000000000000000000",
    "project_id": "prj_01JZ0000000000000000000000",
    "version": 2,
    "world_setting": "人类文明在星门网络崩塌后三百年分裂为多个城邦舰队。",
    "main_conflict": "主角必须查清旧帝国覆灭真相，同时阻止新星门战争。",
    "themes": ["身份", "责任", "文明记忆"],
    "style_guide": "少用解释性旁白，多通过行动和对话暴露设定。",
    "narrative_pov": "third_person_limited",
    "forbidden_elements": ["机械降神式反转", "无铺垫复活", "章节结尾口号化"],
    "continuity_rules": [
      "角色已知信息不得超过其亲历或被告知的信息。",
      "每章新增设定必须能追溯到故事圣经或章节事件。"
    ],
    "created_at": "2026-06-02T13:00:00Z",
    "updated_at": "2026-06-02T13:10:00Z"
  }
}
```

### 4.3 大纲议事确认章纲

旧 `POST /api/v1/projects/{project_id}/chapters/plan` 已删除。新版章纲生成必须通过：

- `POST /api/projects/{id}/outline/debate/sessions` 创建议事会话。
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/chapters/stream` 流式讨论章纲。
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/chapters/confirm` 逐章确认并写入正式章节。
- `POST /api/projects/{id}/outline/debate/sessions/{session_id}/chapters/autopilot` 可创建章纲议事后台推进任务；该任务必须按章节顺序执行“讨论单章章纲 -> 确认单章章纲 -> 写入章节与正典更新”，并通过 `generation_jobs` 暴露 parent job 进度、暂停、取消和失败状态。

批量正文生成只允许处理已经存在且已确认/已创建的章节，不得自动创建“批量生成占位章节规划”。

### 4.4 生成章节正文任务

`POST /api/v1/chapters/{chapter_id}/draft`

请求体：

```json
{
  "mode": "first_draft",
  "user_instruction": "强化舰长醒来后的陌生感，结尾留下星门再次点亮的钩子。",
  "use_memory": true,
  "temperature": 0.75,
  "max_words": 3200,
  "idempotency_key": "draft:chp_01JZ0000000000000000000000:v1",
  "model": "qwen-plus"
}
```

成功响应 `data`：

```json
{
  "job": {
    "id": "job_01JZ0000000000000000000001",
    "project_id": "prj_01JZ0000000000000000000000",
    "chapter_id": "chp_01JZ0000000000000000000000",
    "job_type": "draft_chapter",
    "status": "queued",
    "idempotency_key": "draft:chp_01JZ0000000000000000000000:v1",
    "model": "qwen-plus",
    "progress": {
      "current_step": "queued",
      "total_steps": 5,
      "completed_steps": 0,
      "message": "章节正文生成任务已入队"
    },
    "result": null,
    "error": null,
    "created_at": "2026-06-02T13:30:00Z",
    "started_at": null,
    "finished_at": null
  }
}
```

### 4.5 查询任务状态

`GET /api/v1/jobs/{job_id}`

请求体：无

成功响应 `data`：

```json
{
  "job": {
    "id": "job_01JZ0000000000000000000001",
    "project_id": "prj_01JZ0000000000000000000000",
    "chapter_id": "chp_01JZ0000000000000000000000",
    "job_type": "draft_chapter",
    "status": "succeeded",
    "idempotency_key": "draft:chp_01JZ0000000000000000000000:v1",
    "model": "qwen-plus",
    "progress": {
      "current_step": "completed",
      "total_steps": 5,
      "completed_steps": 5,
      "message": "章节正文生成完成"
    },
    "result": {
      "chapter": {
        "id": "chp_01JZ0000000000000000000000",
        "project_id": "prj_01JZ0000000000000000000000",
        "chapter_no": 1,
        "title": "冷眠舱中的陌生人",
        "outline": "主角在废弃舰船中醒来，发现舰船日志被人为删除。",
        "draft_text": "这里是生成后的章节正文。",
        "revision_notes": "",
        "status": "drafted",
        "word_target": 3000,
        "word_count": 2980,
        "created_at": "2026-06-02T13:21:00Z",
        "updated_at": "2026-06-02T13:45:00Z"
      },
      "memory_chunks_created": 3,
      "model_call_ids": ["call_01JZ0000000000000000000000"]
    },
    "error": null,
    "created_at": "2026-06-02T13:30:00Z",
    "started_at": "2026-06-02T13:30:05Z",
    "finished_at": "2026-06-02T13:45:00Z"
  }
}
```

### 4.6 查询章节运行追踪

`GET /api/v1/chapters/{chapter_id}/trace`

请求体：无

成功响应 `data`：

```json
{
  "trace": {
    "chapter_id": "chp_01JZ0000000000000000000000",
    "project_id": "prj_01JZ0000000000000000000000",
    "chapter_no": 1,
    "latest_job_id": "job_01JZ0000000000000000000001",
    "content_hash": "sha256:2d711642b726b04401627ca9fbac32f5da7aa7e5",
    "context_package": {
      "id": "ctx_01JZ0000000000000000000000",
      "chapter_id": "chp_01JZ0000000000000000000000",
      "required_blocks": ["story_bible", "chapter_intent", "previous_chapter_tail", "character_hard_facts"],
      "optional_blocks": ["retrieved_memory", "recent_summaries", "revision_notes"],
      "dropped_blocks": [],
      "estimated_tokens": 6200
    },
    "quality_report": {
      "id": "qlt_01JZ0000000000000000000000",
      "status": "passed",
      "score": 0.86,
      "blocking_issue_count": 0,
      "warning_issue_count": 2
    },
    "state_snapshot": {
      "id": "snap_01JZ0000000000000000000000",
      "snapshot_type": "post_chapter",
      "chapter_no": 1,
      "content_hash": "sha256:2d711642b726b04401627ca9fbac32f5da7aa7e5"
    },
    "events": [
      {
        "id": "evt_01JZ0000000000000000000000",
        "actor_type": "agent",
        "event_type": "chapter_draft_completed",
        "entity_type": "chapter",
        "entity_id": "chp_01JZ0000000000000000000000",
        "created_at": "2026-06-02T13:45:00Z"
      }
    ]
  }
}
```

### 4.7 取消生成任务

`POST /api/v1/jobs/{job_id}/cancel`

请求体：

```json
{
  "reason": "用户手动停止，准备修改章节目标后重试"
}
```

成功响应 `data`：

```json
{
  "job": {
    "id": "job_01JZ0000000000000000000001",
    "project_id": "prj_01JZ0000000000000000000000",
    "chapter_id": "chp_01JZ0000000000000000000000",
    "job_type": "draft_chapter",
    "status": "canceled",
    "cancel_requested": true,
    "cancel_reason": "用户手动停止，准备修改章节目标后重试",
    "run_dir": "backend/artifacts/runs/job_01JZ0000000000000000000001",
    "created_at": "2026-06-02T13:30:00Z",
    "started_at": "2026-06-02T13:30:05Z",
    "finished_at": "2026-06-02T13:36:00Z"
  }
}
```

### 4.8 查询项目记忆概览

`GET /api/v1/projects/{project_id}/memory/overview`

请求体：无

成功响应 `data`：

```json
{
  "memory": {
    "project_id": "prj_01JZ0000000000000000000000",
    "collection": "novel_memory_v1",
    "total_chunks": 42,
    "banks": [
      {
        "bank": "story_premise",
        "chunk_count": 1,
        "latest_chunk_id": "mem_01JZ0000000000000000000000",
        "latest_updated_at": "2026-06-02T13:00:00Z"
      },
      {
        "bank": "chapter_brief",
        "chunk_count": 10,
        "latest_chunk_id": "mem_01JZ0000000000000000000010",
        "latest_updated_at": "2026-06-02T13:45:00Z"
      }
    ],
    "qdrant": {
      "enabled": true,
      "healthy": true,
      "last_error": null
    }
  }
}
```

## 5. 统一响应格式

成功模板：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "request_id": "req_01JZ0000000000000000000000",
  "timestamp": "2026-06-02T13:00:00Z"
}
```

错误模板：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求体字段不合法",
    "details": {
      "field": "planned_chapter_count",
      "reason": "must be greater than 0"
    }
  },
  "request_id": "req_01JZ0000000000000000000001",
  "timestamp": "2026-06-02T13:00:00Z"
}
```

错误码必须从以下集合中选择：

- `VALIDATION_ERROR`
- `NOT_FOUND`
- `CONFLICT`
- `LLM_PROVIDER_ERROR`
- `JOB_FAILED`
- `INTERNAL_ERROR`

## 6. 数据模型

MVP 阶段关系数据库只使用 SQLite。所有主键均为文本 ID，格式由后端生成，前缀用于区分实体类型。

### 6.1 projects

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `prj_` |
| title | TEXT | NOT NULL，长度 1-120 |
| genre | TEXT | NOT NULL，长度 1-60 |
| target_reader | TEXT | NOT NULL |
| premise | TEXT | NOT NULL |
| style_guide | TEXT | NOT NULL，默认空字符串 |
| language | TEXT | NOT NULL，默认 `zh-CN` |
| planned_chapter_count | INTEGER | NOT NULL，`> 0` |
| chapter_word_target | INTEGER | NOT NULL，`500 <= value <= 10000` |
| status | TEXT | NOT NULL，枚举：`draft`、`active`、`archived` |
| created_at | DATETIME | NOT NULL，UTC |
| updated_at | DATETIME | NOT NULL，UTC |

### 6.2 story_bibles

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `bib_` |
| project_id | TEXT | NOT NULL，UNIQUE，FK `projects.id`，ON DELETE CASCADE |
| version | INTEGER | NOT NULL，默认 1，每次更新递增 |
| world_setting | TEXT | NOT NULL，默认空字符串 |
| main_conflict | TEXT | NOT NULL，默认空字符串 |
| themes_json | TEXT | NOT NULL，JSON 数组字符串 |
| style_guide | TEXT | NOT NULL，默认空字符串 |
| narrative_pov | TEXT | NOT NULL，枚举：`first_person`、`third_person_limited`、`third_person_omniscient` |
| forbidden_elements_json | TEXT | NOT NULL，JSON 数组字符串 |
| continuity_rules_json | TEXT | NOT NULL，JSON 数组字符串 |
| created_at | DATETIME | NOT NULL，UTC |
| updated_at | DATETIME | NOT NULL，UTC |

### 6.3 characters

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `chr_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| name | TEXT | NOT NULL，长度 1-80 |
| role | TEXT | NOT NULL，枚举：`protagonist`、`antagonist`、`supporting`、`minor` |
| profile | TEXT | NOT NULL，默认空字符串 |
| motivation | TEXT | NOT NULL，默认空字符串 |
| arc | TEXT | NOT NULL，默认空字符串 |
| relations_json | TEXT | NOT NULL，JSON 数组字符串 |
| status | TEXT | NOT NULL，枚举：`active`、`inactive`、`dead`、`unknown` |
| created_at | DATETIME | NOT NULL，UTC |
| updated_at | DATETIME | NOT NULL，UTC |

约束：`UNIQUE(project_id, name)`。

### 6.4 chapters

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `chp_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| volume_no | INTEGER | NOT NULL，`>= 1` |
| chapter_no | INTEGER | NOT NULL，`>= 1` |
| title | TEXT | NOT NULL，长度 1-120 |
| outline | TEXT | NOT NULL，默认空字符串 |
| draft_text | TEXT | NOT NULL，默认空字符串 |
| revision_notes | TEXT | NOT NULL，默认空字符串 |
| status | TEXT | NOT NULL，枚举：`planned`、`drafting`、`drafted`、`reviewing`、`needs_repair`、`blocked`、`approved` |
| word_target | INTEGER | NOT NULL，`500 <= value <= 10000` |
| word_count | INTEGER | NOT NULL，默认 0，`>= 0` |
| created_at | DATETIME | NOT NULL，UTC |
| updated_at | DATETIME | NOT NULL，UTC |

约束：`UNIQUE(project_id, chapter_no)`。

### 6.5 memory_chunks

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `mem_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| bank | TEXT | NOT NULL，枚举见第 10.5 节 |
| source_type | TEXT | NOT NULL，枚举：`story_bible`、`character`、`chapter`、`user_note` |
| source_id | TEXT | NOT NULL |
| chapter_no | INTEGER | 可为空，`>= 1` |
| content | TEXT | NOT NULL |
| summary | TEXT | NOT NULL，默认空字符串 |
| token_count | INTEGER | NOT NULL，`>= 0` |
| importance | INTEGER | NOT NULL，默认 3，`1 <= value <= 5` |
| is_pinned | INTEGER | NOT NULL，默认 0，枚举：0、1 |
| content_hash | TEXT | NOT NULL |
| qdrant_point_id | TEXT | UNIQUE，可为空 |
| created_at | DATETIME | NOT NULL，UTC |
| updated_at | DATETIME | NOT NULL，UTC |

约束：`UNIQUE(project_id, source_type, source_id, content_hash)`。

### 6.6 generation_jobs

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `job_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| chapter_id | TEXT | 可为空，FK `chapters.id`，ON DELETE SET NULL |
| job_type | TEXT | NOT NULL，枚举：`draft_chapter`、`review_chapter`、`revise_chapter`、`batch_generate`、`refresh_memory` |
| status | TEXT | NOT NULL，枚举：`queued`、`running`、`succeeded`、`failed`、`canceled` |
| run_id | TEXT | NOT NULL，UNIQUE，前缀 `run_` |
| idempotency_key | TEXT | NOT NULL，防重复提交 |
| model | TEXT | NOT NULL |
| request_json | TEXT | NOT NULL，JSON 对象字符串 |
| progress_json | TEXT | NOT NULL，JSON 对象字符串 |
| result_json | TEXT | 可为空，JSON 对象字符串 |
| content_hash | TEXT | 可为空，章节正文 hash |
| cancel_requested | INTEGER | NOT NULL，默认 0，枚举：0、1 |
| cancel_reason | TEXT | NOT NULL，默认空字符串 |
| error_message | TEXT | 可为空 |
| created_at | DATETIME | NOT NULL，UTC |
| started_at | DATETIME | 可为空，UTC |
| heartbeat_at | DATETIME | 可为空，UTC |
| finished_at | DATETIME | 可为空，UTC |

约束：`UNIQUE(project_id, idempotency_key)`。

### 6.7 model_calls

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `call_` |
| job_id | TEXT | NOT NULL，FK `generation_jobs.id`，ON DELETE CASCADE |
| provider | TEXT | NOT NULL，默认 `qwen`，枚举：`openai`、`qwen`、`dashscope`、`deepseek`、`openrouter`、`siliconflow`、`moonshot`、`zhipu`、`ollama`、`openai_compatible` |
| model | TEXT | NOT NULL |
| request_hash | TEXT | NOT NULL |
| response_hash | TEXT | 可为空 |
| request_tokens | INTEGER | NOT NULL，默认 0 |
| response_tokens | INTEGER | NOT NULL，默认 0 |
| latency_ms | INTEGER | NOT NULL，默认 0 |
| prompt_hash | TEXT | NOT NULL |
| error_message | TEXT | 可为空 |
| created_at | DATETIME | NOT NULL，UTC |

### 6.8 event_logs

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `evt_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| actor_type | TEXT | NOT NULL，枚举：`user`、`agent`、`system` |
| event_type | TEXT | NOT NULL |
| entity_type | TEXT | NOT NULL |
| entity_id | TEXT | NOT NULL |
| payload_json | TEXT | NOT NULL，JSON 对象字符串 |
| created_at | DATETIME | NOT NULL，UTC |

### 6.9 chapter_intents

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `int_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| chapter_id | TEXT | NOT NULL，FK `chapters.id`，ON DELETE CASCADE |
| job_id | TEXT | 可为空，FK `generation_jobs.id`，ON DELETE SET NULL |
| goal | TEXT | NOT NULL，长度 1-200 |
| outline_node | TEXT | NOT NULL，默认空字符串 |
| must_hit_json | TEXT | NOT NULL，JSON 数组字符串 |
| must_preserve_json | TEXT | NOT NULL，JSON 数组字符串 |
| must_avoid_json | TEXT | NOT NULL，JSON 数组字符串 |
| required_characters_json | TEXT | NOT NULL，JSON 数组字符串 |
| required_payoffs_json | TEXT | NOT NULL，JSON 数组字符串 |
| style_emphasis_json | TEXT | NOT NULL，JSON 数组字符串 |
| version | INTEGER | NOT NULL，默认 1 |
| created_at | DATETIME | NOT NULL，UTC |

约束：`UNIQUE(chapter_id, version)`。

### 6.10 context_packages

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `ctx_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| chapter_id | TEXT | NOT NULL，FK `chapters.id`，ON DELETE CASCADE |
| job_id | TEXT | 可为空，FK `generation_jobs.id`，ON DELETE SET NULL |
| package_type | TEXT | NOT NULL，枚举：`draft`、`review`、`revise`、`settle_state` |
| required_blocks_json | TEXT | NOT NULL，JSON 数组字符串 |
| optional_blocks_json | TEXT | NOT NULL，JSON 数组字符串 |
| selected_sources_json | TEXT | NOT NULL，JSON 数组字符串 |
| dropped_blocks_json | TEXT | NOT NULL，JSON 数组字符串 |
| summarized_blocks_json | TEXT | NOT NULL，JSON 数组字符串 |
| estimated_tokens | INTEGER | NOT NULL，`>= 0` |
| prompt_hash | TEXT | NOT NULL |
| created_at | DATETIME | NOT NULL，UTC |

### 6.11 quality_reports

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `qlt_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| chapter_id | TEXT | NOT NULL，FK `chapters.id`，ON DELETE CASCADE |
| job_id | TEXT | 可为空，FK `generation_jobs.id`，ON DELETE SET NULL |
| content_hash | TEXT | NOT NULL |
| status | TEXT | NOT NULL，枚举：`passed`、`warning`、`needs_repair`、`blocked` |
| score | REAL | NOT NULL，`0 <= value <= 1` |
| summary | TEXT | NOT NULL，默认空字符串 |
| blocking_issue_count | INTEGER | NOT NULL，默认 0 |
| warning_issue_count | INTEGER | NOT NULL，默认 0 |
| created_at | DATETIME | NOT NULL，UTC |

约束：`UNIQUE(chapter_id, content_hash)`。

### 6.12 quality_issues

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `iss_` |
| report_id | TEXT | NOT NULL，FK `quality_reports.id`，ON DELETE CASCADE |
| severity | TEXT | NOT NULL，枚举：`blocking`、`warning`、`info` |
| category | TEXT | NOT NULL，枚举：`chapter_obligation`、`continuity`、`character`、`world_rule`、`style`、`timeline`、`length` |
| message | TEXT | NOT NULL |
| evidence | TEXT | NOT NULL，默认空字符串 |
| suggestion | TEXT | NOT NULL，默认空字符串 |
| is_resolved | INTEGER | NOT NULL，默认 0，枚举：0、1 |
| created_at | DATETIME | NOT NULL，UTC |

### 6.13 story_state_snapshots

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `snap_` |
| project_id | TEXT | NOT NULL，FK `projects.id`，ON DELETE CASCADE |
| chapter_id | TEXT | 可为空，FK `chapters.id`，ON DELETE SET NULL |
| job_id | TEXT | 可为空，FK `generation_jobs.id`，ON DELETE SET NULL |
| snapshot_type | TEXT | NOT NULL，枚举：`pre_chapter`、`post_chapter`、`manual_checkpoint` |
| chapter_no | INTEGER | NOT NULL，`>= 0` |
| content_hash | TEXT | 可为空 |
| current_state_json | TEXT | NOT NULL，JSON 对象字符串 |
| open_hooks_json | TEXT | NOT NULL，JSON 数组字符串 |
| chapter_summary_json | TEXT | NOT NULL，JSON 对象字符串 |
| continuity_facts_json | TEXT | NOT NULL，JSON 数组字符串 |
| created_at | DATETIME | NOT NULL，UTC |

### 6.14 job_artifacts

| 字段 | 类型 | 约束 |
|---|---|---|
| id | TEXT | PRIMARY KEY，前缀 `art_` |
| job_id | TEXT | NOT NULL，FK `generation_jobs.id`，ON DELETE CASCADE |
| artifact_type | TEXT | NOT NULL，枚举：`worker_log`、`prompt`、`raw_response`、`parsed_output`、`result_json`、`error` |
| path | TEXT | NOT NULL |
| content_hash | TEXT | NOT NULL |
| byte_size | INTEGER | NOT NULL，`>= 0` |
| created_at | DATETIME | NOT NULL，UTC |

约束：`UNIQUE(job_id, artifact_type, content_hash)`。

### 6.15 Qdrant collection

集合名称：`novel_memory_v1`

| 字段 | 类型 | 约束 |
|---|---|---|
| point_id | UUID string | 与 `memory_chunks.qdrant_point_id` 对应 |
| vector | float array | 维度必须与 `EMBEDDING_MODEL` 输出一致 |
| payload.project_id | string | 必填 |
| payload.source_type | string | 必填 |
| payload.source_id | string | 必填 |
| payload.bank | string | 必填 |
| payload.chapter_no | integer/null | 可为空 |
| payload.importance | integer | 必填 |
| payload.content_hash | string | 必填 |

## 7. 架构约束

必须遵守的规则：

1. 前端不得直接调用 LLM 服务，也不得读取 `LLM_API_KEY`；所有 AI 调用只能由后端发起。
2. 所有 API 必须位于 `/api/v1` 下，并且必须使用第 5 节的统一响应格式。
3. 长时间 AI 任务必须走 `generation_jobs`，接口先返回 `job_id`，前端通过轮询查询状态；不得让请求长时间阻塞等待完整生成。
4. 故事圣经、角色、章节和记忆库是生成上下文的唯一来源；不得在 prompt 中引入未持久化的隐藏项目状态。
5. 每次 AI 生成必须记录 `generation_jobs`、`model_calls` 和 `event_logs`；生成内容写入章节前必须能追溯到具体任务。
6. 所有会修改章节正文的入口必须汇入 `runtime/chapter_runtime.py`；不得在 route、service、agent node 或 worker 中各写一套正文生成/修复逻辑。
7. LLM 输出必须经过 Pydantic schema 解析；解析失败最多重试 2 次，并把错误反馈给模型。第三次失败必须让任务失败，不得静默截断、猜字段或当作成功。
8. Prompt 必须从 `backend/app/prompting/templates` 加载，并通过 `PromptRegistry` 记录 `prompt_hash`；不得在业务函数里拼接大段匿名 prompt。
9. 章节生成上下文必须先构造成 `ContextPackage`，并记录 required、optional、dropped、summarized blocks；不得直接把所有项目文本无预算塞进 prompt。
10. 章节正文进入下一章前必须完成 `quality_gate -> finalization -> state_snapshot -> memory_sync`。如果质量门禁不可用，只能记录 `warning` 或 `degraded` 状态，不能伪装成完全通过。
11. LLM 供应商切换必须通过统一 `LLMProviderResolver` 完成；不得新增 DeepSeek 专用 route、service、agent node 或重复 LLM client。

本阶段非目标：

1. 不做多用户系统、登录、权限、团队协作或组织空间。
2. 不做付费、订阅、额度、账单、商店或商业授权管理。
3. 不做 EPUB、PDF、有声书、网站发布、封面生成或平台分发。
4. 不做本地大模型训练、微调、模型评测平台或多模型自动路由优化。
5. 不做“一键全自动写完整本书并自动定稿”；MVP 必须保留人工审阅、修改和确认。
6. 不做复杂自动导演、候选路线投票、自动审批或无人值守批量生产整卷。
7. 不做实时多人协作编辑、评论批注流、版本分支合并或云同步。
8. 不做桌面端 Electron、移动端 App、浏览器插件或系统托盘后台守护。
9. 不做完整时间线子系统；MVP 只记录章节摘要、当前状态、伏笔和连续性事实。
10. 不做复杂 RAG 后台重索引平台；MVP 只支持章节完成后的同步写入和手动刷新。

## 8. 启动命令

首次准备：

```bash
cp .env.example .env
```

启动 Qdrant：

```bash
docker compose up qdrant
```

启动后端：

```bash
cd /Users/mac/Documents/长篇小说撰写agent
/opt/miniconda3/bin/python3.13 -m pip install -r backend/requirements.txt
PYTHON_BIN=/opt/miniconda3/bin/python3.13 ./scripts/dev-backend.sh
```

如果从 `backend/` 目录启动，可以使用 `uvicorn app.main:app`；如果从项目根目录启动，必须使用 `--app-dir backend` 或设置 `PYTHONPATH=backend`。

启动前端：

```bash
cd frontend
corepack enable
corepack prepare pnpm@11.5.1 --activate
pnpm install --frozen-lockfile
cd ..
./scripts/dev-frontend.sh
```

预览已构建前端：

```bash
cd frontend
pnpm build
pnpm start
```

一键启动 MVP 演示环境：

```bash
docker compose up --build
```

访问地址：

- 前端：`http://localhost:5173`
- 后端 API：`http://localhost:8000/api`
- 后端 OpenAPI 文档：`http://localhost:8000/docs`
- Qdrant：`http://localhost:6333`

## 9. 环境变量清单

| 变量名 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| APP_ENV | 是 | `development` | 运行环境：`development`、`test`、`production` |
| LOG_LEVEL | 是 | `info` | 日志级别 |
| FRONTEND_ORIGIN | 是 | `http://localhost:5173` | CORS 允许的前端源 |
| VITE_API_BASE_URL | 是 | `http://localhost:8000/api` | 前端访问后端的基础地址 |
| BACKEND_HOST | 是 | `0.0.0.0` | 本地后端监听地址，由 `scripts/dev-backend.sh` 读取 |
| BACKEND_PORT | 是 | `8000` | 本地后端监听端口，由 `scripts/dev-backend.sh` 读取 |
| FRONTEND_HOST | 是 | `0.0.0.0` | 本地前端监听地址，由 Vite 配置读取 |
| FRONTEND_PORT | 是 | `5173` | 本地前端监听端口，由 Vite 配置读取 |
| DATABASE_URL | 是 | `sqlite:///./data/novel_agent.db` | SQLite 数据库地址 |
| SQL_ECHO | 否 | `false` | 是否输出 SQL 日志 |
| QDRANT_URL | 是 | `http://localhost:6333` | Qdrant 服务地址 |
| QDRANT_COLLECTION | 是 | `novel_memory_v1` | Qdrant 记忆集合名 |
| LLM_PROVIDER | 是 | `qwen` | LLM 提供方标识，枚举：`openai`、`qwen`、`dashscope`、`deepseek`、`openrouter`、`siliconflow`、`moonshot`、`zhipu`、`ollama`、`openai_compatible` |
| LLM_BASE_URL | 是 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 当前 Provider 的 OpenAI 兼容 API 地址 |
| LLM_API_KEY | 是 | 空 | 当前 Provider 的 API Key；优先级低于 Provider 专属 Key |
| LLM_MODEL | 是 | `qwen-plus` | 当前 Provider 的默认文本生成模型 |
| LLM_REQUIRE_REMOTE | 否 | `false` | 真实 API 验收开关；为 `true` 时缺少 API Key 或远程调用失败必须直接报错，不允许本地降级 |
| DASHSCOPE_API_KEY | 否 | 空 | 通义千问 API Key；`LLM_PROVIDER=dashscope` 时优先使用 |
| DASHSCOPE_BASE_URL | 否 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 通义千问 OpenAI 兼容 API 地址 |
| DASHSCOPE_MODEL | 否 | `qwen-plus` | 通义千问默认模型 |
| DEEPSEEK_API_KEY | 否 | 空 | DeepSeek API Key；`LLM_PROVIDER=deepseek` 时优先使用 |
| DEEPSEEK_BASE_URL | 否 | `https://api.deepseek.com` | DeepSeek OpenAI 兼容 API 地址 |
| DEEPSEEK_MODEL | 否 | `deepseek-v4-flash` | DeepSeek 默认模型；高质量任务可改为 `deepseek-v4-pro` |
| OPENROUTER_API_KEY | 否 | 空 | OpenRouter API Key；`LLM_PROVIDER=openrouter` 时使用 |
| OPENROUTER_BASE_URL | 否 | `https://openrouter.ai/api/v1` | OpenRouter OpenAI 兼容 API 地址 |
| OPENROUTER_MODEL | 否 | `openrouter/auto` | OpenRouter 默认模型 |
| SILICONFLOW_API_KEY | 否 | 空 | SiliconFlow API Key；`LLM_PROVIDER=siliconflow` 时使用 |
| SILICONFLOW_BASE_URL | 否 | `https://api.siliconflow.cn/v1` | SiliconFlow OpenAI 兼容 API 地址 |
| SILICONFLOW_MODEL | 否 | `Qwen/Qwen3-32B` | SiliconFlow 默认模型 |
| MOONSHOT_API_KEY | 否 | 空 | Moonshot/Kimi API Key；`LLM_PROVIDER=moonshot` 时使用 |
| MOONSHOT_BASE_URL | 否 | `https://api.moonshot.cn/v1` | Moonshot OpenAI 兼容 API 地址 |
| MOONSHOT_MODEL | 否 | `kimi-k2-0711-preview` | Moonshot 默认模型 |
| ZHIPU_API_KEY | 否 | 空 | 智谱 GLM API Key；`LLM_PROVIDER=zhipu` 时使用 |
| ZHIPU_BASE_URL | 否 | `https://open.bigmodel.cn/api/paas/v4` | 智谱 OpenAI 兼容 API 地址 |
| ZHIPU_MODEL | 否 | `glm-4-plus` | 智谱默认模型 |
| OLLAMA_API_KEY | 否 | `ollama` | Ollama OpenAI 兼容接口占位 Key |
| OLLAMA_BASE_URL | 否 | `http://localhost:11434/v1` | Ollama 本地 OpenAI 兼容 API 地址 |
| OLLAMA_MODEL | 否 | `qwen2.5:7b` | Ollama 默认模型 |
| LLM_TEMPERATURE | 否 | `0.75` | 默认采样温度 |
| LLM_MAX_TOKENS | 否 | `8192` | 单次生成最大输出 token |
| EMBEDDING_MODEL | 是 | `text-embedding-v4` | 默认向量化模型 |
| CONTEXT_MAX_TOKENS | 否 | `12000` | 单次章节生成上下文 token 预算 |
| CONTEXT_REQUIRED_RESERVE_TOKENS | 否 | `7000` | required blocks 的最低保留预算 |
| MEMORY_TOP_K | 否 | `8` | 单次语义检索返回数量 |
| MEMORY_LEXICAL_FALLBACK | 否 | `true` | Qdrant 不可用时是否启用关键词检索 |
| PROMPT_REGISTRY_VERSION | 否 | `v1` | Prompt 模板版本 |
| DEEP_AGENT_ENABLED | 否 | `false` | 是否启用 deepagents 长程执行 harness；关闭时仅提供本地 advisory 会话 |
| DEEP_AGENT_MODE | 否 | `advisor` | Deep Agent 运行模式，当前支持 `advisor`、`orchestrator` |
| DEEP_AGENT_ALLOW_WRITE | 否 | `false` | 是否允许 Deep Agent 在工具审批后执行写入类工具；默认所有工具调用只生成待审批记录 |
| LANGSMITH_TRACING | 否 | `false` | 是否开启 LangSmith tracing |
| LANGSMITH_API_KEY | 否 | 空 | LangSmith API Key，仅后端读取 |
| LANGSMITH_PROJECT | 否 | `novel-agent-local` | LangSmith project 名称 |
| LANGSMITH_ENDPOINT | 否 | 空 | 自定义 LangSmith endpoint，空则使用 SDK 默认 |
| LANGSMITH_PRIVACY_MODE | 否 | `metadata_only` | LangSmith 数据上传隐私模式：`off`、`metadata_only`、`redacted`、`full` |
| LANGSMITH_PROMPT_SYNC | 否 | `manual` | Prompt Hub 同步策略，1.0 仅允许 `manual` |
| JOB_ARTIFACT_DIR | 是 | `artifacts/runs` | 任务日志、prompt、原始响应与解析结果目录 |
| JOB_POLL_INTERVAL_SECONDS | 否 | `2` | 前端查询任务状态的默认间隔 |
| JOB_MAX_RETRY | 否 | `1` | AI 生成任务失败后的最大重试次数 |
| JOB_CANCEL_CHECK_INTERVAL_SECONDS | 否 | `1` | worker 检查取消标志的间隔 |
| REQUEST_TIMEOUT_SECONDS | 否 | `120` | 后端调用 LLM API 的超时时间 |

## 10. 详细设计补充

本节基于 2026-06-02 对代表性开源项目真实代码的抽样阅读。借鉴的是工程结构和失败经验，不复制代码、不继承外部项目许可证约束。

### 10.1 参考项目与采用点

| 项目 | 抽样依据 | 采用到本项目的设计 |
|---|---|---|
| InkOS | `packages/core/src/agents/planner.ts`、`writer.ts`、`reviser.ts`、`models/runtime-state.ts`、`state/runtime-state-store.ts` | 章节意图、上下文包、规则栈、运行时 state delta、解析失败重试、状态快照和校验 |
| Long-Novel-GPT | `core/writer.py`、`core/outline_writer.py`、`prompts/baseprompt.py`、`prompts/创作正文` | prompt 文件化、正文/大纲/审阅/重写模板分离、长文本分块和摘要压缩 |
| NovelClaw | `apps/novelclaw/rag/memory_system.py`、`job_runner.py`、`rag/consistency_checker.py` | 记忆 bank、动态记忆包、worker 日志、取消标志、任务产物目录、一致性检查 |
| AI-Novel-Writing-Assistant | `docs/wiki/workflows/chapter-production-chain.md`、`server/src/services/novel/runtime/ChapterRuntimeCoordinator.ts`、`server/src/prompting/core/contextSelection.ts` | 唯一章节执行链、热路径瘦身、上下文预算、质量门禁缓存、状态闭合后再进入下一章 |

### 10.2 MVP 总体架构

```text
前端操作
  -> FastAPI route
  -> generation_jobs 入队
  -> JobRunner 领取任务
  -> ChapterRuntime 唯一执行链
  -> ContextPackageBuilder 组装上下文
  -> PromptRegistry 渲染模板
  -> LLM Client 调用通义千问 OpenAI 兼容 API
  -> OutputParser 结构化解析
  -> QualityGate 审阅与可接受性判断
  -> Finalization 写入正文、状态快照、事件日志
  -> MemoryService 写入 SQLite + Qdrant
  -> 前端轮询 job/trace 展示结果
```

设计重心：

- `route` 只做 HTTP 映射、鉴权占位、请求校验和响应包装。
- `service` 只做业务用例编排，不直接写 prompt。
- `runtime` 是章节正文生成和修复的唯一入口。
- `agents/nodes` 是 LangGraph 或状态机节点，每个节点只能处理一个明确步骤。
- `prompting` 统一管理模板、版本、渲染、结构化输出提示和解析。
- `memory` 统一管理记忆分 bank、chunk、embedding、检索和 fallback。
- `jobs` 统一管理后台执行、取消、日志、产物和 heartbeat。

### 10.3 唯一章节执行链

所有章节正文生成和修复必须走以下链路：

```text
prepare_context
  -> plan_chapter
  -> draft_chapter
  -> acceptance_gate
  -> revise_chapter（可选，最多 1 次自动修复）
  -> settle_state
  -> sync_memory
  -> finalize_job
```

节点职责：

| 节点 | 输入 | 输出 | 可写数据 |
|---|---|---|---|
| `prepare_context` | project、chapter、story_bible、characters、memory | `ContextPackage`、`RuleStack` | `context_packages` |
| `plan_chapter` | ContextPackage、用户指令 | `ChapterIntent` | `chapter_intents` |
| `draft_chapter` | ChapterIntent、ContextPackage、RuleStack | 章节正文、标题、模型调用记录 | `model_calls`、`job_artifacts` |
| `acceptance_gate` | 正文、ChapterIntent、RuleStack | `QualityReport` | `quality_reports`、`quality_issues` |
| `revise_chapter` | 正文、QualityIssue | 修复后正文 | `model_calls`、`job_artifacts` |
| `settle_state` | 最终正文、上一状态快照 | 状态 delta、章节摘要、连续性事实 | `story_state_snapshots` |
| `sync_memory` | 最终正文、摘要、事实卡 | memory chunks、Qdrant points | `memory_chunks` |
| `finalize_job` | 全部节点结果 | job result、event log | `generation_jobs`、`event_logs` |

强约束：

- `draft_chapter` 不允许直接更新 `chapters.draft_text`；必须等 `quality_gate` 和 `finalization` 后统一写入。
- 自动修复最多 1 次；仍失败时保留当前最佳正文，状态标为 `needs_repair` 或 `blocked`。
- 只要正文 content hash 未变化，不得重复写状态快照、记忆 chunk 或 Qdrant point。
- 下一章生成前必须读取上一章 `story_state_snapshots`，不能只读章节正文。

### 10.4 ContextPackage 与 RuleStack

`ContextPackage` 是每次 LLM 调用的完整上下文清单，必须持久化到 `context_packages`。

字段结构：

```json
{
  "id": "ctx_01JZ0000000000000000000000",
  "chapter_id": "chp_01JZ0000000000000000000000",
  "package_type": "draft",
  "required_blocks": [
    {
      "id": "story_bible",
      "source_type": "story_bible",
      "source_id": "bib_01JZ0000000000000000000000",
      "reason": "全书事实源",
      "content": "故事圣经内容",
      "estimated_tokens": 1800
    }
  ],
  "optional_blocks": [
    {
      "id": "retrieved_memory:mem_01JZ0000000000000000000000",
      "source_type": "memory",
      "source_id": "mem_01JZ0000000000000000000000",
      "reason": "与本章目标相关的历史伏笔",
      "content": "记忆片段",
      "estimated_tokens": 420
    }
  ],
  "dropped_blocks": [],
  "summarized_blocks": [],
  "estimated_tokens": 6200
}
```

required blocks：

- `story_bible`
- `chapter_intent`
- `previous_chapter_tail`
- `character_hard_facts`
- `continuity_facts`

optional blocks：

- `retrieved_memory`
- `recent_chapter_summaries`
- `revision_notes`
- `style_examples`
- `open_hooks`

`RuleStack` 用于告诉模型哪些规则是硬约束、软偏好和诊断提示。

```json
{
  "hard": [
    "不得改变已写章节事实",
    "不得让角色知道其未亲历或未被告知的信息"
  ],
  "soft": [
    "本章节奏偏紧",
    "少用解释性旁白"
  ],
  "diagnostic": [
    "注意上一章结尾动作承接",
    "检查新设定是否能追溯到故事圣经"
  ]
}
```

上下文预算策略：

- 总预算默认 `CONTEXT_MAX_TOKENS=12000`。
- required blocks 必须优先保留；超预算时只能摘要 optional blocks。
- optional blocks 按 `importance`、`chapter_no` 新鲜度、bank 优先级排序。
- 被丢弃或摘要的 block 必须写入 `context_packages.dropped_blocks_json` 或 `summarized_blocks_json`。

### 10.5 记忆 Bank 设计

MVP 使用以下 memory bank：

| bank | 用途 | 写入时机 |
|---|---|---|
| `story_premise` | 项目前提、主线冲突、主题 | 创建/更新故事圣经 |
| `style_guide` | 文风、叙事视角、禁用表达 | 创建/更新故事圣经 |
| `chapter_brief` | 章节目标、摘要、关键事件 | 章节完成后 |
| `character_state` | 角色身份、立场、目标、位置、状态 | 角色更新或章节完成后 |
| `world_state` | 世界观规则、地点、组织、技术/法则 | 故事圣经或章节引入设定后 |
| `continuity_fact` | 必须保持连续性的硬事实 | 章节完成后 |
| `open_hook` | 伏笔、悬念、承诺和预计回收 | 规划或章节完成后 |
| `decision_log` | 用户确认过的创作决策 | 用户显式确认后 |
| `revision_note` | 审阅问题、修复建议、质量债务 | 审阅或修复后 |
| `working_set` | 最近窗口摘要、临时上下文 | 章节生成前后 |

检索策略：

- 默认先查 Qdrant，`top_k=MEMORY_TOP_K`。
- Qdrant 不可用时启用关键词 fallback，fallback 不写入 Qdrant。
- 检索结果必须带 `source_id`、`bank`、`reason`，不能只返回裸文本。
- `decision_log`、`continuity_fact`、`character_state` 的权重高于普通章节正文片段。
- 禁止把整章正文全文作为默认检索块；章节正文只能切为摘要、事实卡和必要短摘录。

### 10.6 Prompt Registry 与结构化输出

Prompt 模板必须拆分为以下文件：

- `chapter_plan.jinja2`
- `chapter_draft.jinja2`
- `chapter_review.jinja2`
- `chapter_revise.jinja2`
- `state_settle.jinja2`

每个模板必须包含：

- `template_id`
- `template_version`
- `expected_output_schema`
- `required_context_blocks`
- `failure_repair_instruction`

输出解析规则：

- `chapter_plan` 输出必须符合 `ChapterIntent`。
- `chapter_draft` 输出必须包含 `title`、`content`、`author_note`。
- `chapter_review` 输出必须符合 `QualityReport`。
- `state_settle` 输出必须符合 `StateDelta`。
- 所有 JSON 输出允许包裹在代码块中，但解析器必须剥离代码块后再校验。
- 解析失败时，把错误信息追加到下一轮 prompt；最多重试 2 次。

### 10.6.1 LLM Provider Resolution

后端必须通过统一的 `LLMProviderResolver` 解析模型配置，不得在 agent、service 或 prompt 代码里直接读取多个供应商环境变量。

解析规则：

| `LLM_PROVIDER` | API Key 优先级 | Base URL 优先级 | Model 优先级 |
|---|---|---|---|
| `qwen` / `dashscope` | `QWEN_API_KEY` -> `DASHSCOPE_API_KEY` -> `LLM_API_KEY` | `QWEN_BASE_URL` -> `DASHSCOPE_BASE_URL` -> `LLM_BASE_URL` -> `https://dashscope.aliyuncs.com/compatible-mode/v1` | 请求体 `model` -> `QWEN_MODEL` -> `DASHSCOPE_MODEL` -> `LLM_MODEL` -> `qwen-plus` |
| `deepseek` | `DEEPSEEK_API_KEY` -> `LLM_API_KEY` | `DEEPSEEK_BASE_URL` -> `LLM_BASE_URL` -> `https://api.deepseek.com` | 请求体 `model` -> `DEEPSEEK_MODEL` -> `LLM_MODEL` -> `deepseek-v4-flash` |
| `openai` | `OPENAI_API_KEY` -> `LLM_API_KEY` | `OPENAI_BASE_URL` -> `LLM_BASE_URL` -> `https://api.openai.com/v1` | 请求体 `model` -> `OPENAI_MODEL` -> `LLM_MODEL` -> `gpt-4.1-mini` |
| `openrouter` | `OPENROUTER_API_KEY` -> `LLM_API_KEY` | `OPENROUTER_BASE_URL` -> `LLM_BASE_URL` -> `https://openrouter.ai/api/v1` | 请求体 `model` -> `OPENROUTER_MODEL` -> `LLM_MODEL` -> `openrouter/auto` |
| `siliconflow` | `SILICONFLOW_API_KEY` -> `LLM_API_KEY` | `SILICONFLOW_BASE_URL` -> `LLM_BASE_URL` -> `https://api.siliconflow.cn/v1` | 请求体 `model` -> `SILICONFLOW_MODEL` -> `LLM_MODEL` -> `Qwen/Qwen3-32B` |
| `moonshot` | `MOONSHOT_API_KEY` -> `LLM_API_KEY` | `MOONSHOT_BASE_URL` -> `LLM_BASE_URL` -> `https://api.moonshot.cn/v1` | 请求体 `model` -> `MOONSHOT_MODEL` -> `LLM_MODEL` -> `kimi-k2-0711-preview` |
| `zhipu` | `ZHIPU_API_KEY` -> `LLM_API_KEY` | `ZHIPU_BASE_URL` -> `LLM_BASE_URL` -> `https://open.bigmodel.cn/api/paas/v4` | 请求体 `model` -> `ZHIPU_MODEL` -> `LLM_MODEL` -> `glm-4-plus` |
| `ollama` | `OLLAMA_API_KEY` -> `ollama` | `OLLAMA_BASE_URL` -> `LLM_BASE_URL` -> `http://localhost:11434/v1` | 请求体 `model` -> `OLLAMA_MODEL` -> `LLM_MODEL` -> `qwen2.5:7b` |

DeepSeek 约束：

- DeepSeek 只作为文本生成 Provider，不作为默认 embedding Provider。
- DeepSeek 调用仍使用 `openai` SDK 和 Chat Completions 兼容格式。
- 推荐默认模型为 `deepseek-v4-flash`；需要更高质量、复杂推理或审稿时可使用 `deepseek-v4-pro`。
- 不得使用计划在 2026-07-24 弃用的 `deepseek-chat` 和 `deepseek-reasoner` 作为默认模型。
- Provider 切换不得改变 API 路径、数据库结构或前端请求体结构。

### 10.7 质量门禁

质量门禁不是文学评分器，只判断本章是否能进入下一步。

必须检查：

- 是否完成 `ChapterIntent.must_hit_json`。
- 是否违反 `must_avoid_json`。
- 是否改变已持久化事实。
- 是否出现角色身份、立场、位置、知识范围错误。
- 是否缺失上一章结尾的必要承接。
- 是否严重偏离目标字数。

质量报告状态：

- `passed`：可以进入 finalization。
- `warning`：可以继续，但必须记录质量债务。
- `needs_repair`：允许自动修复一次。
- `blocked`：不能自动进入下一章，需要用户处理。

### 10.8 Job Runner 与产物目录

每个任务必须拥有独立 run 目录：

```text
backend/artifacts/runs/{job_id}
├── request.json
├── worker.log
├── prompt
│   ├── 01_prepare_context.json
│   ├── 02_plan_chapter.txt
│   ├── 03_draft_chapter.txt
│   └── 04_review_chapter.txt
├── response
│   ├── 02_plan_chapter.raw.txt
│   ├── 03_draft_chapter.raw.txt
│   └── 04_review_chapter.raw.txt
├── parsed
│   ├── chapter_intent.json
│   ├── draft_output.json
│   └── quality_report.json
├── result.json
└── cancel.flag
```

规则：

- `worker.log` 只记录摘要、阶段、耗时、错误，不记录 API Key。
- `cancel.flag` 存在时，worker 必须在下一个节点边界停止。
- `job_artifacts` 记录所有重要文件路径和 hash。
- 原始响应和解析结果都要保存，便于排查模型输出问题。
- heartbeat 超过 60 秒未更新时，前端可显示“可能卡住”，但不能自动判定失败。

### 10.9 状态闭合与记忆同步

章节最终写入顺序固定：

```text
final_content
  -> content_hash
  -> quality_report
  -> story_state_snapshot
  -> memory_chunks
  -> qdrant_points
  -> chapter.status
  -> generation_jobs.result_json
  -> event_logs
```

禁止顺序：

- 先写 `chapter.status=approved` 再补质量报告。
- 先写 Qdrant 再写 SQLite 事实源。
- 修复前正文写入状态快照后继续修复。
- 轮询 job 状态时顺手写入恢复事件或状态快照。

### 10.10 前端交互设计约束

MVP 前端第一屏是工作台，不做营销页。

页面结构：

- 左侧：项目、章节列表、任务队列。
- 中间：章节正文编辑与生成结果。
- 右侧：故事圣经摘要、上下文包、质量报告、记忆命中、任务日志。

交互规则：

- 生成按钮触发 job 后立即进入任务面板。
- 任务运行时允许取消，不允许重复提交同一 `idempotency_key`。
- 上下文包和质量报告必须可查看，但默认折叠。
- 质量门禁为 `blocked` 时，前端必须提示用户处理，不自动继续生成下一章。

### 10.11 测试策略

MVP 必须覆盖以下测试：

| 测试文件 | 覆盖内容 |
|---|---|
| `test_context_package.py` | required/optional blocks、预算、丢弃和摘要记录 |
| `test_prompt_output_parser.py` | JSON 代码块剥离、schema 校验、失败重试错误 |
| `test_chapter_runtime.py` | 唯一章节执行链、自动修复上限、状态闭合顺序 |
| `test_memory_retriever.py` | Qdrant 检索、关键词 fallback、bank 权重 |
| `test_jobs_api.py` | job 状态、取消、heartbeat、artifact 记录 |
| `test_chapters_api.py` | 创建章节、生成任务、trace 查询 |

不要求 MVP 覆盖真实 LLM 集成测试。所有默认测试必须使用 fake LLM client，真实通义千问调用只放在手动 smoke test。

### 0.18 设定版本章节轴与正文候选更新修订（2026-06-21）

设定工作台必须提供项目级章节轴，用于查看每一章触发的正典版本、候选变更与章节生成快照。

新增 API：

- `GET /api/projects/{id}/settings/version-timeline`：返回按章节聚合的设定版本、候选变更、章节/Agent 快照和未绑定章节的更新事件；支持 `ref_type`、`ref_id` 和 `chapter_id` 过滤。

行为约束：

- `CanonVersion` 和 `CanonChangeProposal` 返回结果必须补充 `source_chapter` 摘要，包含 `id`、`volume_no`、`chapter_no` 和 `title`，前端不得再把 `source_chapter_id` 当作“第几章”显示。
- 已确认的大纲/章纲提交可以直接写入正式设定，并记录 `canon_versions`；生成预览阶段不得写入正式设定。
- 章节正文生成后的 `canon_updates` 默认只创建 `canon_change_proposals`，不得直接写入正式角色、实体、世界观事实、伏笔或关系图谱；用户审批通过后才写入正式设定并生成对应版本。
- `relation_updates` 必须进入 `target_type=graph_edge` 的候选变更，审批通过后写入 `graph_edges` 并生成关系版本。
- `foreshadowing_updates` 必须进入 `target_type=foreshadowing` 的候选变更，审批通过后写入 `foreshadowing_items`、同步图谱并生成伏笔版本。
- 设定工作台章节轴必须按卷/章展示更新节点，支持从节点继续审批候选、回滚版本和定位对应设定。

文档版本：2026-06-21

### 0.19 作品资料创作 Star 档案修订（2026-06-21）

设定工作台的“作品资料”必须从单纯表单升级为作品级立项档案，完整体现创作 Star 已生成并确认的关键信息。

新增 API：

- `GET /api/projects/{id}/creation/profile`：返回当前项目、Story Bible、最新创作 Star 会话，以及可展示的 `basic_info`、`selected_worldview`、`selected_protagonist`、`selected_title`、`market_position`、`project_seed`、`core_conflict_system`、`novel_constitution`、`constitution_review`、`canon_candidates` 和 `confirmed_canon`。接口只读，不触发生成或写入。

前端约束：

- 作品资料页必须优先展示“创作 Star 立项档案”，再提供可编辑作品信息和故事圣经表单。
- 档案必须覆盖基本定位、世界观抽卡、主角人设抽卡、书名与包装、核心矛盾系统、小说宪法、压力测试和正典入库摘要。
- 复杂对象必须转换为中文字段、摘要卡、标签或结构化列表展示，不得出现 `[object Object]` 或裸 JSON 充当主 UI。
- 页面视觉应保持工作室工具属性：信息密度适中、层级清晰、卡片边界统一、移动端可读，不做营销式 Hero 或装饰性大背景。

文档版本：2026-06-21
