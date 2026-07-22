# 叙界推演引擎 / Narraverse Engine 项目规范

> 本文件是项目级规则入口。根规则与适用的作用域 `AGENTS.md` 共同构成当前开发约束；历史归档、自动图谱、上下文快照和 Wiki 不能替代这组规则。

## GLOBAL-DISCOVERY-001：分层规则与渐进加载

Codex 在一次运行开始时按“项目根目录到当前工作目录”发现规则，不会因为稍后打开某个子目录文件而自动重新加载。因此，本项目采用“根基线 + 目录作用域 + 显式路由”的混合模式：

| 目标路径或工作类型 | 必须额外完整读取 | 规则所有权 |
|---|---|---|
| `backend/**`、根 `requirements.txt`、后端 Dockerfile | `backend/AGENTS.md` | Python、FastAPI、Agent 工作流、API、数据、LLM、后端测试 |
| `frontend/**`、前端 Dockerfile | `frontend/AGENTS.md` | React 工作室、交互审批边界、前端依赖与测试 |
| `scripts/**`、`.codex/**`、`.gitignore`、`.cbmignore`、`.repomixignore`、`repomix.config.json`、`docker-compose.yml`、`.github/workflows/**` | `scripts/AGENTS.md` | 启动部署、开发工具、AI 上下文工具、CI 与生成数据 |
| `docs/**`、`README.md`、`CONTRIBUTING.md` | `docs/AGENTS.md` | 文档事实层、ADR、Mermaid、历史资料和同步规则 |

执行要求：

- 从仓库根目录启动的 Agent，在读取、修改或验证上述路径前，必须主动读取对应作用域文件；跨目录任务必须读取所有相关文件。
- 从子目录启动时，Codex 会合并根规则和路径上的作用域规则；作用域规则只能细化，不能削弱本文件的版本、安全、人工审批、非目标或变更确认门。
- 同一规则只保留一个所有者，其他文档用稳定规则 ID 引用，不复制一份可独立演化的强制正文。
- 若规则冲突，优先顺序为：用户当前明确指令 > 根级全局规则 > 最接近目标文件的作用域规则 > README、架构说明等同步摘要。无法按此顺序消解时必须停止并请求确认。
- 新增作用域规则文件时，必须同时更新本路由表、`scripts/verify-agents-guidance.py` 和 ADR。

## GLOBAL-STATUS-001：文档与版本状态

- 规范版本：2026.07.22
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

## GLOBAL-PRODUCT-001：当前产品边界

叙界推演引擎是本地优先的多模型长篇小说创作工作室，不是 SaaS。默认部署不得要求登录、云端数据库或公网服务，必须能在普通用户本机运行。

当前能力包括：

- FastAPI 后端、React + TypeScript Web 前端、Python CLI 和 SQLite 本地数据库。
- 统一 LLM Client、OpenAI 兼容供应商与无密钥本地 fallback。
- 创作 Star 分步立项、回合制大纲议事、章节正文和批量生成。
- 正典、角色、实体、世界观事实、关系图谱、伏笔和连续性问题。
- Agent 轨迹、任务、版本快照、diff、回滚和分支探索。
- 本地导出、备份、恢复、已有小说导入、Method Pack、对标资产和审稿计划。
- Deep Agent 与 LangSmith 的可选管理能力。

当前功能定位：

| 模块 | 当前定位 |
|---|---|
| 创作 Star | 唯一前台立项入口；候选经用户确认后才写入项目和正典。 |
| 大纲议事 | 唯一正式大纲入口；按 `book`、`volumes`、`chapters` 实时讨论、确认和提交。 |
| 正文工作台 | 项目级三栏写作环境，支持编辑、AI 协作、修改提案、自动保存、版本和字数统计。 |
| 设定工作台 | 统一正典文件树，管理实体、事实、图谱、伏笔、候选变更、锁定字段和版本轴。 |
| 批量生成 | 基于正式章节的异步任务队列，支持暂停、恢复、取消、重试和失败追踪。 |
| 写作资料 | 导入报告、Method Pack、对标资产和审稿计划只作为参考上下文，不直接覆盖正文或正典。 |
| Agent 配置 | 展示基础 AgentSpec、大纲议事运行时席位、提示词、工作流和人工模型覆盖。 |
| Deep Agent / LangSmith | 可选总管与观测层；默认关闭写入，不能绕过既有工作流和审批。 |
| 导出 / CLI | 本地导出与脚本化项目、章节、版本、正典和作品操作。 |

## GLOBAL-RELEASE-001：发布与跨层不变量

只有满足以下条件后，才允许进入 `1.0.0 Stable`：

- README 能让 Windows、macOS、Linux 用户在 10 分钟内完成 Docker 快速启动。
- 默认测试和构建在干净环境中通过。
- 创作 Star、大纲议事、正文生成、正典审批、批量任务、版本和导出至少有一条完整本地验收链路。
- 默认配置不依赖 Qdrant、Redis、Postgres、云数据库或公网服务。
- API Key 只由后端读取，前端不接触任何密钥。
- 所有 AI 写入正文、设定和伏笔的路径都保留用户确认或审批边界。

跨层不变量：

- 实际依赖以 `backend/requirements.txt`、`frontend/package.json`、`frontend/pnpm-lock.yaml` 和 `docker-compose.yml` 为准；根 `requirements.txt` 若保留，必须与后端依赖同步。
- 后端同时提供 `/api` 和 `/api/v1`；双前缀是当前合约，前端默认使用 `http://localhost:8000/api`。
- SQLite 是默认数据库；Qdrant 只能是可选记忆增强。
- AI 输出默认是候选、提案或预览；正式正文、正典和伏笔更新必须经过对应审批边界。
- 不得在根规则、作用域规则、README、Dockerfile、package manifest 和 requirements 之间维护冲突的版本或能力描述。

## GLOBAL-CHANGE-GATE-001：变更确认门

任何新增功能、生产或开发依赖、活跃目录、公共接口、数据表或部署方式，必须在实现前：

1. 更新本根规则或拥有该事项的作用域规则；如果作用域或加载路径变化，同时更新根路由。
2. 更新必要的 README、CONTRIBUTING、架构文档、ADR 和验证证据。
3. 获得用户明确确认后再实施。

用户已经明确授权的当前分批整改按已确认范围推进，不需要为同一批中的普通实现步骤重复确认；若引入未在建议中出现的新系统、外部服务、产品能力或破坏性迁移，仍需重新确认。

## GLOBAL-SAFETY-001：作者控制权与密钥

- API Key 只能来自后端环境变量；前端不得读取、保存、转发或直接调用 LLM Key。
- 用户手写正文、设定和正典不得被 AI 无来源、无置信度、无原因地覆盖。
- AI 编辑遵循“生成提案 → 展示差异 → 用户确认 → 应用前快照 → 写入”。
- 正典更新遵循“候选变更 → 用户审批 → 写入设定集”。
- 真实 LLM、远程追踪或会发送源码/小说内容的工具必须显式启用；默认测试不得依赖真实 API Key。

## GLOBAL-NON-GOALS-001：当前非目标

当前阶段不做：

1. 用户登录、权限、组织空间或云端多人协作。
2. 支付、订阅、额度、账单或商业授权系统。
3. 在线发布平台、自动投稿或平台账号托管。
4. 默认引入 Neo4j、Postgres、Redis 或复杂向量数据库作为核心依赖。
5. 移动端原生 App、Electron 桌面端、浏览器插件或系统托盘后台守护。
6. 本地模型训练、微调平台或多模型自动路由优化。
7. 前端直接读取或调用 LLM API Key。
8. AI 无审批覆盖用户手写设定或正文。
9. 一键无人值守自动写完整本书并自动定稿。

PDF、EPUB、Word 等本地导出已经属于当前能力，只能说明排版质量阶段，不得重新列为“完全不做”。

## GLOBAL-VERIFY-001：默认验证

默认完整验证命令：

```bash
python3 scripts/verify-agents-guidance.py
python3 -m pytest backend/tests -q
cd frontend
pnpm test
pnpm build
cd ..
docker compose config --quiet
```

按变更范围先运行作用域文件规定的最小测试，交付前再按风险决定是否运行完整验证。真实 LLM 验收必须显式设置 `LLM_REQUIRE_REMOTE=true` 和 `RUN_REAL_LLM_CONTRACTS=true`，且报告 Provider、模型、日期、输入规模和输出风险。

## GLOBAL-DOCS-001：事实层与文档同步

- 根规则与适用的作用域规则是项目约束入口；源码、测试和正式 API schema 是实现事实，人工审阅的 ADR / Mermaid 记录稳定设计意图。
- README、CONTRIBUTING、架构说明和 Prompt Catalog 文档是面向人的同步摘要，不能覆盖规则或源码事实。
- 代码图谱、Repomix 输出和任何自动 Wiki 只是检索或解释层，不能自动创建规则或 ADR。
- 文档不得把目标能力集写成当前版本，不得混合冲突的 MVP/Studio 1.0 约束，不得描述已删除入口，不得把可选服务写成默认依赖，也不得把真实 LLM 手动验收写成默认测试。
- DeepWiki Open 仍明确为“暂不启用”；不得克隆、安装、运行或生成 Wiki 缓存。AI 上下文工具的完整边界归 `TOOLING-AI-CONTEXT-001` 所有。

## GLOBAL-HISTORY-001：历史规格

2026-07-04 前的长版根规则归档于 `docs/archive/legacy-agents-before-2026-07-04-cleanup.md`。归档、`docs/superpowers/` 和既有测试报告只用于追溯当时决策，不属于当前活跃规则；与当前规则冲突时，以当前根基线和适用作用域规则为准。
