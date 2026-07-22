# 运维、脚本与开发工具作用域规范

> 适用于 `scripts/**`，并由根路由扩展到 `.codex/**`、AI 工具 ignore/config、`docker-compose.yml` 和 `.github/workflows/**`。本文件不能放宽根级产品、安全和确认边界。

## OPS-DEPLOY-001：部署边界

README 是普通用户部署入口，必须保持可执行、跨系统和低门槛。

必须支持：

- Windows 10/11 + Docker Desktop。
- macOS + Docker Desktop。
- Linux + Docker Engine / Docker Compose v2。
- 本地源码启动：Python 3.10+、Node.js 24.14.0、pnpm 11.5.1。

默认 Docker Compose 只启动：

- backend
- frontend

不得要求普通用户额外启动 Qdrant、Redis、Postgres 或其他服务。新增可选服务必须标为“可选增强”，说明核心流程的降级路径，并先通过 `GLOBAL-CHANGE-GATE-001`。

## OPS-STARTUP-001：本地启动入口

- 后端：`scripts/dev-backend.sh`
- 前端：`scripts/dev-frontend.sh`
- 一键本地启动：`scripts/dev.sh`
- 前端默认 API：`http://localhost:8000/api`
- Docker 模式修改 `VITE_*` 后必须重建前端镜像。

启动脚本不得把 API Key 注入前端，不得把可选 AI 开发工具变成产品启动前置条件。

## OPS-GENERATED-DATA-001：不得提交的数据

以下路径是本地数据、密钥或可重建生成物，不得提交：

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
- `.codebase-memory/`
- `.ai-context/`

`.env.example` 是版本化配置模板，不得被 Git 忽略；其中只能包含空值或已审阅占位符，不能包含真实凭据。

## TOOLING-AI-CONTEXT-001：AI 项目上下文工具链

AI 辅助开发工具只属于可选开发期增强，不属于产品运行时、默认 Docker、后端依赖、前端依赖或小说业务能力。当前顺序与状态：

```text
codebase-memory-mcp 服务端只读代理（已接入）
  -> Markdown ADR 与 Mermaid（已接入）
  -> Repomix 可移植快照（已接入）
  -> DeepWiki Open（暂不启用）
```

| 工具 | 锁定版本 | 许可和状态 |
|---|---:|---|
| codebase-memory-mcp | 0.9.0 | MIT；固定八工具代理、独立输入代际与完整性合同已验收 |
| Repomix | 1.17.0 | MIT；锁文件运行时、不可变输入与文件集等值验证 |
| Mermaid | 不新增运行时包 | 只使用人工审阅的 Markdown 文本图源 |
| DeepWiki Open | `88a47bf9277d52026b1f05f869c3ff622331cc8b` | MIT 候选提交；未启用 |

工具定位：

- `codebase-memory-mcp` 是本地代码结构索引器；只允许采用主项目 MIT 版本并锁定版本，保留分发包第三方许可证与 notices。
- Mermaid 不增加前端包，生成图片不是架构源。
- ADR 保存人工确认的决策；图谱、快照或 Wiki 推断不得直接创建或接受 ADR。
- Repomix 只生成按需、可删除的上下文快照，不加入产品 package manifest 或 requirements。
- DeepWiki Open 只可能成为仓库外缓存的可选本地 Wiki，不能进入默认 Compose、核心启动或事实层。
- Backstage、Graphiti、Neo4j、FalkorDB 和其他外部图数据库当前不接入。

### 当前版本化边界

这套能力当前允许维护：

- `.codex/config.toml`
- `.cbmignore`
- `.repomixignore`
- `repomix.config.json`
- `scripts/code-intel.sh`
- `scripts/code-intel-mcp-proxy.py`
- `scripts/code-intel-native.py`
- `scripts/code-intel-validate.py`
- `scripts/ai_tool_subprocess.py`
- `scripts/run-bounded-ai-tool.py`
- `scripts/verify-ai-tool-supply-chain.py`
- `scripts/ai-context-inputs.py`
- `scripts/ai-context-profiles.json`
- `scripts/ai-context-eval.json`
- `scripts/evaluate-ai-context.py`
- `scripts/evaluate-code-graph.py`
- `scripts/build-ai-context.sh`
- `scripts/verify-ai-context.sh`
- `scripts/verify-agents-guidance.py`
- `scripts/repomix-runtime/**`
- `scripts/tests/**`
- 根与作用域 `AGENTS.md`
- `docs/ai-assisted-development.md`
- `docs/adr/**`
- `docs/architecture.md`
- `docs/test-reports/**`
- `.gitignore`、`README.md`、`CONTRIBUTING.md` 和相关 CI workflow

不得借此修改产品 API、数据表、前端页面、默认 Compose 服务或产品运行时依赖。

### 生成数据、隐私和权限

- `.codebase-memory/` 与 `.ai-context/` 是可重建敏感数据，必须被 Git 忽略，不得提交。
- DeepWiki 的克隆、向量索引、缓存和输出必须位于仓库外；在用户再次明确启用前不得创建。
- 代码图谱必须使用当前仓库独立缓存并限制根目录。索引和刷新只能通过 `scripts/code-intel.sh` 显式执行；MCP 会话不得自动创建、删除或刷新索引，watcher 默认关闭。
- 服务端代理是模型权限边界，只暴露 `search_graph`、`query_graph`、`trace_path`、`get_code_snippet`、`get_graph_schema`、`get_architecture`、`search_code`、`index_status` 八个只读工具。`project` 由代理注入，`detect_changes`、索引、删除、ADR 写入、跨仓库路径、shell、文件写入和写 Cypher 必须在调用原生二进制前拒绝。客户端 `enabled_tools` 只是纵深防御。
- 输入成员资格来自 Git index 中已提交或 staged-added 的普通文件，内容使用当前 worktree 字节。untracked 默认拒绝，仅允许精确 `--allow-untracked PATH`；deny 永远优先。同一安全 fd 必须同时完成密钥扫描和内容认证；symlink、gitlink、非普通文件、多硬链接文件和 unmerged index 必须失败关闭。受控目录须归当前 UID、owner-only；快照/代际/锁用 `0700`，不可变 shadow 目录用 `0500`。
- 图谱只能索引 `.codebase-memory/inputs/<inventory_sha>/files` 的 owner-only 独立只读副本，不得使用硬链接。流程为“生成副本 -> 索引 -> 复验 manifest -> 验证图路径为 manifest 的非空、未截断子集 -> 原子替换 `current-input.json`”。只能称“指针原子激活”，不得声称图数据库事务化。
- 每次 MCP 查询前后都必须完整复验活跃输入与仓库固定的原生二进制 SHA/身份；前验失败不调用 native，后验失败不返回结果。请求、超时、stdout、stderr 和最终结果都必须有硬上限。受控锁必须用 PID/token、inode 复验和原子 owner 发布，对正常释放/stale 清理竞争重试；索引/runtime 锁及安装卸载必须可恢复。正式安装发布和卸载 tombstone 均先在受控 parent 内原子 rename。
- Repomix 必须从同一已验证 manifest 物化的不可变独立副本读取，通过 stdin 传入精确路径，并验证输出文件集与 manifest 完全相等。package/lock/config 先复制到私有构建目录，专用 lockfile、`npm ci --ignore-scripts`、最小环境和有界 runner 缺一不可。bundle ID 必须认证 snapshot SHA；`.publication.lock` 必须从 build rename 前持有到 links/current 完成，retention/quarantine 的可失败操作先于 `current.json` 激活，最多保留当前与前一 bundle。
- Repomix 支持 `full`、`backend`、`frontend`、`tooling` 四个 profile；profile 只能缩小已批准 manifest，不能绕过 deny，也不影响代码图谱。
- 工具不得索引或打包 `.env`、SQLite 数据库、用户小说数据、导出、备份、日志、测试产物、密钥、`data/`、`backend/data/`、`backend/artifacts/`、`output/`、`outputs/`、`logs/`、`.logs/`、`test-artifacts/`、`frontend/node_modules/`、`frontend/dist/`、`.git/`、`.codebase-memory/`、`.ai-context/` 及文档历史/测试报告目录。
- 图谱、快照和自动 Wiki 均按潜在敏感源码处理，不得默认上传公网或远程模型。远程调用必须由用户显式启用，Key 只能来自环境变量。当前脚本不是 OS 级网络/文件沙箱；需要敌对二进制隔离时必须由宿主提供。
- 不允许未经审阅的 `curl | sh`、`irm | iex` 或自动修改个人客户端配置的安装流程。
- 外部工具升级必须锁定明确版本、校验和与许可证，独立审阅并重新执行排除和准确率验收；不得约定浮动 `latest`。

### 事实源与验收

- 当前任务适用的根/作用域规则、源码、测试和正式 API schema 是事实源；人工 ADR/Mermaid 记录设计；图谱、快照和 Wiki 只是检索层。
- 图谱准确率验收固定九场景且每场景恰一条真实检索，至少覆盖 Python、TypeScript、双 API 前缀、三条 Agent 线、批量任务和正典审批；场景集合不可静默删减，并须与源码和 `rg` 逐项比对。
- Repomix 验收必须证明敏感路径未进入输出、输出目录未被跟踪，并记录文件数和 token/字符规模。
- `verify-ai-context.sh --static` 必须离线执行合同单测、profile 选择和场景锚点 smoke；它不证明真实图谱的 hit@k、边方向或 snippet 准确性。真实生成、MCP handshake、manifest、权限与保留策略由 `--full` 验收。
- AI 工具缺失时，产品测试、构建和 Docker 快速启动仍必须通过。
- DeepWiki 只有在当前三阶段通过且用户再次明确启用后才可运行；目前仍不得克隆、安装或生成缓存。

## OPS-GUIDANCE-001：分层规则验证

`scripts/verify-agents-guidance.py` 是分层规则的静态合同。它必须：

- 模拟 Codex 从 Git 根到目标 cwd 的发现顺序。
- 拒绝未登记的 `AGENTS.md`、任何 `AGENTS.override.md` 和孤儿规则。
- 验证根路由覆盖所有作用域文件。
- 验证稳定规则 ID 全局唯一。
- 在不依赖项目被信任的情况下，保证每条有效 instruction chain 不超过默认 32 KiB 的安全预算。
- 验证 `.codex/config.toml` 提供显式容量兜底，但不得用放大上限掩盖臃肿规则。

默认静态模式供 CI 使用；本机安装 Codex 时可运行 `python3 scripts/verify-agents-guidance.py --runtime`，直接比较 Codex 实际加载的 instruction chain，证明没有漏载或截断。该 debug smoke 不作为普通 CI 的 Codex 依赖。

规则结构变化必须先更新根路由、该验证器和对应 ADR。

## OPS-CI-001：CI 与脚本验证

CI 至少执行不需要第三方 AI 二进制或真实 LLM 的规则静态检查。脚本修改按范围运行：

```bash
python3 scripts/verify-agents-guidance.py
bash -n scripts/*.sh
./scripts/verify-ai-context.sh --static
docker compose config --quiet
```

`verify-ai-context.sh --full`、真实图谱构建和 Repomix 完整生成可放在手动或定时验收，不得把外部工具变成普通产品 CI 的必需运行时。验证脚本自身的策略变化必须与受保护规则和测试同步审阅。
