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
| LangChain | langchain | 1.3.4 |
| LangChain OpenAI | langchain-openai | 1.2.2 |
| LLM SDK | openai | 2.40.0 |
| ORM | SQLAlchemy | 2.0.50 |
| 数据校验 | pydantic | 2.13.4 |
| 配置 | python-dotenv | 1.2.2 |
| Markdown 导出 | Markdown | 3.10.2 |
| 前端 | React | 18.3.1 |
| 前端语言 | TypeScript | 5.9.3 |
| UI 组件 | Ant Design | 5.27.6 |
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

API Key 只能来自环境变量。缺少 API Key 时，工作流允许本地降级生成可验证草案，但必须在配置和模型调用结果中标明未调用远程模型。

Agent 配置中心允许为每个可视化工作流中的每个 Agent 保存显式模型覆盖。解析优先级为：请求体 `model` → `agent_model_configs` 中的 `workflow_id + agent_name` 覆盖 → Provider 专属默认模型 → `LLM_MODEL`。该能力只做人工显式配置，不做多模型自动路由优化。

### 0.4 11 个 Agent

1. 总策划 Agent：世界观、人物、三卷大纲和全局一致性。
2. 章节规划 Agent：以“顶级长篇网文总编 + 爽文结构设计师”职责生成全书总纲、分卷卷纲和本次章纲；必须读取创作 Star 写入的基本信息、故事圣经、角色、实体、世界观事实，并接收目标总字数、卷数、每卷章节数、每章字数、本次章纲数等参数。
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
- 章节规划：章节规划 Agent → 审核修改 Agent → 设定整理 Agent。
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
15. `version_snapshots`
16. `export_jobs`
17. `user_feedback`

MVP 阶段已有表继续保留；1.0 通过运行时 SQLite 轻量迁移补齐旧库缺失列。

### 0.7 新增 API

后端同时提供 `/api` 与 `/api/v1` 前缀。1.0 前端默认使用 `/api`。

核心路由：

- 项目：`POST/GET /api/projects`，`GET/PUT/DELETE /api/projects/{id}`，`POST /api/projects/{id}/duplicate`
- 状态：`GET/PUT /api/projects/{id}/state`
- Story Bible：`GET/PUT /api/projects/{id}/story-bible`，`POST /api/projects/{id}/story-bible/generate`
- 大纲：`POST /api/projects/{id}/outline/book/generate` 预览生成总纲+动态卷纲，`POST /api/projects/{id}/outline/book/commit` 用户确认后写入 Story Bible 与 Volumes；`POST /api/projects/{id}/outline/chapters/batch-generate` 预览批量章纲，`POST /api/projects/{id}/outline/chapters/commit` 用户确认后写入 Chapters。
- 章节：`POST /api/projects/{id}/chapters/plan` 作为旧兼容接口保留，`GET /api/projects/{id}/chapters`，`GET/PUT /api/projects/{id}/chapters/{chapter_id}`，`POST draft/rewrite/partial-rewrite`
- Agent：`GET /api/agents`，`GET /api/agents/{agent_name}`，`PUT /api/agents/{agent_name}/prompt`，`/api/agents/templates`
- LLM 模型：`GET /api/llm/models`，`GET/PUT /api/agent-model-configs`，`DELETE /api/agent-model-configs/{workflow_id}/{agent_name}`
- 任务：`POST /api/write/generate`，`POST /api/write/batch-generate`，`POST pause/resume/cancel`，`GET /api/jobs/{job_id}`，`GET /api/jobs/{job_id}/agent-runs`
- 版本：`GET /api/versions`，`POST /api/versions/compare`，`POST rollback/branch`
- 图谱/设定集：`GET/POST /api/projects/{id}/characters`，`GET/PUT/DELETE /api/projects/{id}/characters/{character_id}`，`GET/POST /api/projects/{id}/entities`，`PUT/DELETE /api/projects/{id}/entities/{entity_id}`，`GET/POST /api/projects/{id}/world-facts`，`PUT/DELETE /api/projects/{id}/world-facts/{fact_id}`，`GET /api/projects/{id}/graph`，`GET /api/projects/{id}/canon/context`
- Agent 辅助生成设定：`POST /api/projects/{id}/settings/generate`，支持 `target=characters/entities/world_facts/all`；前端默认传 `preview_only=true` 仅生成候选预览，不写入角色/实体/世界观事实和图谱，用户确认后再调用对应创建接口正式入库。
- 创作 Star：`GET /api/creation-star/options`，`POST /api/projects/{id}/creation-star/draw`，`POST /api/projects/{id}/creation-star/commit`
- 工作流结构：`GET /api/workflows`，返回初始化、章节规划、单章正文、批量生成四套可视化节点和边。
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

- 项目级顶部导航：创作 Star、作品、正文、设定、大纲、Agent；原“笔记”顶层入口由 Agent 配置中心替换。
- 设定页必须作为项目内子目录承载角色卡、世界与实体、关系图谱、伏笔四类页面，路径统一为 `/projects/{id}/settings/*`，四类页面使用一致的设定集导航和卡片式信息布局。
- 项目二级工具栏只允许在“正文”工作区出现，内容为：批量、笔记、导出、版本；图谱、世界、伏笔不得再作为正文外的二级工具栏入口。
- 正文工作区三栏布局：左侧卷章目录与创作资源，中间正文编辑器，右侧 AI 协作助手。
- 项目内页面共享当前项目、当前章节、当前卷和当前上下文，不得要求用户在功能间重复选择项目。
- 支持专注写作、亮暗主题、自动保存、字数统计、智能排版、高频词、查找替换和版本恢复。
- AI 编辑操作必须遵循“生成提案 → 展示差异 → 用户确认 → 应用前快照 → 写入正文”的流程；不得直接无确认覆盖用户正文。
- 设定更新必须遵循“候选变更 → 用户审批 → 写入设定集”的流程。
- 本地备份、恢复、导入和导出属于 1.0 范围；云同步、平台账号托管和自动发布仍属于非目标。
- 项目顶部导航第一个入口必须是“创作 Star”，位于“作品”左侧；正文工具栏不再重复放置该入口。
- 创作 Star 用于抽卡式立项。流程为：基本信息与标签选择 → 世界观抽卡 → 主角人设抽卡 → 项目总设定表/世界观规则表 → 创建书名 → 用户确认后写入作品信息和设定集。
- 创作 Star 每个抽卡环节都必须读取前序环节数据：主角参考已选世界观，总设定表参考世界观和主角，书名参考世界观、主角、总设定表和规则表。每次“换一批/重抽”都必须生成新的批次并返回本轮上下文提示词快照，不得复用固定顺序结果。
- 创作 Star 书名环节必须同时支持书名抽卡和作者自定义书名；自定义书名被选中后必须作为 `selected_title` 写入项目标题。
- 项目首页的“创建新项目”必须进入创作 Star 流程：先创建本地草稿项目，再打开创作 Star 向导，最后由用户确认写入正式标题和设定。

新增本地工作室数据：

1. `volumes`：分卷名称、卷纲、顺序和状态。
2. `notes`：目录化写作笔记、灵感卡和可引用上下文。
3. `editor_proposals`：AI 编辑提案、原文、建议稿、diff、审批状态。
4. `chapters` 补充 `sort_order`、`deleted_at`、`is_locked`，用于排序、回收站和锁定。

新增核心 API：

- 分卷：`GET/POST /api/projects/{id}/volumes`，`PUT/DELETE /api/projects/{id}/volumes/{volume_id}`
- 目录：`POST /api/projects/{id}/chapters`，`POST /api/projects/{id}/chapters/reorder`，`GET /api/projects/{id}/chapters/trash`，`POST /api/projects/{id}/chapters/trash/batch`，`POST trash/restore`
- 笔记：`GET/POST /api/projects/{id}/notes`，`PUT/DELETE /api/projects/{id}/notes/{note_id}`
- 快照：`POST /api/projects/{id}/chapters/{chapter_id}/snapshot`
- AI 编辑提案：`POST /api/projects/{id}/chapters/{chapter_id}/proposals`，`GET /api/projects/{id}/proposals`，`POST apply/reject`
- 本地备份：`GET /api/projects/{id}/backup`

### 0.10 13-Agent 长篇大纲推演系统（2026-06-07）

项目必须并入独立的“长篇小说多 Agent 推演系统”，用于从【现有世界观】和【一句话故事】开始生成完整长篇纲要。该系统不负责正文创作，只负责大纲、节拍、伏笔和结构推演。

输出必须覆盖：

1. 故事核心
2. 类型卖点定位
3. 世界圣经
4. 主角成长线
5. 人物树
6. 势力冲突表
7. 金手指升级体系
8. 全书10卷总纲
9. 逐卷50章大纲
10. 章节节拍表
11. 伏笔账本
12. 逻辑审计报告
13. 最终修订版纲要

核心设计原则：

- 不做“万能写作 Agent”，必须是“总编 Agent 控制状态机 + 专项 Agent 分层生成 + 审计 Agent 强制返工 + StoryState 持续写回”的闭环系统。
- 默认规模为 100 万字、10 卷、每卷 50 章、每章约 2000 字；这些参数可由调用方覆盖。
- 所有 13 个大纲推演 Agent 的固定系统提示词必须保存在 `backend/app/agents/prompts.py`，不得压缩、删减或改写为摘要版。
- 13 个 Agent 类必须继承统一 `BaseAgent`，并通过统一 `client.generate()` 调用模型。
- 默认 `MockOutlineLLMClient` 必须可离线运行；`OpenAIOutlineLLMClient` 只能从环境变量读取 API Key，不得硬编码。
- `StoryState`、`ProjectConfig`、`WorldBible`、`VolumeOutline`、`ForeshadowingItem`、`AuditReport` 等结构必须用 pydantic v2 模型验证。
- `GateValidator` 必须实现故事核心、世界圣经、人物系统、全书结构、单卷结构、全局闭环六类验收标准。
- `RevisionRouter` 必须按问题类型路由到对应 Agent：主角目标不清、世界规则混乱、战力膨胀、配角工具化、势力冲突弱、卷与卷割裂、单卷节奏弱、爽点重复、伏笔没回收、结局突兀、综合失控。
- CLI 必须支持：`init`、`set-input`、`run-full`、`run-stage`、`run-volume`、`audit`、`export --outline`。
- 本地状态默认保存到 `./workspace/story_state.json`，Markdown 默认导出到 `./workspace/exports/`，导出文件名固定为 `01_故事核心.md` 到 `13_最终修订版纲要.md`。

### 0.11 正典补全与多 Agent 推演系统（2026-06-08）

在 13-Agent 长篇大纲推演系统之上，项目必须提供“长篇小说多 Agent 协作推演与正典补全系统”，用于从“已有世界观 + 一句话故事”开始，持续追问为什么、抽取实体、补全 S/A 级正典、检查连续性，并导出可复用的 `final_outline.md` 与 `canon_store.json`。

核心架构：

- LangGraph 兼容主流程：`START → SeedInterpreterNode → WhyQuestionNode → StoryDirectorAgent → EntityExtractorAgent → CanonCompletionRouter → 对应补全 Agent → CanonMergeNode → ConflictAgent → ProgressiveComplicationAgent → CrisisClimaxAgent → PlotArchitectAgent → BeatControllerAgent → ForeshadowingAgent → ContinuityAgent → ExportNode → END`。
- Swarm 式 Agent handoff 图必须保存在代码中，可由前端展示。
- 正典库使用本地 JSON：`canon_store.json`、`trace_store.json`、`version_store.json`，不得默认引入 Neo4j 或复杂向量数据库。
- 缺少真实 LLM API Key 时，必须使用 `MockLLM` 或规则化回退生成结构化结果，保证 CLI/API/UI 可验证。

最高优先级规则：

1. 多问为什么：关键设定、行动、冲突、危机、高潮必须说明为什么现在发生、为什么必须由此人经历、为什么不能逃避、为什么会增加代价、为什么读者在意、为什么推动主线、为什么不破坏已有设定。
2. 不确定不硬编：无法确认的设定、规则、动机、因果或时间线必须创建 `UncertaintyTicket`。
3. 重要实体必须补全：新增角色、事件、物品、势力、地点、规则、秘密、资源、制度等实体必须判断是否入正典库。
4. S / A 级实体未补全，不允许进入正式大纲。
5. 剧情节点必须带戏剧功能：说明改变了什么、增加了什么压力、制造了什么新问题、如何逼近危机和高潮。
6. 严格区分危机、高潮、结果：危机是不可逆选择，高潮是执行选择，结果是承担后果。
7. 每次 Agent 输出后必须经过实体抽取、正典补全、正典合并和连续性检查。

新增后端模块：

- `backend/app/schemas/canon.py`：`NovelState`、`DramaNode`、`UncertaintyTicket`、`CanonCompletionTicket`、`CanonEntity`、各类实体 Profile、`ConflictMatrix`、`ForeshadowingRecord`、`ContinuityIssue`。
- `backend/app/storage/canon_store.py`：`CanonStore.load/save/upsert_entity/get_entity/list_entities/find_incomplete_entities/mark_entity_complete/record_version/detect_conflict`。
- `backend/app/services/entity_router.py`：按实体类型和缺失字段路由到 `CharacterArcAgent`、`RelationshipAgent`、`PlotArchitectAgent`、`CrisisClimaxAgent`、`ItemLoreAgent`、`RuleSystemAgent`、`FactionSocietyAgent`、`WorldSettingAgent`、`LocationAgent`、`ForeshadowingAgent`、`ThemeAgent`、`ContinuityAgent`。
- `backend/app/services/canon_merge.py`：判断新增、扩展、修正、冲突、信息不足；不得直接覆盖已完成正典。
- `backend/app/services/validators.py`：ContinuityAgent 门禁；S/A 缺档案必须失败。
- `backend/app/agents/canon_workflow.py`：正典推演主流程与 handoff 图。
- `backend/app/prompts/*.md`：全局提示词和 18 个专业 Agent 独立提示词；不得省略。

新增 API：

- `POST /api/projects/{id}/canon-studio/run`
- `GET /api/projects/{id}/canon-studio/store`
- `GET /api/projects/{id}/canon-studio/final-outline`

CLI：

```bash
python main.py canon-run --input data/sample_input.json --output outputs/final_outline.md
python cli.py --input data/sample_input.json --output outputs/final_outline.md
```

前端：

- 大纲工作台必须提供“正典补全”区域，包含世界观输入框、一句话故事输入框、类型、风格、目标篇幅、Agent 执行轨迹、active/handoff 图、正典库实体表、实体补全状态表、DramaNode 故事节点图、ContinuityAgent 审查结果、`final_outline.md` 下载、`canon_store.json` 下载。

### 0.10 结构拆分约束（2026-06-08）

为避免 1.0 功能继续堆叠到单一页面或单一路由文件，后续开发必须遵守以下拆分边界。

后端 API 路由按领域放在 `backend/app/api/v1/endpoints/`：

- `backend/app/api/v1/endpoints/project_studio.py`：项目、状态、故事圣经和章节读写。
- `backend/app/api/v1/endpoints/agents.py`：Agent、创作 Star、提示词模板和工作流图。
- `backend/app/api/v1/endpoints/knowledge.py`：角色、实体、世界观事实和图谱。
- `backend/app/api/v1/endpoints/foreshadowing.py`：伏笔预埋、编辑、删除和回收。
- `backend/app/api/v1/endpoints/writing.py`：写作任务、批量任务、暂停恢复取消和 Agent 轨迹。
- `backend/app/api/v1/endpoints/versions.py`：版本列表、diff、回滚和分支。
- `backend/app/api/v1/endpoints/canon.py`：正典补全、canon context、final_outline 与 canon_store。
- `backend/app/api/v1/endpoints/tools.py`：摘要、事实核查、一致性检查、风格学习和知识查询。
- `backend/app/api/v1/endpoints/exporting.py`：导出和导出模板。
- `backend/app/api/v1/endpoints/websockets.py`：WebSocket 进度和任务连接。

`backend/app/api/v1/router.py` 只负责挂载路由，不写业务分支。`backend/app/api/v1/endpoints/studio.py` 仅作为 legacy compatibility facade 保留；新增 API 不得继续添加到该文件。

前端大纲工作台必须保持薄页面编排：

- `frontend/src/pages/OutlineStudioPage.tsx` 只负责 URL 参数、React Query、选择状态、mutation 编排和子组件组合。
- `frontend/src/pages/outline/OutlineDirectory.tsx` 负责大纲目录、卷章层级、删除和批量删除。
- `frontend/src/pages/outline/OutlineEditorPanel.tsx` 负责总纲、卷纲、章节、章纲编辑区。
- `frontend/src/pages/outline/OutlineGenerationModal.tsx` 负责长篇大纲/卷纲/章纲生成参数弹窗。
- `frontend/src/pages/outline/OutlineInferenceGraph.tsx` 负责 13-Agent 实时推演过程。
- `frontend/src/pages/outline/CanonStudioPanel.tsx` 负责正典补全、下载 `final_outline.md` 和 `canon_store.json`。

结构拆分原则：功能入口增加时优先新增小组件或领域 endpoint；只有共享状态和跨组件编排可以留在页面级文件。若单文件超过约 450 行，继续开发前必须先评估拆分。

### 0.13 Agent 三线架构约束（2026-06-08）

后续 `backend/app/agents` 必须按三条独立产品线组织：

- `backend/app/agents/creation_star/`：抽卡式立项，只生成候选设定，用户确认后写入正式项目；抽卡与提交编排由 `creation_star/service.py` 承担。
- `backend/app/agents/outline_swarm/`：大纲生成与世界构建，使用 `langgraph-swarm` 做动态 handoff 和有限循环；每个 Swarm 节点必须通过 `OutlineSwarmAgentRunner` 加载 `backend/app/prompts/*.md` 并调用统一 `llm_client`，无 API Key 时使用同 schema 的本地降级结果。
- `backend/app/agents/chapter_writing/`：章节正文生成，使用稳定 LangGraph StateGraph 和质量门修订循环；真实 `AgentWorkflow` 必须归属本目录。

共享能力放入 `backend/app/agents/shared/`，包括 canon context、trace、prompt loader 和 lane contract。`backend/app/agents/workflow.py` 仅作为 `chapter_writing.workflow` 的旧导入兼容转发；`outline_workflow.py`、`canon_workflow.py` 暂时作为 legacy compatibility 入口保留；新增 Agent 能力不得继续堆入这些旧文件。

大纲生成线必须消除示例故事硬编码。世界观、势力、物品、地点、秘密、角色和规则必须来自用户输入、项目正典、数据库上下文或 LLM 结构化输出，不得在代码中写死类似“龙骨能源”“最后真龙封印”“帝国能源署”等样例内容。

项目内新大纲工作台必须走两段式接口：`outline/book/generate` 只生成“总纲 + 卷纲”候选，不创建章节；`outline/book/commit` 才写入 Story Bible 与 Volumes。章纲必须通过 `outline/chapters/batch-generate` 独立生成，读取已确认总纲、卷纲和正典上下文；`outline/chapters/commit` 才写入 Chapters。`POST /api/projects/{id}/chapters/plan` 仅作为旧兼容接口保留，仍需保留旧 13-Agent 结构化大纲字段，同时附加 `outline_swarm`、`outline_swarm_agent_trace` 和 `outline_swarm_llm_results`。

卷纲生成不得固定套用 5 Phase 或 50 章模板。每卷必须先选择 `rhythm_model`，可在三幕推进、五段升级、单元案串联、多线群像、战役推进、地图探索、规则试炼、权谋拉扯、情感递进、真相逐层揭示等模型中动态选择，并说明 `why_this_model`、`phase_count` 和 `chapter_distribution`。五段升级只是可选模型之一。

文档版本：2026-06-10

## 1. 项目概述

项目名称：叙界推演引擎 / Narraverse Engine

当前版本：0.2.0

一句话描述：一个面向长篇小说创作者的本地优先 AI 写作工作台，用结构化故事状态、章节规划、记忆检索和人工审稿来辅助持续创作。

目标用户：

- 网络小说作者
- 长篇类型小说作者
- 需要维护世界观、人物关系、章节连续性的 AI 辅助写作者

核心功能：

1. 项目与故事圣经管理：维护题材、受众、世界观、主线冲突、叙事视角、风格约束和禁用元素。
2. 章节规划与正文生成：基于故事圣经、人物设定、已有章节和用户指令生成章节大纲与正文草稿。
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
| 后端运行时 | Python | 3.13.13 | 本机已验证版本 |
| 后端框架 | FastAPI | 0.136.3 | REST API 与 OpenAPI 文档 |
| ASGI Server | uvicorn | 0.48.0 | 本地开发服务 |
| 数据校验 | pydantic | 2.13.4 | 请求体、响应体、配置模型 |
| ORM | SQLAlchemy | 2.0.50 | SQLite 数据访问 |
| 迁移工具 | Alembic | 1.18.4 | 数据库迁移 |
| HTTP 客户端 | httpx | 0.28.1 | 调用 OpenAI 兼容 API |
| LLM SDK | openai | 2.40.0 | 使用 OpenAI 兼容协议接入通义千问与 DeepSeek |
| Agent 编排 | langgraph | 1.2.4 | 章节生成、审稿、重试和状态流 |
| Swarm 编排 | langgraph-swarm | 0.1.0 | 大纲生成线的动态 Agent handoff 与有限循环 |
| Agent 基础框架 | langchain | 1.3.4 | langgraph-swarm 运行依赖 |
| Agent 基础库 | langchain-core | 1.4.0 | 消息、工具、提示模板基础类型 |
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
├── Codex.md
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
│       │   ├── chapters.ts
│       │   ├── jobs.ts
│       │   ├── memory.ts
│       │   └── runtime.ts
│       ├── components
│       │   ├── AppShell.tsx
│       │   ├── ProjectNav.tsx
│       │   ├── ChapterEditor.tsx
│       │   ├── ContextInspector.tsx
│       │   ├── JobStatusPanel.tsx
│       │   └── QualityReportPanel.tsx
│       ├── pages
│       │   ├── ProjectListPage.tsx
│       │   ├── ProjectWorkspacePage.tsx
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
    │   │   ├── memory.py
    │   │   └── runtime.py
    │   ├── api
    │   │   └── v1
    │   │       ├── router.py
    │   │       └── endpoints
    │   │           ├── projects.py
    │   │           ├── story_bible.py
    │   │           ├── chapters.py
    │   │           ├── jobs.py
    │   │           ├── memory.py
    │   │           └── runtime.py
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
    │   │   ├── chapter_service.py
    │   │   ├── generation_service.py
    │   │   ├── memory_service.py
    │   │   └── state_service.py
    │   ├── agents
    │   │   ├── workflow.py
    │   │   ├── contracts.py
    │   │   └── nodes
    │   │       ├── plan_chapters.py
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

### 4.3 生成章节规划任务

`POST /api/v1/projects/{project_id}/chapters/plan`

请求体：

```json
{
  "volume_title": "第一卷：失落星门",
  "start_chapter_no": 1,
  "chapter_count": 10,
  "outline_requirement": "建立主角身份谜团、星门遗迹、第一位主要反派和舰队内部矛盾。",
  "target_words": 1000000,
  "volume_count": 10,
  "chapters_per_volume": 50,
  "chapter_word_target": 2000,
  "overwrite_existing": false,
  "idempotency_key": "plan:prj_01JZ0000000000000000000000:volume-1:chapters-1-10:v1",
  "model": "qwen-plus"
}
```

成功响应 `data`：

```json
{
  "job": {
    "id": "job_01JZ0000000000000000000000",
    "project_id": "prj_01JZ0000000000000000000000",
    "chapter_id": null,
    "job_type": "plan_chapters",
    "status": "queued",
    "idempotency_key": "plan:prj_01JZ0000000000000000000000:volume-1:chapters-1-10:v1",
    "model": "qwen-plus",
    "progress": {
      "current_step": "queued",
      "total_steps": 4,
      "completed_steps": 0,
      "message": "章节规划任务已入队"
    },
    "result": null,
    "error": null,
    "created_at": "2026-06-02T13:20:00Z",
    "started_at": null,
    "finished_at": null
  }
}
```

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
| job_type | TEXT | NOT NULL，枚举：`plan_chapters`、`draft_chapter`、`review_chapter`、`revise_chapter`、`refresh_memory` |
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

DATABASE_URL=sqlite:///./backend/data/novel_agent.db \
JOB_ARTIFACT_DIR=backend/artifacts/runs \
FRONTEND_ORIGIN=http://localhost:5173 \
/opt/miniconda3/bin/python3.13 -m uvicorn --app-dir backend app.main:app --reload --host 0.0.0.0 --port 8000
```

如果从 `backend/` 目录启动，可以使用 `uvicorn app.main:app`；如果从项目根目录启动，必须使用 `--app-dir backend` 或设置 `PYTHONPATH=backend`。

启动前端：

```bash
cd frontend
corepack enable
corepack prepare pnpm@11.5.1 --activate
pnpm install --frozen-lockfile
pnpm dev --host 0.0.0.0 --port 5173
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
- 后端 API：`http://localhost:8000/api/v1`
- 后端 OpenAPI 文档：`http://localhost:8000/docs`
- Qdrant：`http://localhost:6333`

## 9. 环境变量清单

| 变量名 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| APP_ENV | 是 | `development` | 运行环境：`development`、`test`、`production` |
| LOG_LEVEL | 是 | `info` | 日志级别 |
| FRONTEND_ORIGIN | 是 | `http://localhost:5173` | CORS 允许的前端源 |
| VITE_API_BASE_URL | 是 | `http://localhost:8000/api/v1` | 前端访问后端的基础地址 |
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
| JOB_ARTIFACT_DIR | 是 | `backend/artifacts/runs` | 任务日志、prompt、原始响应与解析结果目录 |
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
