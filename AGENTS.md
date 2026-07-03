# 叙界推演引擎 / Narraverse Engine 项目规范

> 本文档是本项目后续开发会话的最高优先级项目约束。任何新增功能、依赖、目录、接口、数据表或部署方式，必须先更新本文档并获得确认。

## 0. 文档状态

- 规范版本：2026.07.04
- 当前实现版本：0.2.0 Alpha
- 目标能力集：Studio 1.0
- API 合约阶段：1.0 Draft
- 历史归档：`docs/archive/legacy-agents-before-2026-07-04-cleanup.md`

版本字段必须严格区分：

- `当前实现版本` 表示当前可发布代码版本，必须与 `backend/app/main.py`、`backend/pyproject.toml`、`frontend/package.json` 和 README 保持一致。
- `目标能力集` 表示产品规格目标，不等同于当前发布版本号。
- `API 合约阶段` 表示接口形态接近目标规格但仍允许在 Alpha/Beta 阶段修订。

当前不得把项目版本号直接改成 `1.0.0`。推荐演进顺序：

```text
0.2.0 Alpha -> 0.3.0 Beta -> 0.9.0 RC -> 1.0.0 Stable
```

## 1. 当前产品边界

叙界推演引擎是本地优先的多模型长篇小说创作工作室。当前实现围绕以下能力构建：

- FastAPI 后端服务。
- React + TypeScript Web 前端。
- Python CLI 入口。
- SQLite 本地数据库。
- 统一 LLM Client，支持 OpenAI 兼容模型供应商和本地 fallback。
- 创作 Star 分步立项。
- 回合制大纲议事。
- 章节正文生成和批量生成。
- 正典库、角色、实体、世界观事实、关系图谱、伏笔和连续性问题。
- Agent 运行轨迹、任务记录、版本快照、diff、回滚和分支探索。
- 本地导出、备份、恢复和导入相关入口。
- Deep Agent 与 LangSmith 可选管理能力。

本项目不是 SaaS，不默认要求登录、云端数据库或公网服务。所有默认部署都应能在普通用户本机运行。

## 2. 当前实现功能地图

| 模块 | 当前定位 |
|---|---|
| 创作 Star | 唯一前台立项入口，完成基础信息、世界观卡、主角卡、书名包装、核心矛盾、小说宪法、压力测试和正典候选预览。 |
| 大纲议事 | 正式大纲生成入口，按 `book`、`volumes`、`chapters` 阶段进行回合制实时讨论、用户插话、确认和提交。 |
| 正文工作台 | 项目级三栏写作环境，提供章节目录、正文编辑、AI 协作、选区修改提案、自动保存、版本和字数统计。 |
| 设定工作台 | 统一正典文件树，管理角色、实体、世界事实、图谱、伏笔、候选变更、重复项、锁定字段、影响范围和版本轴。 |
| 批量生成 | 基于已确认章节的异步任务队列，支持暂停、恢复、取消、重试、进度恢复和失败追踪。 |
| Agent 配置 | 展示正式 Agent、提示词模板、可视化工作流、模型目录和 Agent 模型覆盖。 |
| Deep Agent | 可选总管层，默认 advisory 模式；写入类工具调用必须走审批边界。 |
| LangSmith | 可选观测、Prompt/Eval 管理层；默认关闭远程写入，隐私模式默认 `metadata_only`。 |
| 导出 | 支持 Markdown、TXT、HTML、PDF、EPUB、Word 等本地导出路径；部分格式是本地最小可读实现，不等同完整排版引擎。 |
| CLI | 支持项目创建、恢复、章节生成、查询、版本、正典包导出和作品导出等脚本化入口。 |

## 3. 版本和发布策略

当前实现版本保持 `0.2.0 Alpha`。不要用 `1.0` 表示当前版本；使用 `Studio 1.0` 表示目标能力集。

版本字段写法统一为：

```md
当前实现版本：0.2.0 Alpha
目标能力集：Studio 1.0
API 合约阶段：1.0 Draft
```

只有满足以下条件后，才允许进入 `1.0.0 Stable`：

- README 能让 Windows、macOS、Linux 用户在 10 分钟内完成 Docker 快速启动。
- 默认测试和构建在干净环境中通过。
- 创作 Star、大纲议事、正文生成、正典审批、批量任务、版本和导出至少有一条完整本地验收链路。
- 默认配置不依赖 Qdrant、Redis、Postgres、云数据库或公网服务。
- API Key 只由后端读取，前端不接触任何密钥。
- 所有 AI 写入正文、设定和伏笔的路径都保留用户确认或审批边界。

## 4. 技术栈锁定

实际依赖以 `backend/requirements.txt`、`frontend/package.json`、`frontend/pnpm-lock.yaml` 和 `docker-compose.yml` 为准。根目录 `requirements.txt` 若继续保留，必须与 `backend/requirements.txt` 同步，不得作为另一个版本源。

| 层级 | 技术 | 当前锁定 |
|---|---:|---:|
| 后端运行时 | Python | 3.10+，本机验证 3.13.13 |
| Web 框架 | FastAPI | 0.136.3 |
| ASGI Server | uvicorn | 0.48.0 |
| ORM | SQLAlchemy | 2.0.50 |
| 迁移 | Alembic | 1.18.4 |
| 数据校验 | pydantic | 2.13.4 |
| HTTP 客户端 | httpx | 0.28.1 |
| 配置 | python-dotenv | 1.2.2 |
| LLM SDK | openai | 2.40.0 |
| Agent 编排 | langgraph | 1.2.4 |
| Swarm 依赖 | langgraph-swarm | 0.1.0，依赖可保留，旧大纲线不得恢复 |
| Deep Agent | deepagents | 0.6.10 |
| LangChain | langchain | 1.3.9 |
| LangChain Core | langchain-core | 1.4.7 |
| LangChain OpenAI | langchain-openai | 1.2.2 |
| LangSmith | langsmith | 0.8.15 |
| Markdown 导出 | Markdown | 3.10.2 |
| 向量客户端 | qdrant-client | 1.18.0，可选记忆增强 |
| 测试 | pytest | 9.0.1 |
| 前端运行时 | Node.js | 24.14.0 |
| 包管理 | pnpm | 11.5.1 |
| 前端框架 | React | 18.3.1 |
| 前端语言 | TypeScript | 5.9.3 |
| 构建工具 | Vite | 7.2.7 |
| UI 组件 | Ant Design | 5.27.6 |
| Chat UI | @assistant-ui/react | 0.14.14 |
| 路由 | react-router-dom | 6.30.2 |
| 请求状态 | @tanstack/react-query | 5.100.14 |
| 状态管理 | Zustand | 5.0.8 |
| HTTP | Axios | 1.13.2 |
| 图谱 | ECharts | 6.0.0 |
| 图标 | lucide-react | 1.17.0 |

不得在 `AGENTS.md`、README、Dockerfile、package.json 和 requirements 文件之间维护互相冲突的版本描述。

## 5. AI Provider 和密钥边界

后端必须通过统一 LLM Client 支持：

- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=deepseek`
- `LLM_PROVIDER=qwen`
- `LLM_PROVIDER=dashscope`
- `LLM_PROVIDER=openrouter`
- `LLM_PROVIDER=siliconflow`
- `LLM_PROVIDER=moonshot`
- `LLM_PROVIDER=zhipu`
- `LLM_PROVIDER=ollama`
- 通用 OpenAI 兼容 `LLM_BASE_URL` + `LLM_API_KEY`

配置规则：

- API Key 只能来自环境变量，前端不得读取、保存或转发 API Key。
- 缺少 API Key 时，默认允许本地结构化 fallback 跑通主要流程，但调用结果必须标识未调用远程模型。
- `LLM_REQUIRE_REMOTE=true` 时，缺少 API Key 或远程调用失败必须直接失败，不得 fallback。
- Agent 模型覆盖优先级为：请求体 `model` -> `agent_model_configs` 的 `workflow_id + agent_name` 覆盖 -> Provider 专属默认模型 -> `LLM_MODEL`。
- Agent 模型覆盖只做人工显式配置，不做多模型自动路由优化。

## 6. Agent 产品线

后端 Agent 与服务层按三条独立产品线组织：

1. `backend/app/agents/creation_star/`
   - 抽卡式立项线。
   - 只生成候选设定，用户确认后才写入正式项目和正典。
   - 抽卡与提交编排由 `creation_star/service.py` 承担。

2. `outline_debate`
   - 正式大纲生成与世界构建线。
   - 入口为 `backend/app/api/v1/endpoints/outline_debate.py`。
   - 编排服务为 `backend/app/services/outline_debate_service.py`。
   - 采用回合制实时议事，支持用户插话、`@` 指定角色、打断、逐阶段确认和正式提交。

3. `backend/app/agents/chapter_writing/`
   - 章节正文生成线。
   - 使用稳定 LangGraph StateGraph、canon context、质量门和修订循环。
   - `backend/app/agents/workflow.py` 仅作为章节正文 workflow 的旧导入兼容转发。

共享能力放入 `backend/app/agents/shared/`，包括 canon context、trace、prompt loader、prompt catalog 和 lane contract。

### 6.1 旧大纲线边界

旧 `outline_swarm` 大纲线、旧两段式大纲生成、旧章节规划 API、旧推演图组件和旧本地 `StoryState` 大纲 CLI 已删除，不得恢复。

如果本地文件系统中出现 `backend/app/agents/outline_swarm/__pycache__/`，它只是 Python 缓存产物，不属于源码，不得据此恢复旧模块。

正式大纲生成只能通过：

- Web 大纲页。
- `/api/projects/{project_id}/outline/debate/sessions`
- `/api/projects/{project_id}/outline/debate/sessions/{session_id}/{phase}/run`
- `/api/projects/{project_id}/outline/debate/sessions/{session_id}/{phase}/stream`
- 对应 confirm、commit 和 autopilot 接口。

## 7. 正式 Agent 和 Prompt Catalog

对外稳定的正式 Agent 角色为 11 个：

1. 总策划 Agent
2. 章节规划 Agent
3. 情节叙事 Agent
4. 人物对话 Agent
5. 环境描写 Agent
6. 审核修改 Agent
7. 风格统一 Agent
8. 事实核查 Agent
9. 整合输出 Agent
10. 设定整理 Agent
11. 创作 Star Agent

提示词目录规则：

- `backend/app/prompts/00_*.md` 到 `31_*.md` 是提示词库，不得机械扩展为 32 个正式 Agent。
- `32_creation_worldview_draw_prompt.md`、`33_creation_protagonist_draw_prompt.md`、`34_creation_title_packaging_prompt.md` 是创作 Star 专用抽卡提示词，不是新增正式 Agent。
- Prompt Catalog 必须记录 `prompt_id`、文件名、所属工作流、默认 Agent、标题、输入 schema、输出 schema、必需输入和产物字段。
- `/api/workflows` 必须展示当前可视化工作流和可配置节点，不得暴露旧大纲线。

## 8. 工作流约束

### 8.1 创作 Star

创作 Star 是唯一前台立项入口。新版流程为：

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

约束：

- 所有输出在用户确认前均为候选。
- `creation_star` 只负责世界观、主角、书名与包装卖点候选抽卡。
- `chief_architect` 负责把已确认立项种子收敛为 `core_conflict_system` 与 `novel_constitution`。
- `reviewer` 负责 `constitution_review`。
- `canon_curator` 负责把立项种子、核心矛盾、小说宪法和压力测试映射为 `canon_candidates`。
- `canon-preview` 和 `commit` 必须执行小说宪法质量门。
- 新版前端默认走 `creation/sessions` 分步接口；旧 `creation-star/draw` 和 `creation-star/commit` 仅作兼容。

### 8.2 大纲议事

大纲生成统一收敛为回合制实时议事：

- `book` 阶段：总纲。
- `volumes` 阶段：逐卷卷纲。
- `chapters` 阶段：逐章章纲。

每个 `phase_run` 必须保存：

- `turns`
- `decisions`
- `artifacts`
- `outline_topology`
- 结构化 `result`

`outline_topology` 至少包含：

- `mode`
- `nodes`
- `edges`
- `events`
- `artifacts`
- `metrics`

大纲议事必须遵守：

- 前端只能通过 `OutlineDebatePanel` 展示议事流、逐字流式输出、用户加入讨论、`@` 角色、打断和确认。
- 拓扑信息作为议事流的结构化证据展示，不得恢复旧推演图组件。
- 角色生成与设定生成仅限大纲线，输出为候选 artifact。
- 生成预览阶段不得直接写正式正典；确认或提交后由服务层同步物化。
- S/A 级实体未补全，不允许进入正式大纲；若降级生成，必须标明缺失字段和风险。
- 卷纲生成不得固定套用 5 Phase 或 50 章模板；必须根据作品规模和节奏模型动态选择。

### 8.3 章节正文

章节正文链路：

```text
构建 canon_context
  -> 章节卡
  -> 场景细纲
  -> 正文草稿
  -> 自检
  -> 改写
  -> 整合输出
  -> 审核修改
  -> 事实核查
  -> quality_gate
  -> 必要时修订
  -> 风格统一
  -> 章后叙事账本和正典候选更新
```

所有创作 Agent 生成前必须读取 `canon_context`。`canon_context` 至少包含 project、story_bible、核心角色、相关实体、world_facts、graph 子图、连续性问题和前文摘要。

质量门出现 `blocking` 或 `error` 时不得直接定稿。章节正文生成后的正典更新默认只创建候选变更，用户审批通过后才写入正式设定。

### 8.4 批量生成

批量正文生成必须走异步任务队列：

- `POST /api/write/batch-generate` 立即创建 parent job。
- 只读取已存在且未归档的正式章节。
- parent job 必须记录总章数、已完成章数、当前章节、当前状态消息和子 job 状态。
- 每章使用独立数据库会话和事务提交。
- 暂停、恢复、取消只允许在章节边界生效。
- 恢复或重试时跳过已成功章节。

## 9. API 和路由边界

后端同时提供 `/api` 和 `/api/v1` 前缀。当前前端默认使用：

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

不得再写“所有 API 必须只位于 `/api/v1`”。双前缀是当前 API 合约的一部分。

领域路由必须放在 `backend/app/api/v1/endpoints/`：

- `backend/app/api/v1/endpoints/project_studio.py`：项目、状态、故事圣经、章节读写和项目工作室入口。
- `backend/app/api/v1/endpoints/agents.py`：Agent、创作 Star、提示词模板和工作流图。
- `backend/app/api/v1/endpoints/outline_debate.py`：大纲议事。
- `backend/app/api/v1/endpoints/knowledge.py`：角色、实体、世界观事实、图谱和正典文件树。
- `backend/app/api/v1/endpoints/foreshadowing.py`：伏笔预埋、编辑、删除和回收。
- `backend/app/api/v1/endpoints/writing.py`：写作任务、批量任务、暂停、恢复、取消和 Agent 轨迹。
- `backend/app/api/v1/endpoints/versions.py`：版本列表、diff、回滚和分支。
- `backend/app/api/v1/endpoints/canon.py`：canon context 与正典刷新入口。
- `backend/app/api/v1/endpoints/tools.py`：摘要、事实核查、一致性检查、风格学习和知识查询。
- `backend/app/api/v1/endpoints/exporting.py`：导出和导出模板。
- `backend/app/api/v1/endpoints/workbench.py`：分卷、笔记、章节目录、编辑提案、本地备份等工作台能力。
- `backend/app/api/v1/endpoints/deep_agent.py`：Deep Agent 配置、会话和工具审批。
- `backend/app/api/v1/endpoints/langsmith.py`：LangSmith 状态、Prompt 同步和 Eval。
- `backend/app/api/v1/endpoints/websockets.py`：WebSocket 进度和任务连接。

`backend/app/api/v1/router.py` 只负责挂载路由，不写业务分支。`backend/app/api/v1/endpoints/studio.py` 仅作为 legacy compatibility facade 保留；新增 API 不得继续添加到该文件。

## 10. 数据和正典边界

SQLite 是当前默认数据库。默认部署不得要求 Postgres、Redis、Neo4j 或云数据库。

核心持久化对象包括：

- projects
- story_bibles
- creation_sessions
- chapters
- volumes
- notes
- editor_proposals
- characters
- story_entities
- world_facts
- graph_nodes
- graph_edges
- canon_nodes
- canon_versions
- canon_change_proposals
- continuity_issues
- foreshadowing_items
- generation_jobs
- agent_runs
- agent_messages
- generation_outputs
- version_snapshots
- export_jobs
- deep_agent_sessions
- deep_agent_tool_calls
- langsmith_trace_links

正典更新必须遵守：

- 用户手写设定不得被无来源、无置信度、无原因地覆盖。
- AI 自动设定默认进入候选变更。
- 字段锁定必须保存在 `canon_nodes.metadata_json.locked_fields`。
- 候选变更审批支持 `create`、`update`、`archive`、`merge`。
- 审批通过时必须记录版本、同步 `canon_nodes` 与图谱；驳回时保留审计记录。
- 伏笔回收必须把 `payoff_status` 置为 `paid_off`，并同步图谱关系。

Qdrant 只作为可选记忆增强。Docker 快速启动不得要求用户额外启动 Qdrant；没有 Qdrant 时，项目必须能通过 SQLite 和本地 fallback 跑通核心流程。

## 11. 前端工作室约束

前端是统一创作工作室，不是多个割裂管理页。当前项目路由必须围绕项目上下文共享当前项目、当前章节、当前卷和当前正典上下文。

大纲前端拆分路径必须保持清晰：

- `frontend/src/pages/OutlineStudioPage.tsx`：页面级编排、URL 参数、React Query、选择状态和 mutation 组合。
- `frontend/src/pages/outline/`：大纲目录、编辑器、议事面板、规模规划和批量选择等子模块。

工作室必须提供：

- 项目列表和项目创建。
- 创作 Star 入口。
- 正文工作台。
- 大纲议事工作台。
- 设定工作台。
- 作品资料。
- 角色、世界观、图谱、伏笔。
- 笔记。
- Agent 配置。
- 版本。
- 批量任务。
- 导出。

交互边界：

- AI 编辑操作必须遵循“生成提案 -> 展示差异 -> 用户确认 -> 应用前快照 -> 写入正文”。
- 章节 Chat 选区修改流程为“选中文本 -> 输入修改要求 -> 流式生成建议 -> 用户点击应用到选区 -> 自动保存并保留快照”。
- 流式生成阶段不得直接写入正文。
- 设定更新必须遵循“候选变更 -> 用户审批 -> 写入设定集”。
- 项目首页的“创建新项目”必须进入创作 Star 流程：先创建本地草稿项目，再打开创作 Star 向导。

## 12. Deep Agent 与 LangSmith

Deep Agent 是工作室总管层，不替代 11 个正式 Agent，也不得绕过质量门和人工确认流程。

Deep Agent 权限边界：

- 默认 `DEEP_AGENT_ENABLED=false`。
- `DEEP_AGENT_ALLOW_WRITE=false` 时，所有工具调用必须进入 `pending_approval`。
- 即使 `DEEP_AGENT_ALLOW_WRITE=true`，AI 编辑和设定更新仍必须遵循提案或候选审批流程。
- Deep Agent 工具白名单限定为读取项目上下文、读取 canon context、列章节、启动既有工作流、创建编辑提案、创建候选正典、创建版本快照和查询任务状态。
- 不得开放任意 SQL、文件系统写入、shell 执行或前端直连 API Key。

LangSmith 边界：

- 默认 `LANGSMITH_TRACING=false`。
- 未配置 `LANGSMITH_API_KEY` 时不得尝试远程写入。
- 隐私模式支持 `off`、`metadata_only`、`redacted`、`full`，默认 `metadata_only`。
- `metadata_only` 不得上传小说正文、提示词全文、用户私密设定或章节草稿。
- Prompt 管理以本地 `backend/app/prompts` 与 `prompt_templates` 为主。
- LangSmith Prompt Hub 只做手动 push/pull-preview，pull 结果必须预览并由用户确认后才能覆盖本地提示词。

## 13. 部署和启动

README 是面向普通用户的部署入口，必须保持可执行、跨系统和低门槛。

必须支持：

- Windows 10/11 + Docker Desktop。
- macOS + Docker Desktop。
- Linux + Docker Engine / Docker Compose v2。
- 本地源码启动：Python 3.10+、Node.js 24.14.0、pnpm 11.5.1。

当前 Docker Compose 只启动：

- backend
- frontend

不得在 README 中要求普通用户额外启动 Qdrant、Redis、Postgres 或其他外部服务。若新增可选服务，必须标为“可选增强”，并提供核心流程不依赖它的降级说明。

启动脚本约束：

- 后端本地启动入口为 `scripts/dev-backend.sh`。
- 前端本地启动入口为 `scripts/dev-frontend.sh`。
- 一键本地启动入口为 `scripts/dev.sh`。
- 前端默认 API 地址为 `http://localhost:8000/api`。
- Docker 模式下修改 `VITE_*` 变量后需要重新构建前端镜像。

不得提交：

- `.env`
- `data/`
- `backend/data/`
- `backend/artifacts/`
- `output/`
- `outputs/`
- `logs/`
- `.logs/`
- `test-artifacts/`
- `frontend/node_modules/`
- `frontend/dist/`

## 14. 非目标

当前阶段仍然不做：

1. 用户登录、权限、组织空间或云端多人协作。
2. 支付、订阅、额度、账单或商业授权系统。
3. 在线发布平台、自动投稿或平台账号托管。
4. 默认引入 Neo4j、Postgres、Redis 或复杂向量数据库作为核心依赖。
5. 移动端原生 App、Electron 桌面端、浏览器插件或系统托盘后台守护。
6. 本地模型训练、微调平台或多模型自动路由优化。
7. 前端直接读取或调用 LLM API Key。
8. AI 无审批覆盖用户手写设定或正文。
9. 一键无人值守自动写完整本书并自动定稿。

注意：PDF、EPUB、Word 等本地导出路径已经属于当前项目能力，不得再作为“完全不做”的非目标；只能标注实现质量和排版能力阶段。

## 15. 测试和验收

默认验证命令：

```bash
python -m pytest backend/tests -q
cd frontend
pnpm test
pnpm build
docker compose config --quiet
```

真实 LLM 验收必须显式设置环境变量，例如：

```bash
LLM_REQUIRE_REMOTE=true
RUN_REAL_LLM_CONTRACTS=true
```

默认测试不得依赖真实 API Key。真实 LLM 测试必须可跳过，并在测试报告中说明 Provider、模型、日期、输入规模和输出风险。

## 16. 文档维护规则

任何新增功能、依赖、目录、接口、数据表或部署方式，必须同步更新：

- `AGENTS.md`
- `README.md`
- 必要时更新 `CONTRIBUTING.md`
- 必要时更新 `docs/architecture.md`
- 必要时更新测试或验证报告

文档必须避免：

- 把目标能力集写成当前版本号。
- 同一文件同时保留互相冲突的 MVP 和 Studio 1.0 约束。
- 重复使用修订编号。
- 写已经删除的路由、目录、组件或 CLI 命令。
- 把 Docker 快速启动写成依赖可选服务。
- 把真实 LLM 手动测试写成默认测试要求。

## 17. 历史规格处理

2026-07-04 前的长版 `AGENTS.md` 已归档到：

```text
docs/archive/legacy-agents-before-2026-07-04-cleanup.md
```

归档文件只用于追溯历史决策，不再作为当前开发约束。若归档内容与本文件冲突，以本文件为准。
