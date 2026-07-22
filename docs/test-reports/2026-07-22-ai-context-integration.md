# AI 项目上下文工具接入验收报告

## 1. 报告状态

- 日期：2026-07-22
- 范围：`codebase-memory-mcp 0.9.0` 只读试点、Markdown ADR 与 Mermaid、Repomix 1.17.0。
- DeepWiki Open：**未启用**；本轮不得克隆、运行、建索引或生成 Wiki。前三阶段验收通过后仍需用户第二次明确确认。
- 人工 ground truth：已按 2026-07-22 当前工作树源码复核。
- 代码图谱查询、Repomix 统计、敏感路径扫描和项目测试：已完成。
- 当前结论：**前三阶段通过验收**；DeepWiki Open 仍未启用。

本报告将人工审阅的源码事实与工具输出分开记录。`AGENTS.md`、当前源码、测试和正式 API schema 是事实源；代码图谱与 Repomix 仅是检索层。若工作树在实际查询前发生影响下述调用链的变化，必须先重审对应 ground truth。

## 2. 评分规则

- 共 15 题，每题 2 分，总分 30 分。
- 2 分：入口、调用方向、关键符号、写入边界和易误判点均正确；次要细节可简写，但不得改变结论。
- 1 分：主方向正确，但遗漏一个重要中间层、消费者或边界；不得存在相反方向或把候选误写成正式数据等错误。
- 0 分：未回答、定位到无关实现，或出现任一方向性错误。
- 通过线：总分至少 24 分。
- 关键题：Q01、Q03、Q05、Q07、Q10、Q11。关键题即使得 1 分，也不得存在方向性错误；任一关键题有方向性错误则整体验收失败。
- 方向性错误包括但不限于：把调用者和被调用者倒置、把只读误报为写入、把候选误报为正式正典、把同步误报为异步、把非当前路径误报为生产路径、把 `/api` 与 `/api/v1` 错报为单前缀。

## 3. 15 道代码图谱人工基线

以下“问题”用于实际 MCP 只读查询；“人工 ground truth”不得作为工具自报答案，评分时必须将工具结果逐项与源码复核。

### Q01（关键）双 API 前缀下的批量生成入口

**问题：** 从前端创建批量任务到后端服务，给出完整调用方向，并说明最终有哪些 HTTP 路径。

**人工 ground truth：**

`frontend/src/pages/BatchPage.tsx::mutation` → `frontend/src/api/studio.ts::studioApi.batchGenerate`（相对路径 `/write/batch-generate`）→ `frontend/src/api/client.ts::API_BASE_URL`（默认 `http://localhost:8000/api`）→ `backend/app/api/v1/router.py::api_router.add_api_route` → `backend/app/api/v1/endpoints/writing.py::batch_generate`（从 legacy facade 重导出）→ `backend/app/api/v1/endpoints/studio.py::batch_generate` → `backend/app/services/studio_service.py::StudioService.batch_generate`。`backend/app/main.py` 将同一个 `api_router` 分别挂到 `/api` 与 `/api/v1`，所以后端同时暴露 `/api/write/batch-generate` 和 `/api/v1/write/batch-generate`；前端默认调用前者。

**易误判：** 只报告 `/api/v1`；把 `writing.py` 当成独立业务实现；忽略前端 base URL；把根级 WebSocket 路由误当成同一前缀链。

### Q02 创作 Star 会话创建的真实落点

**问题：** `POST /projects/{project_id}/creation/sessions` 从前端到数据库的调用链是什么，哪一层创建持久化对象？

**人工 ground truth：**

`frontend/src/components/CreationStarWizard.tsx::createSession` → `studioApi.createCreationSession` → `api_router` → `backend/app/api/v1/endpoints/agents.py::create_creation_session`（从 `endpoints/studio.py` 重导出）→ `endpoints/studio.py::create_creation_session` → `StudioService.create_creation_session`。服务先以 `_apply_creation_basic_to_project` 更新项目基础字段，再创建 `backend/app/db/models.py::CreationSession`，写入 `basic_info_json`、候选态 `state_json`、`status=draft` 与 `current_step=brief` 后提交。

**易误判：** 把 `agents.py` 当成实现函数所在地；把新版会话创建归到 `backend/app/agents/creation_star/service.py`；漏报创建会话时对项目基础字段的写入。

### Q03（关键）创作 Star 的 Agent 分工、质量门和写入边界

**问题：** 新版创作 Star 各阶段由哪些 Agent/运行时名称承担，正典预览和正式提交分别有哪些质量门与写入？

**人工 ground truth：**

- `StudioService._run_creation_star_draw_step` 用 `creation_worldview_draw`、`creation_protagonist_draw`、`creation_title_packaging` 三个专用运行时名称生成候选卡；模型配置可由 `_configured_creation_star_model` 回退到基础 `creation_star` 配置。
- `creation_session_core_conflict` 与 `creation_session_constitution` 调用 `chief_architect`；`creation_session_constitution_review` 调用 `reviewer`；`creation_session_canon_preview` 调用 `canon_curator`。
- `_require_creation_constitution_ready` 要求压力测试状态为 `passed` 或 `passed_with_notes` 且 `blocking_issues` 为空；预览和提交都执行该门。
- 预览只把 `canon_candidates` 保存到 `CreationSession.state_json`，不写正式设定。
- 提交还调用 `_require_approved_canon_sections`；当前向导显式提交 `project/story_bible/characters/entities/world_facts/graph`。提交更新 Project、StoryBible，创建或更新角色、实体、世界事实、图谱，调用 `_sync_canon_ref` 形成 CanonNode/CanonVersion，并建立版本快照后把会话标为 `committed`。
- 当前实现允许在缺少预览结果时由 commit 本地重建 candidates；这不绕过压力测试门。`approved_canon_sections=None` 在服务 helper 中按完整集合处理，而当前 UI 明确发送完整集合。

**易误判：** 把三个专用抽卡提示词机械当成新的基础 AgentSpec；声称预览已写正式正典；声称 commit 必须先调用前端 preview；漏掉压力测试阻塞项或人工审批集合。

### Q04 负向控制：前端是否实际调用正典预览

**问题：** `previewCreationCanon` 是否在当前前端向导流程中被调用？给出定义与真实调用证据。

**人工 ground truth：**

`frontend/src/api/studio.ts::previewCreationCanon` 已定义，后端 route/endpoint/service 也存在；但当前 `frontend/src/components/CreationStarWizard.tsx` 没有调用它。向导在 review 后直接调用 `studioApi.commitCreationSession`，而后端 commit 在 `canon_candidates` 为空时自行构建候选。源码搜索除 API 定义外不应找到 UI 调用者。

**易误判：** 因为 API wrapper 与路由存在，就推断 UI 已使用；把“可调用”当成“当前生产交互已调用”。

### Q05（关键）六席大纲议事与 SSE 调用方向

**问题：** 列出正式大纲议事的六个运行时席位，并给出前端发起流式阶段到服务编排器的方向。

**人工 ground truth：**

六席只来自 `backend/app/services/outline_debate_service.py::DEBATE_AGENTS`：

1. `outline_debate/StoryDirectorAgent`
2. `outline_debate/MarketPositionAgent`
3. `outline_debate/StructureDoctorAgent`
4. `outline_debate/CharacterGeneratorAgent`
5. `outline_debate/SettingGeneratorAgent`
6. `outline_debate/ContinuityAuditorAgent`

调用方向为 `OutlineStudioPage` → `OutlineDebatePanel::runActivePhase` → `frontend/src/api/studio.ts::streamOutlineDebatePhase` → `/{phase}/stream` route → `endpoints/outline_debate.py::stream_outline_debate_*` → FastAPI `StreamingResponse` → `OutlineDebateService.stream_phase` → `OutlineDebateOrchestrator`。服务动态选择下一席、构建 turn，随后综合 `decisions`、`artifacts`、`outline_topology` 与结构化 `result`，以 SSE 发回 `meta/turn/delta/decision/artifact/done` 等事件。

**易误判：** 把 11 个基础 AgentSpec、Prompt Catalog 文件或旧大纲实现算入六席；把正文图谱或 ECharts 组件当成议事拓扑的运行入口。

### Q06 大纲 confirm 与最终 commit 的不同写入

**问题：** `confirm_phase` 与 `commit_confirmed_candidates` 分别写什么，候选角色/设定何时物化？

**人工 ground truth：**

`OutlineDebateService.confirm_phase` 先执行质量门。总纲确认会标记候选，并通过 `_commit_confirmed_book_outline` 写 StoryBible、通过 `_ensure_planned_volume_shells` 建计划卷壳；卷纲/章纲走 `_confirm_itemized_phase`，逐条经 `_commit_outline_item_to_canon` 写 Volume 或 Chapter，并记录 CanonVersion。各阶段确认还会通过 `_materialize_phase_candidate_artifacts` 将可确认的 `character_candidate`、`setting_candidate` 物化为角色、实体或世界事实及其 CanonNode/CanonVersion。

全部阶段确认后，`commit_confirmed_candidates` 经 `_ensure_all_candidates_confirmed`，调用 `_write_book_outline_plan` 和 `_commit_chapter_outline_items` 汇总写正式 StoryBible、Volumes、Chapters；`formal_commit.writes` 明示三类写入，`graph_edges` 在该最终汇总步骤的 `excluded_writes` 中，候选正典物化被记录为 `pre_materialized_writes`。

**易误判：** 声称 confirm 只改会话状态且所有写入都延迟到最终 commit；或反过来声称最终 commit 才首次物化角色/设定；把 `excluded_writes=graph_edges` 误解成系统永远不维护图谱。

### Q07（关键）正文工作台生成首稿的异步调用链

**问题：** 从正文工作台点击生成到最终写入 Chapter 与候选正典，给出真实异步链和节点顺序。

**人工 ground truth：**

`frontend/src/pages/WorkspacePage.tsx::draftMutation` → `studioApi.draftChapter`（发送 `async_mode=true`）→ router 的 `project_studio.draft_chapter`（该符号从 legacy `endpoints/studio.py` 重导出）→ `endpoints/studio.py::draft_chapter` → `StudioService.draft_chapter` 创建 queued `GenerationJob` → FastAPI `BackgroundTasks.add_task(StudioService.run_draft_chapter_job)` → 新 `SessionLocal` → `_execute_draft_chapter` → `chapter_writing_service.stream_chapter_draft` → `agent_workflow.stream_chapter_draft`。

当前流式节点顺序是 `build_context → chapter_prep → chapter_card → scene_outline → plot_narrator → dialogue_writer → environment_writer → integrator → reviewer → fact_checker → draft_rewrite → quality_gate → [必要时 revise_draft] → style_unifier → post_length_review → narrative_ledger → canon_curator`。成功后 `_execute_draft_chapter` 更新 `Chapter.draft_text/final_text/summary/status/word_count`、保存 GenerationOutput/质量报告，并经 `_create_canon_update_proposals` 只创建待审批正典候选。

**易误判：** 漏掉 BackgroundTasks 与新数据库会话；把 `project_studio.py` 当成独立 endpoint 实现；把候选正典误报成已写正式设定。

### Q08 当前 HTTP 正文路径是否使用 `_compile_draft`

**问题：** 当前章节 HTTP 生成实际执行 `_compile_draft` 生成的 LangGraph，还是手工流式节点循环？质量门后的方向是什么？

**人工 ground truth：**

当前 HTTP 路径由 `_execute_draft_chapter` 调用 `ChapterWritingService.stream_chapter_draft`，后者委托 `AgentWorkflow.stream_chapter_draft`；该方法手工依次调用节点。`quality_gate.status == needs_revision` 且尚未达到 `max_revisions` 时执行一次 `revise_draft`，然后进入 `style_unifier` 等后续节点。`AgentWorkflow._compile_draft` 虽定义了 StateGraph 和条件边，但当前上述 HTTP 调用链没有调用它。

**易误判：** 图索引只看到 `_compile_draft` 的完整边就断言生产请求走该 compiled graph；把“类中存在”当成“当前 endpoint 可达”。

### Q09 `build_canon_context` 的输出契约与直接消费者

**问题：** `StudioService.build_canon_context` 返回哪些顶层字段，章节过滤如何工作，哪些服务直接调用它？

**人工 ground truth：**

返回外层 `{canon_context: ...}`，内层字段为 `project`、`story_bible`、`chapter`、`characters`、`world_facts`、`story_entities`、`graph`、`unresolved_continuity_issues`、`previous_summaries`。角色按重要度取 12，世界事实与实体各取 20，开放连续性问题取 20；有有效 chapter 时 previous summaries 只取较早章节并按章号倒序最多 5 条。`get_graph` 返回项目节点，并在有 chapter_id 时把边限制为来源章节等于该章或无来源。

直接调用点在 `studio_service.py`：`_execute_draft_chapter`、`stream_chapter_chat`、`foreshadowing`、`consistency_check`、`_generate_fast_batch_chapter`；另由 `endpoints/studio.py::get_canon_context` 暴露 GET API，再经 `endpoints/canon.py` 重导出和 router 挂载。

**易误判：** 把字段写成 `entities` 而不是 `story_entities`；声称 previous summaries 包含当前章；混入 `OutlineDebateService._canon_context` 的另一套独立契约。

### Q10（关键）批量生成任务的队列、事务、暂停和恢复

**问题：** 批量生成如何建 parent job、执行每章、暂停/取消、恢复/重试？当前 UI 默认走哪种正文分支？

**人工 ground truth：**

`StudioService.batch_generate` 校验范围及已存在且 `deleted_at is None` 的章节，立即创建 queued parent `GenerationJob`，初始化 `chapter_results/failed_chapters/skipped_chapters` 后放入进程内 `queue.Queue`；`_ensure_batch_worker` 启动 daemon thread，不依赖 Redis 或外部 worker。

`_run_batch_generate_job` 在 parent 初始化、每章准备、每章正文执行和结果记录时分别打开 `SessionLocal`；每章成功独立提交。`_prepare_batch_chapter` 与章后 `_record_batch_chapter_success` 实现章节边界检查：控制 API 会立即改变 parent 状态/标志，但正在运行的当前章允许完成，下一章前才停止；cancel 同理在边界生效。resume/retry 重新入队，`_completed_batch_chapter_numbers` 使已成功章节被跳过，失败时当前 run 停止，重试从失败或未完成章继续。

当前 `BatchPage` 显式发送 `{fast_draft: true, local_fast_draft: true, draft_mode: "local_fast_draft"}`，因此默认走 `_generate_fast_batch_chapter` 的本地快速正文分支；只有关闭 fast 选项时才复用完整 `draft_chapter` 工作流。

**易误判：** 把进程内线程说成分布式持久队列；声称暂停会中断当前模型调用；声称批量 API 自动创建缺失章节；仅看到备用分支就声称 UI 默认跑完整 Agent workflow。

### Q11（关键）章节生成后的正典候选审批方向

**问题：** 章节输出如何变成 `CanonChangeProposal`，approve 与 reject 对正式正典分别做什么？

**人工 ground truth：**

`_execute_draft_chapter` 在正文和质量门成功后调用 `_create_canon_update_proposals(result.canon_updates)`；该方法经 `_create_canon_proposal` 为 character/entity/world_fact/graph_edge/foreshadowing 的 create 或 update 建立 `CanonChangeProposal`，默认 `approval_status=pending`，此时不把这些候选写成正式设定。

前端 `SettingsWorkbenchPage::approveMutation/rejectMutation` → `studioApi.approveCanonProposal/rejectCanonProposal` → settings proposal routes → `endpoints/knowledge.py` 重导出的 legacy endpoint → `StudioService.approve_canon_proposal/reject_canon_proposal`。approve 根据 `create/update/archive/merge` 落正式实体，并创建或更新 CanonNode/CanonVersion（具体 create helper 内也同步正典），最后把 proposal 标为 `approved`；reject 只更新 proposal 为 `rejected`、记录原因与 `decided_at`，不写正式设定。

**易误判：** 把 `_create_canon_update_proposals` 与直接写入的 `_persist_canon_updates` 混为一谈；声称 reject 会删除正式实体；漏掉 approve 对版本与 CanonNode 的同步。

### Q12 大纲前端 SSE、确认、正式提交与缓存失效

**问题：** Outline 页如何消费 SSE，并在阶段完成、确认和正式提交后刷新哪些 React Query 数据？

**人工 ground truth：**

`OutlineDebatePanel::runActivePhase` 调用 `streamOutlineDebatePhase`；API helper 用 `fetch` 读取 SSE buffer，`emitJsonSseBlock` 派发事件，Panel 对 delta 追加文本、对 done 更新 session 并调用 `onPhaseComplete`。`confirmActivePhase/confirmAllActivePhase` 调用 `studioApi.confirmOutlineDebatePhase`；总纲确认调用 `onFormalCommit`，卷/章确认调用 `onPhaseComplete`。`commitConfirmedCandidates` 调用最终 commit 后调用 `onFormalCommit`。

这些回调由 `OutlineStudioPage` 提供，最终调用其 `invalidate`，失效 `['volumes', projectId]`、`['state', projectId]`、`['project-shell', projectId]`；正式提交还切换到 outline 视图并打开详情。Panel 自身不直接持有 QueryClient。

**易误判：** 声称每个 delta 都触发服务端查询刷新；漏掉父组件 callback；虚构 `project-chapters` 等并未由此 helper 直接失效的 key。

### Q13 设定工作台审批后的缓存影响

**问题：** 设定候选通过或驳回后，前后端调用方向及需要失效的 query key 是什么？

**人工 ground truth：**

方向为 `SettingsWorkbenchPage::approveMutation/rejectMutation` → `studioApi` → `/settings/proposals/{proposal_id}/approve|reject` → router → `endpoints/knowledge.py` 重导出 → legacy endpoint → `StudioService`。两种 mutation 成功后都调用 `invalidateWorkbench`，失效 10 个前缀：`settings-tree`、`canon-proposals`、`canon-versions`、`canon-version-timeline`、`canon-impact`、`characters`、`entities`、`world`、`graph`、`foreshadowing`（均以当前 projectId 开始匹配）。后端写入差异以 Q11 为准。

**易误判：** 只刷新 proposal 列表；把 reject 的 UI 全量缓存失效误解成 reject 也创建正式 CanonVersion。

### Q14 路由改名的影响范围

**问题：** 若仅把相对 HTTP 路径 `/write/batch-generate` 改名，哪些版本化源文件必须检查或修改，哪些同名符号通常不必因“仅改路径”而修改？

**人工 ground truth：**

必须检查/修改：

- `AGENTS.md`（API 合约和变更确认门）
- `README.md`
- `backend/app/api/v1/router.py`
- `frontend/src/api/studio.ts`
- `backend/app/services/studio_service.py` 中工作流 endpoint 元数据
- `backend/tests/test_core_apis.py`
- `backend/tests/test_acceptance_boundaries.py`

`backend/app/main.py` 的双前缀挂载不需因相对路径改名而改变，但新相对路径仍自动产生 `/api/...` 与 `/api/v1/...` 两条。若函数/语义不变，`writing.py` 的重导出、legacy endpoint 函数、`StudioService.batch_generate`、`BatchGenerateRequest`、`BatchPage` 调用的方法名和 CLI 直接服务调用不必仅因 URL 改名而重命名。`frontend/dist` 与 artifacts 是生成物或被排除数据，不应作为需手工维护的源文件。

**易误判：** 只找到 router 与前端；漏掉文档、工作流元数据和测试；建议直接编辑 `frontend/dist`；把 URL 改名错误扩大为所有 Python/TypeScript 符号改名。

### Q15 `build_canon_context` 契约变更的影响范围

**问题：** 若修改 `StudioService.build_canon_context` 的字段名或结构，列出直接、间接和不应误报的影响面。

**人工 ground truth：**

直接影响：`StudioService._execute_draft_chapter`、`stream_chapter_chat`/`_chapter_chat_prompts`、`foreshadowing`、`consistency_check`、`_generate_fast_batch_chapter`、`endpoints/studio.py::get_canon_context`，以及经 `endpoints/canon.py` 和 router 暴露的 `/projects/{project_id}/canon/context`。间接消费者包括 `backend/app/agents/chapter_writing/workflow.py` 对 `characters/world_facts/story_entities/previous_summaries` 等键的读取、`frontend/src/api/studio.ts::canonContext` 的返回契约、相关 schema/types、AGENTS/架构文档与 `backend/tests/test_core_apis.py` 的 previous summaries 测试。

当前没有页面调用 `studioApi.canonContext`，但公共 wrapper 仍属于兼容面。`OutlineDebateService._phase_context` 使用该服务自己的 `_canon_context`，字段中有 `entities/foreshadowing_items/creation_seed/...`，不是 `StudioService.build_canon_context` 的直接调用者；仅改后者时不应把整条大纲链误报为直接依赖。Deep Agent 的 `read_canon_context` 当前只是工具调用记录名称，也不是这里的直接函数调用。

**易误判：** 全局按字符串 `canon_context` 把两套构造器合并；漏掉 prompt/node 对具体键的消费；把未被页面调用的 API wrapper 误报为活跃 UI 调用。

## 4. MCP 实际查询记录

查询通过 `scripts/code-intel.sh query` 调用与 MCP 服务相同的九个只读 tool handler；另行完成 stdio MCP JSON-RPC 握手、分页 `tools/list` 和 `codex mcp get codebase_memory` 白名单验证。评分依据是九个允许工具的组合能否恢复正确结论，不把单条原始边当成事实。全程未调用 `index_repository`、`delete_project`、`manage_adr`、`ingest_traces`、rename、写 Cypher 或文件写入型 MCP 工具。

| 题号 | 使用的只读工具与查询摘要 | MCP 返回摘要 | 源码复核证据 | 得分（0/1/2） | 方向错误 | 状态/备注 |
|---|---|---|---|---:|---|---|
| Q01 | `search_graph` + `query_graph` + snippets；批量前端到服务与双前缀 | 组合结果恢复 UI → wrapper → route → facade → service，以及 `/api`/`/api/v1` | `BatchPage.tsx`、`studio.ts`、`router.py`、`writing.py`、`studio.py`、`studio_service.py`、`main.py` | 2 | 否 | 原始图漏 endpoint→service 和完整 `/api/v1` Route |
| Q02 | 会话 route、service、model 图搜索与 snippets | 恢复项目基础字段更新和 `CreationSession` 持久化层 | `CreationStarWizard.tsx`、`studio.ts`、`agents.py`、`studio.py`、`studio_service.py`、`models.py` | 2 | 否 | `db.commit()` 和局部 `project` 出现同名误边 |
| Q03 | 抽卡运行时、质量门、preview/commit 查询 | 恢复专用运行时、四种 Agent 职责、压测门和正典写入边界 | `studio_service.py`、`CreationStarWizard.tsx`、`models.py` | 2 | 否 | 同名 `commit` 误边未用于结论 |
| Q04 | `previewCreationCanon` 定义及调用者负向查询 | 确认 API 存在，当前 UI 无调用，向导直接 commit | `studio.ts`、`CreationStarWizard.tsx`、后端 route/service | 2 | 否 | 过滤了 wrapper 的假自调用 |
| Q05 | 六席常量、SSE wrapper、route 与 service snippets | 恢复六个运行时席位及 Panel → SSE → endpoint → service 方向 | `outline_debate_service.py`、`OutlineDebatePanel.tsx`、`studio.ts`、`outline_debate.py` | 2 | 否 | 动态 URL 无结构化 data-flow，snippet 补齐 |
| Q06 | confirm/commit 直接调用与 materializer snippets | 恢复阶段质量门、逐项写入和最终汇总的时机 | `outline_debate_service.py:1240`、`:1914`、`:2637` 附近 | 2 | 否 | `db.commit()` 假连 Creation Star `commit` |
| Q07 | HTTP、DATA_FLOWS、IMPORTS、CALLS 与全链 snippets | 恢复 async job、新 session、写作 workflow、质量门和 pending proposal | `WorkspacePage.tsx`、`studio.ts`、`project_studio.py`、`studio.py`、`studio_service.py`、`workflow.py` | 2 | 否 | 漏 callback/endpoint/yield-from 边，有假自环 |
| Q08 | `_compile_draft` caller 负向查询与两层 stream snippets | 确认当前 HTTP 路径手工串流节点，`_compile_draft` 生产不可达 | `chapter_writing/service.py`、`workflow.py:1227`、`:1287` 附近 | 2 | 否 | `yield from` CALLS 漏边，snippet 恢复 |
| Q09 | `build_canon_context` 定义、callers、route/import 查询 | 恢复九字段、数量限制、图边筛选与生产调用者 | `studio_service.py:3569`、`:3778`、`:3833`、`:4320`；`canon.py`、`router.py` | 2 | 否 | 无影响结论的解析错误 |
| Q10 | batch worker/control/retry/success 查询与 UI snippet | 恢复进程内队列、逐章独立 session/提交、边界控制、跳过成功章 | `studio_service.py:318`、`:1388`、`:3866`、`:4498` 附近；`BatchPage.tsx` | 2 | 否 | `.get/.put/.first/commit` 同名误边 |
| Q11 | proposal 生成、approve/reject、route/UI 查询 | 恢复 pending 候选；approve 物化并同步版本；reject 只记录决策 | `studio_service.py:1192`、`:2645`、`:7824` 附近；`models.py`、`SettingsWorkbenchPage.tsx` | 2 | 否 | 漏内嵌 helper 和 endpoint→service；WRITES 误边 |
| Q12 | Panel SSE/confirm/commit snippets 与父组件 callback | 恢复 delta/done 处理、两类回调和三组 Query 失效 | `OutlineDebatePanel.tsx:434`、`:553`；`studio.ts:580`；`OutlineStudioPage.tsx` | 2 | 否 | React 运行时 callback 无直接图边 |
| Q13 | approve/reject HTTP_CALLS 与完整页面 snippet | 恢复前后端方向和两类 mutation 共用的 10 个 query key | `SettingsWorkbenchPage.tsx:555`、`:580`；`studio.ts:919`；`knowledge.py`、`studio.py` | 2 | 否 | 匿名 `mutationFn/onSuccess` qualified name 合并 |
| Q14 | URL 字面量 `search_code` + 符号/route 查询 | 精确找到 7 个必查版本化文件，未扩大为同名符号重命名 | AGENTS、README、router、service metadata、前端 API、两个测试 | 2 | 否 | 合成 Route 重复，不影响文件级影响分析 |
| Q15 | qualified-name callers + 具体字段 `search_code` | 区分直接/间接消费者，并排除 OutlineDebate 另一套 context 和 Deep Agent 名称 | `studio_service.py`、`workflow.py`、`canon.py`、`studio.ts`、`outline_debate_service.py` | 2 | 否 | 重导出无普通 CALLS，IMPORTS/snippet 补齐 |

### 4.1 评分汇总

| 项目 | 结果 |
|---|---|
| 总分 | **30 / 30** |
| 是否达到 24 分 | 是 |
| Q01/Q03/Q05/Q07/Q10/Q11 是否存在方向错误 | 否 |
| 图谱解析错误或无法解析项 | 原始 CALLS 会漏 instance method、endpoint→service、内嵌 callback、`yield from` 和 React callback；动态 URL 常缺 data-flow；同名 `commit/first/get/put/list` 及局部 `project/version/output` 会产生假边；匿名 TS callback 可能折叠 qualified name；变量 snippet 的结束行有时过长；第二个 `/api/v1` 前缀未物化为完整 Route 节点。 |
| 最终代码图谱结论 | **通过只读试点**；结论依赖图搜索、文本搜索、snippet 和源码复核的组合，不允许单独信任原始边。 |

## 5. Repomix 实际统计

| 字段 | 实际值 |
|---|---|
| Repomix 版本 | `1.17.0`；npm integrity 与仓库锁定值一致 |
| 执行命令/脚本 | `./scripts/build-ai-context.sh` |
| 生成时间 | `2026-07-22 09:49:25 +0800` |
| 输出文件（应位于 `.ai-context/`） | `.ai-context/repomix.xml` |
| 包含文件数 | 297 |
| 字符数 | 3,090,756 |
| Repomix 报告 token 数或估算 token 数 | 935,877（Repomix `o200k_base` 报告） |
| 输出字节数 | 3,320,924 |
| 输出是否被 Git 跟踪 | 否；`git ls-files -- .ai-context` 为空 |
| 是否启用外部 processor/远程上传 | 否；`input.processors=[]`，只生成本地 XML |
| 最终 Repomix 结论 | **通过**；固定版本生成成功，安全检查无可疑文件，路径扫描无敏感生成数据 |

### 5.1 敏感路径排除矩阵

“输出命中数”必须通过实际扫描生成快照得到，不能只引用 `.gitignore` 或 Repomix 自报配置。

| 路径或模式 | 输出命中数 | 排除结果 | 证据/备注 |
|---|---:|---|---|
| `.env`、`.env.*`、密钥形态 | 0 | 通过 | 文件路径为 0；另扫描 OpenAI-like、GitHub PAT、AWS access key 和 private-key header，均为 0 |
| `*.db`、`*.sqlite`、`*.sqlite3` | 0 | 通过 | 包含 sidecar 形式的路径检查 |
| `data/` | 0 | 通过 | 路径扫描 |
| `backend/data/` | 0 | 通过 | 路径扫描 |
| `backend/artifacts/` | 0 | 通过 | 路径扫描 |
| `output/`、`outputs/` | 0 | 通过 | 路径扫描 |
| `logs/`、`.logs/` | 0 | 通过 | 路径扫描 |
| `test-artifacts/` | 0 | 通过 | 路径扫描 |
| `frontend/node_modules/` | 0 | 通过 | 路径扫描 |
| `frontend/dist/` | 0 | 通过 | 路径扫描 |
| `.git/` | 0 | 通过 | 路径扫描 |
| `.codebase-memory/` | 0 | 通过 | 路径扫描 |
| `.ai-context/`（防止递归打包） | 0 | 通过 | 路径扫描 |
| 小说正文、备份与本地导出内容抽查 | 0 | 通过 | `backups/`、`exports/` 及 EPUB/Word/PDF/archive 路径为 0；仅保留版本化示例种子 |

历史 `docs/archive/`、`docs/superpowers/`、`docs/test-reports/` 和报告型 Markdown 也均为 0。首轮快照曾包含真实 LLM 测试报告，随后收紧三层排除规则并覆盖重建；最终统计只针对重建后的快照。

## 6. 生成数据与 Git 边界

| 检查 | 预期 | 实际结果 | 状态 |
|---|---|---|---|
| codebase-memory 供应链 | 固定版本、校验和许可文件 | `0.9.0` macOS arm64 发布包 SHA-256 `faa02f…ed4`；安装二进制 SHA-256 `d9fbdd…8d6`；`LICENSE` 与 `THIRD_PARTY_NOTICES.md` 存在 | 通过 |
| Repomix 供应链 | 固定版本与 npm integrity | `1.17.0`；registry integrity `sha512-W5vc…ohw==` 与受控脚本锁定值一致，install scripts 已禁用 | 通过 |
| `.codebase-memory/` 被 `.gitignore` 排除 | 是 | `git check-ignore -v` 命中 `.gitignore` | 通过 |
| `.ai-context/` 被 `.gitignore` 排除 | 是 | `git check-ignore -v` 命中 `.gitignore` | 通过 |
| `git ls-files` 不含两类生成物 | 是 | 两个目录查询结果均为空 | 通过 |
| codebase-memory 缓存仅限当前仓库 | 是 | 缓存只有 `_config.db` 与当前绝对路径派生的单项目 DB；`index_status.root_path` 等于仓库根 | 通过 |
| auto index 与 watcher 关闭 | 是 | `_config.db` 中 `auto_index=false`、`auto_watch=false` | 通过 |
| Codex MCP 只暴露批准的只读工具 | 是 | 原生服务分页列出 14 个工具；`codex mcp get codebase_memory` 的 `enabled_tools` 精确为批准的 9 个 | 通过 |
| DeepWiki 仓库内缓存 | 不存在 | 未克隆、未安装、未运行；`.deepwiki/` 仅作防御性忽略 | 通过；DeepWiki 未启用 |

首轮可重建图缓存曾包含后来被排除的历史报告；在收紧规则后，旧 `.codebase-memory/` 先移入废纸篓，待新索引验证通过后已永久删除。该对象只是可重建的工具索引，不含产品 SQLite 数据或用户稿件，现已不可恢复。

## 7. 验证与回归结果

| 命令或检查 | 结果摘要 | 状态 |
|---|---|---|
| `scripts/verify-ai-context.sh --full` | 静态配置、Git 边界、基线只读查询和 Repomix 路径/密钥形态扫描全部 OK | 通过 |
| `scripts/code-intel.sh status` | `ready`；3,744 nodes / 15,712 edges；root path 为当前仓库 | 通过 |
| 15 题只读图谱抽查 | 30/30；Q01/Q03/Q05/Q07/Q10/Q11 六道关键题均无方向错误；所有误边/漏边已记录 | 通过 |
| 并发只读查询压力测试 | 20 并发、共 40 次 `status`；40/40 成功，stderr 为 0，无残留配置锁 | 通过 |
| 越界与写入负向测试 | 非白名单 `list_projects`、跨仓库 `project` 覆盖、写 Cypher `CREATE` 均被受控 CLI 入口拒绝；原生 `query_graph` 仅支持只读 Cypher 子集 | 通过 |
| `scripts/build-ai-context.sh` | Repomix 1.17.0，297 files / 935,877 tokens，内置 security check 通过 | 通过 |
| Repomix 敏感路径内容扫描 | 14 类路径/扩展与 4 类常见密钥形态均为 0 | 通过 |
| `git check-ignore` / `git ls-files` 生成物检查 | 两目录已忽略且无 tracked 文件 | 通过 |
| `python -m pytest backend/tests -q` | 仓库外临时 Python 3.12.13 venv：165 passed，1 个第三方 Starlette/httpx 弃用警告，189.75s | 通过 |
| `cd frontend && pnpm test` | 41/41 passed；当前 Node 26 与锁定 Node 24.14.0 有 engine warning | 通过 |
| `cd frontend && pnpm build` | TypeScript 与 Vite 构建成功；有 511.83 kB chunk size 提示 | 通过 |
| `docker compose config --quiet` | 退出码 0，无诊断；默认仍只有 backend/frontend | 通过 |

## 8. 最终判定

- 代码图谱准确率门：**通过**，30/30 且关键题无方向错误。
- Repomix 排除与规模门：**通过**，敏感路径和密钥形态扫描为 0，规模已记录。
- 生成数据/Git 边界：**通过**，索引和快照均未跟踪，索引根未越界。
- 产品默认测试、构建与 Compose：**通过**，无新增产品运行时依赖或默认服务。
- DeepWiki：未启用，不属于本轮通过条件。
- 最终结论：**codebase-memory-mcp 只读试点、Markdown ADR + Mermaid 和 Repomix 前三阶段验收通过**。图谱是定位辅助层，已知误边/漏边决定了它不能替代源码、测试和人工架构决策。
