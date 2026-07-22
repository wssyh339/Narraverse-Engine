# 后端作用域规范

> 适用于 `backend/**`、根 `requirements.txt` 和后端 Dockerfile。本文件与根 `AGENTS.md` 同时生效；先遵守根基线，再应用这里的后端细则。

## BACKEND-STACK-001：运行时与依赖

后端实际依赖以 `backend/requirements.txt` 和 `backend/pyproject.toml` 为准。根 `requirements.txt` 若继续保留，必须与 `backend/requirements.txt` 同步，不得成为第二版本源。

| 技术 | 当前锁定 |
|---|---:|
| Python | 3.10+，本机验证 3.13.13 |
| FastAPI | 0.136.3 |
| uvicorn | 0.48.0 |
| SQLAlchemy | 2.0.50 |
| Alembic | 1.18.4 |
| pydantic | 2.13.4 |
| httpx | 0.28.1 |
| python-dotenv | 1.2.2 |
| openai | 2.40.0 |
| langgraph | 1.2.4 |
| langgraph-swarm | 0.1.0；依赖可保留，历史大纲线不得恢复 |
| deepagents | 0.6.10 |
| langchain | 1.3.9 |
| langchain-core | 1.4.7 |
| langchain-openai | 1.2.2 |
| langsmith | 0.8.15 |
| Markdown | 3.10.2 |
| qdrant-client | 1.18.0；仅可选记忆增强 |
| pytest | 9.0.1 |

新增、删除或升级依赖前，遵守根规则 `GLOBAL-CHANGE-GATE-001`，并同步所有后端依赖来源和版本说明。

## BACKEND-LLM-001：Provider、密钥与 fallback

统一 LLM Client 必须支持：

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

- API Key 只能来自环境变量，任何响应、日志、trace 或前端接口都不得暴露 Key。
- 缺少 API Key 时，默认允许本地结构化 fallback 跑通主要流程，但结果必须标识未调用远程模型。
- `LLM_REQUIRE_REMOTE=true` 时，缺少 API Key 或远程调用失败必须直接失败，不得 fallback。
- Agent 模型覆盖优先级为：请求体 `model` → `agent_model_configs` 的 `workflow_id + agent_name` 覆盖 → Provider 专属默认模型 → `LLM_MODEL`。
- Agent 模型覆盖只做人工显式配置，不做多模型自动路由优化。

## BACKEND-AGENT-LANES-001：三条 Agent 产品线

后端 Agent 与服务层按三条独立产品线组织：

1. `backend/app/agents/creation_star/`
   - 抽卡式立项能力，只生成候选设定。
   - 旧兼容 `creation-star/draw` 与 `creation-star/commit` 由 `creation_star/service.py` 承担。
   - 当前正式 `creation/sessions` 分步会话由 `backend/app/services/studio_service.py` 编排，并复用 Creation Star 能力；不得把新会话入口误记为仅由 lane service 所有。
2. `outline_debate`
   - 唯一正式大纲生成与世界构建线。
   - API 入口为 `backend/app/api/v1/endpoints/outline_debate.py`，编排服务为 `backend/app/services/outline_debate_service.py`。
   - 支持回合制实时议事、用户插话、`@` 指定角色、打断、逐阶段确认和正式提交。
3. `backend/app/agents/chapter_writing/`
   - 章节正文生成线，使用稳定 LangGraph StateGraph、canon context、质量门和修订循环。
   - `backend/app/agents/workflow.py` 仅作为章节正文 workflow 的旧导入兼容转发。

共享能力放入 `backend/app/agents/shared/`，包括 canon context、trace、prompt loader、prompt catalog 和 lane contract。

2026-07-04 前的大纲实现已经归档。历史源码、历史本地 CLI、历史图组件和历史章节规划入口不得恢复；Python 缓存不是源码。正式大纲只能通过 Web 大纲页、`/api/projects/{project_id}/outline/debate/sessions` 及其 run、stream、confirm、commit、autopilot 接口生成。

## BACKEND-PROMPT-CATALOG-001：AgentSpec 与 Prompt Catalog

不得用旧的固定数量口径概括全部系统，必须区分：

1. 大纲议事运行时席位：`outline_debate/StoryDirectorAgent`、`outline_debate/MarketPositionAgent`、`outline_debate/StructureDoctorAgent`、`outline_debate/CharacterGeneratorAgent`、`outline_debate/SettingGeneratorAgent`、`outline_debate/ContinuityAuditorAgent`。
2. 基础 AgentSpec：`chief_architect`、`creation_star`、`chapter_planner`、`plot_narrator`、`dialogue_writer`、`environment_writer`、`reviewer`、`style_unifier`、`fact_checker`、`integrator`、`canon_curator`。

`chapter_planner` 只允许用于已确认章纲后的章节卡、场景准备、状态变化或专项结构任务，不得作为独立全书大纲、卷纲或章纲入口。

提示词规则：

- `backend/app/prompts/00_*.md` 到 `31_*.md` 是提示词库，不得机械扩展为独立运行时 Agent。
- `32_creation_worldview_draw_prompt.md`、`33_creation_protagonist_draw_prompt.md`、`34_creation_title_packaging_prompt.md` 是创作 Star 抽卡提示词。
- `35_chapter_prep_prompt.md` 绑定 `chapter_planner`，只用于已确认章纲后的章节位置、情绪目标、正典依赖、伏笔提醒和字数预算固化。
- Prompt Catalog 必须记录 `prompt_id`、文件名、所属工作流、默认 AgentSpec 或运行时席位、标题、输入 schema、输出 schema、必需输入和产物字段。
- `/api/workflows` 只能展示当前可视化工作流和可配置节点，不得暴露历史大纲线。

## BACKEND-CREATION-001：创作 Star

创作 Star 是唯一前台立项入口：

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

- 所有输出在用户确认前均为候选。
- `creation_star` 负责世界观、主角、书名与包装卖点候选抽卡。
- `chief_architect` 把已确认种子收敛为 `core_conflict_system` 与 `novel_constitution`。
- `reviewer` 负责 `constitution_review`。
- `canon_curator` 把立项种子、核心矛盾、小说宪法和压力测试映射为 `canon_candidates`。
- `canon-preview` 和 `commit` 必须执行小说宪法质量门。
- 新前端默认走 `creation/sessions` 分步接口；`creation-star/draw` 和 `creation-star/commit` 仅作兼容。

## BACKEND-OUTLINE-001：大纲议事

大纲统一按 `book`、`volumes`、`chapters` 三阶段进行回合制实时议事。每个 `phase_run` 必须保存：

- `turns`
- `decisions`
- `artifacts`
- `outline_topology`
- 结构化 `result`

`outline_topology` 至少包含 `mode`、`nodes`、`edges`、`events`、`artifacts`、`metrics`。

约束：

- 固定 6 个运行时席位：主持总策划、类型卖点、结构医生、角色生成、设定生成、连续性审计。
- 拓扑只作为议事流内的结构化证据，不得恢复历史图组件。
- 角色与设定生成只输出候选 artifact；预览阶段不得直接写正式正典，确认或提交后由服务层物化。
- S/A 级实体未补全时不得进入正式大纲；降级生成必须标明缺失字段和风险。
- 卷纲不得固定套用 5 Phase 或 50 章模板，必须按作品规模和节奏动态选择。
- 前端展示与交互要求由 `frontend/AGENTS.md` 的 `FRONTEND-OUTLINE-001` 所有。

## BACKEND-CHAPTER-001：章节正文与质量门

```text
构建 canon_context
  -> 章节写前准备
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

- 所有创作 Agent 生成前必须读取 `canon_context`；至少包含 project、story_bible、核心角色、相关实体、world_facts、graph 子图、连续性问题和前文摘要。
- `chapter_prep` 必须保留已确认章纲的章节编号、标题、位置、情绪目标、字数预算、正典依赖和伏笔提醒，不得重写全书大纲、卷纲或章纲。
- 质量门必须同时包含 Agent 审校、事实核查和确定性文本检查。确定性检查至少覆盖长度不足、模型拒写、截断、工程元数据泄漏、重复退化、异常标点和超长段落。
- 出现 `blocking` 或 `error` 时不得直接定稿。
- 章后正典更新默认只创建候选变更，审批通过后才写入正式设定。

## BACKEND-MATERIALS-001：导入与写作资料

以下入口默认存入本地 SQLite：

- `/api/projects/{project_id}/import/novel`：拆分章节草稿、生成置顶 `import_report` 笔记，并可创建候选时间线正典。
- `/api/projects/{project_id}/method-packs`：管理原则、章节配方、风格规则和反模式。
- `/api/projects/{project_id}/reference-assets`：管理对标片段、标签、来源和基础文本指标。
- `/api/projects/{project_id}/review/plan`：只生成 `solo`、`lean`、`full` 审稿计划。

这些资料只作为章节准备、正文生成和审稿上下文；写入正文、设定、伏笔或正典仍必须走提案、候选或人工确认。

## BACKEND-BATCH-001：批量生成

- `POST /api/write/batch-generate` 必须立即创建 parent job。
- 只读取已存在且未归档的正式章节。
- parent job 记录总章数、完成数、当前章节、状态消息和子 job 状态。
- 每章使用独立数据库会话和事务提交。
- 暂停、恢复、取消只在章节边界生效。
- 恢复或重试跳过已成功章节。

## BACKEND-API-001：API 与路由所有权

后端同时提供 `/api` 和 `/api/v1`，不得宣称只允许 `/api/v1`。领域路由必须位于 `backend/app/api/v1/endpoints/`：

- `project_studio.py`：项目、状态、故事圣经、章节读写和工作室入口。
- `agents.py`：Agent、创作 Star、提示词模板和工作流图。
- `outline_debate.py`：大纲议事。
- `knowledge.py`：角色、实体、世界事实、图谱和正典文件树。
- `foreshadowing.py`：伏笔预埋、编辑、删除和回收。
- `writing.py`：写作任务、批量任务、控制和 Agent 轨迹。
- `versions.py`：版本、diff、回滚和分支。
- `canon.py`：canon context 与正典刷新。
- `tools.py`：摘要、事实核查、一致性检查、风格学习和知识查询。
- `exporting.py`：导出和模板。
- `workbench.py`：分卷、笔记、章节目录、编辑提案、备份、小说导入、Method Pack、对标资产和审稿计划。
- `deep_agent.py`：Deep Agent 配置、会话和工具审批。
- `langsmith.py`：LangSmith 状态、Prompt 同步和 Eval。
- `websockets.py`：WebSocket 进度和任务连接。

`backend/app/api/v1/router.py` 只挂载路由，不写业务分支。`backend/app/api/v1/endpoints/studio.py` 仅保留 legacy compatibility facade，新增 API 不得继续加入。

## BACKEND-DATA-001：SQLite、正典与持久化

SQLite 是默认数据库；默认部署不得要求 Postgres、Redis、Neo4j 或云数据库。

核心持久化对象包括：

- projects、story_bibles、creation_sessions、chapters、volumes
- notes；`note_type` 可含 `note`、`folder`、`inspiration`、`import_report`、`method_pack`、`reference_asset`、`review_report`
- editor_proposals
- characters、story_entities、world_facts
- graph_nodes、graph_edges
- canon_nodes、canon_versions、canon_change_proposals
- continuity_issues、foreshadowing_items
- generation_jobs、agent_runs、agent_messages、generation_outputs
- version_snapshots、export_jobs
- deep_agent_sessions、deep_agent_tool_calls、langsmith_trace_links

正典更新：

- 用户手写设定不得被无来源、无置信度、无原因地覆盖。
- AI 自动设定默认进入候选变更。
- 字段锁定保存在 `canon_nodes.metadata_json.locked_fields`。
- 候选审批支持 `create`、`update`、`archive`、`merge`。
- 审批通过时记录版本并同步 `canon_nodes` 与图谱；驳回保留审计记录。
- 伏笔回收把 `payoff_status` 置为 `paid_off` 并同步图谱关系。
- 无 Qdrant 时，核心流程仍必须通过 SQLite 和本地 fallback 运行。

## BACKEND-DEEP-001：Deep Agent 与 LangSmith

Deep Agent 是工作室总管层，不替代创作 Star、大纲议事、章节正文或正典维护，也不得绕过质量门和人工确认。

- 默认 `DEEP_AGENT_ENABLED=false`。
- `DEEP_AGENT_ALLOW_WRITE=false` 时，所有工具调用进入 `pending_approval`。
- 即使允许写入，AI 编辑和设定更新仍走提案或候选审批。
- 工具白名单只限读取上下文、读取 canon context、列章节、启动既有工作流、创建编辑提案、创建候选正典、创建快照和查询任务。
- 不得开放任意 SQL、文件系统写入、shell 执行或前端直连 API Key。

LangSmith：

- 默认 `LANGSMITH_TRACING=false`；无 `LANGSMITH_API_KEY` 时不得远程写入。
- 隐私模式支持 `off`、`metadata_only`、`redacted`、`full`，默认 `metadata_only`。
- `metadata_only` 不得上传正文、提示词全文、私密设定或章节草稿。
- 本地 `backend/app/prompts` 与 `prompt_templates` 是 Prompt 管理主源。
- Prompt Hub 只做手动 push/pull-preview；pull 必须预览并由用户确认后才能覆盖本地文件。

## BACKEND-VERIFY-001：后端验证

默认后端验证：

```bash
python3 -m pytest backend/tests -q
```

真实 LLM 测试必须可跳过，只有显式设置根规则规定的远程验收环境变量时才运行。修改 API、迁移、Prompt Catalog、工作流、质量门或持久化模型时，应先运行对应定向测试，再运行默认后端套件。
