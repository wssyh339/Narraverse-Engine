# AI 辅助开发上下文

本文说明叙界推演引擎的本地代码智能和可移植上下文工具。它们只服务开发者与 AI coding 客户端，不属于产品运行时、默认 Docker 部署、后端或前端依赖，也不能替代源码、测试、正式 API schema、当前任务适用的分层 `AGENTS.md` 规则链和人工审阅的架构决策。强制边界由 `scripts/AGENTS.md` 的 `TOOLING-AI-CONTEXT-001` 所有，本文只提供操作、验证与故障处理说明。

## 当前状态

| 阶段 | 工具 | 锁定版本 | 当前状态 |
|---|---|---:|---|
| 1 | codebase-memory-mcp | `0.9.0` | 已接入；固定八工具服务端代理、独立输入代际、受控并发锁，以及查询前后输入与原生二进制完整性复验。 |
| 2 | Markdown ADR + Mermaid | 不新增运行时包 | 已接入；由人维护和审阅。 |
| 3 | Repomix | `1.17.0` | 已接入；170 包依赖闭包、独立只读输入、manifest 文件集等值验证和带 provenance 的快照 bundle。 |
| 4 | DeepWiki Open | 候选提交 `88a47bf9277d52026b1f05f869c3ff622331cc8b` | **未启用**；不得克隆、安装、运行或生成缓存。 |

版本与来源：

- [codebase-memory-mcp v0.9.0 官方发布页](https://github.com/DeusData/codebase-memory-mcp/releases/tag/v0.9.0)
- [Repomix v1.17.0 官方发布页](https://github.com/yamadashy/repomix/releases/tag/v1.17.0)
- [Codex `config.toml` 官方配置参考](https://developers.openai.com/codex/config-reference#configtoml)
- [Codex MCP 官方说明](https://developers.openai.com/codex/mcp)

Codex 只会在用户信任项目后读取项目级 `.codex/config.toml`。本仓库的该文件只声明代码图谱 MCP，不设置个人模型、认证、Provider、通知或遥测。

## 事实源与使用原则

开发时按以下顺序核对：

1. 根 `AGENTS.md` 与目标路径作用域规则；
2. 当前源码、测试和正式 API schema；
3. 人工维护的 ADR 与 `docs/architecture.md`；
4. codebase-memory 查询和 Repomix 快照等派生检索结果。

图谱、快照或 profile smoke 与源码冲突时，以源码和测试为准，并刷新或重建派生数据。工具推断不得自动创建、接受或改写 ADR。

当前安全设计由 [ADR-0003](adr/0003-verifiable-ai-context-boundary.md) 记录。[ADR-0001](adr/0001-local-ai-context-toolchain.md)、[2026-07-22 初始接入报告](test-reports/2026-07-22-ai-context-integration.md) 与 [安全加固报告](test-reports/2026-07-22-ai-context-security-hardening.md) 分别保留为当时的历史基线，不回写为新状态；当前发布候选的范围、最终实测值和签发结论见 [2026-07-22 发布候选验收报告](test-reports/2026-07-22-ai-context-release-candidate-validation.md)。

## 输入成员资格与内容语义

代码图谱和 Repomix 共用 `scripts/ai-context-inputs.py` 建立可验证 manifest，但分别应用 `.cbmignore` 和 `.repomixignore`。当前静态合同要求两份有效 deny 规则不漂移。

- 默认成员资格来自 Git index：已经提交或 staged-added 的普通文件才有资格进入清单。
- 文件内容来自当前 worktree，而不是 Git blob。因此 tracked 文件的 staged 或 unstaged 修改会进入新清单。
- worktree 中已删除的 tracked 文件会跳过；intent-to-add、gitlink、symlink、非普通文件、多硬链接文件和 unmerged index 会跳过或失败关闭。
- untracked 文件默认拒绝。确需纳入时，使用精确的仓库相对路径 `--allow-untracked PATH`；不接受 glob，例外会写入 manifest，deny 规则始终优先。
- 新增文件准备进入正常开发上下文时，优先将其加入 Git index，而不是长期依赖 untracked 例外。

manifest 记录 Git HEAD、成员资格与内容来源、profile、ignore 文件哈希、显式 untracked 例外，以及每个文件的路径、来源、Git object、SHA-256、大小和权限。当前上限为 20,000 个文件、单文件 1 MiB、总计 100 MiB。

清单读取使用 dirfd、no-follow 和 `lstat`/`fstat` inode 复验，要求受控目录与文件归当前 UID 所有。同一个安全打开的文件描述符在一次读取中同时完成密钥形态扫描、SHA-256、大小和权限记录，并在读取前后复验元数据；tracked 与显式 untracked 使用同一边界。权限设置或 `fchmod` 失败时不会降级继续。

这些哈希用于检测输入漂移和生成物篡改，不是签名或远程证明；已控制本地账户、脚本或原生二进制的攻击者不在该边界内。

## 安装 codebase-memory

所有命令都从仓库根目录执行。安装入口只安装审阅过的固定版本，不修改编辑器、个人 MCP 配置、Git hook、skill 或分层规则文件：

```bash
./scripts/code-intel.sh install
```

该入口支持 macOS、Linux 和 Windows WSL。二进制、许可证和 notices 默认安装到 `${XDG_DATA_HOME:-$HOME/.local/share}/narraverse/code-intel/codebase-memory-mcp/0.9.0/`，不进入 Git。安装流程：

- 只从 `v0.9.0` 官方 GitHub Release 下载当前平台资产；
- 在解包前核对仓库内审阅的 SHA-256；
- 保留 MIT 许可证、第三方许可证和 notices；
- 为已安装文件写入哈希清单，后续每次使用前复核；原生调用包装器还在执行前后核对平台固定的二进制 SHA-256 与文件身份；
- 不接受 PATH 中的同名程序或环境变量二进制覆盖；
- 通过最小环境与有界子进程包装器运行原生 CLI。

不得使用浮动 `latest`、未经审阅的 `curl | sh`，也不得绕开安装文件完整性检查。

## 构建和查询代码图谱

首次索引必须显式执行：

```bash
./scripts/code-intel.sh index
./scripts/code-intel.sh status
./scripts/verify-ai-context.sh --static
```

源文件变化后显式刷新或重建：

```bash
./scripts/code-intel.sh refresh
./scripts/code-intel.sh rebuild
```

若一次性需要未跟踪文件，可逐个声明：

```bash
./scripts/code-intel.sh refresh --allow-untracked path/to/file.py
```

### 输入代际和激活

索引器不直接读取实时仓库。每次 index、refresh 或 rebuild 会先获取 `.codebase-memory/.index.lock` 受控锁，再：

1. 建立 manifest；
2. 将批准文件复制到 `.codebase-memory/inputs/<inventory_sha>/files/`；
3. 把代际与嵌套目录设为 owner read/execute（`0500`），普通文件设为 owner-read-only（`0400`），可执行文件为 owner read/execute（`0500`）；
4. 只索引这份独立副本；不使用硬链接；
5. 索引后完整复验副本，并确认图中的文件路径是 manifest 的非空、未截断子集；
6. 最后原子替换 `.codebase-memory/current-input.json`。

构建或验证失败时，先前激活指针保持不变。“原子”只描述输入指针切换，不表示底层图数据库拥有跨步骤事务。cache、inputs、snapshot、generation、build 与 lock 等可写受控目录为当前 UID 的 `0700`；只读输入树目录为 `0500`。锁目录必须是真实目录，owner 记录使用 PID 和随机 token；并发构建会有界等待。有效 owner 仅在其 PID 不再存活时按 inode 复验回收；创建中断留下的精确空锁目录或仅含 `.owner.pending.<token>` 的锁目录，超过 5 秒 grace 后可以恢复；异常文件集、类型、所有权或替换路径都会失败关闭。

自动索引和后台 watcher 始终关闭。受控 `.runtime-config.lock` 串行化原生 CLI 的安全运行时配置写入，持续保持 `auto_index=false` 与 `auto_watch=false`。一次 MCP 会话绑定启动时的输入代际；成功刷新后应重新打开 Codex 任务，以使用新代际。

### 服务端固定八工具

`.codex/config.toml` 通过 `scripts/code-intel.sh mcp` 启动仓库内 Python 服务端代理。代理只发布：

1. `search_graph`
2. `query_graph`
3. `trace_path`
4. `get_code_snippet`
5. `get_graph_schema`
6. `get_architecture`
7. `search_code`
8. `index_status`

客户端 `enabled_tools` 是纵深防御，不是唯一边界。服务端不暴露 `project` 参数，而是注入当前已验证输入代际；`detect_changes`、`index_repository`、`list_projects`、`delete_project`、`manage_adr`、`ingest_traces`、rename、shell、文件写入、跨仓库路径和写 Cypher 都在原生调用前拒绝。

每次 MCP 查询会在原生调用前后完整复验输入代际和原生二进制：前验失败时不启动原生 CLI，后验失败时丢弃原生结果。二进制检查同时绑定固定 SHA-256 与启动时文件身份，运行期间被替换后，本次结果和后续调用都会失败关闭。代理还限制参数 schema、相对路径、只读 Cypher、环境变量和 I/O：请求 64 KiB、原生 stdout 256 KiB、stderr 32 KiB、最终 MCP 结果 256 KiB、单次调用 45 秒。超时或越界时终止整个子进程组并失败关闭。

终端可通过同一受控入口调试：

```bash
./scripts/code-intel.sh query index_status '{}'
```

### 已知查询限制

- 原始 `CALLS` / `WRITES` 边可能漏掉 instance method、endpoint 到 service、内嵌 callback、`yield from`、React callback 和动态 URL，也可能把常见同名符号连接到无关节点。
- 查询影响范围时应组合 `search_graph`、`query_graph`、`search_code` 和 `get_code_snippet`，再用当前源码、测试或 `rg` 复核。
- `trace_path` 应使用完整 qualified name；正式 ADR 以 `docs/adr/*.md` 为准，不使用图谱内置 ADR 写入能力。

## 生成 Repomix 上下文

默认生成全仓批准范围：

```bash
./scripts/build-ai-context.sh
```

也可以选择只缩小范围的 profile：

```bash
./scripts/build-ai-context.sh --profile backend
./scripts/build-ai-context.sh --profile frontend
./scripts/build-ai-context.sh --profile tooling
```

profile 集合固定为 `full`、`backend`、`frontend`、`tooling`，`full` 是默认值。profile 只能从已批准 manifest 中删减路径，不能增加 deny 路径，也不改变代码图谱范围。显式 untracked 文件若不属于所选 profile 会失败关闭。

### 锁定运行时和独立输入

Repomix 不加入产品 `package.json`、前端 lockfile 或后端 requirements。专用的 `scripts/repomix-runtime/package.json` 只依赖精确的 `repomix 1.17.0`；`package-lock.json` 使用 lockfileVersion 3，当前锁定 170 个 `node_modules` 包条目。离线验证要求每个条目都有精确版本、HTTPS registry URL 和 SHA-512 integrity，拒绝 link、install script、浮动版本及非 registry 来源。

每次构建都会在 `.ai-context/.building.*` 中：

1. 由 manifest 物化独立、owner-read-only 的临时输入根；
2. 以 no-follow 文件描述符复制专用 package manifest、lockfile 和 Repomix 配置，限制大小并在复制前后复验源文件身份、大小与修改时间；
3. 清空继承环境，只注入受控 PATH、HOME、TMP、npm cache 和稳定 locale/timezone，再运行 `npm ci --ignore-scripts --no-audit --no-fund --omit=dev`；
4. 核对安装后的 Repomix 版本、lock entry、integrity、入口文件和许可证；
5. 在独立输入根中通过 stdin 传入精确路径并运行 Repomix；
6. 验证快照文件路径集合与 manifest 完全相等；
7. 删除临时输入、node_modules、HOME、cache 和 tmp。

Node/npm/Repomix 版本探测限制为 15 秒和 4 KiB stdout/stderr；`npm ci` 限制为 600 秒、stdout/stderr 各 1 MiB；Repomix 生成限制为 600 秒、stdout 4 MiB、stderr 1 MiB，并实时监控快照不超过 512 MiB。超时、信号、I/O 越界、不安全输出或后台同进程组残留都会终止整个子进程组并失败关闭。

脚本不使用 `npm exec`、`npm view`、`npx` 或浮动版本。`npm ci` 仍可能访问 npm registry，因此完整快照生成不是离线 CI 步骤。

### 快照 bundle 与 provenance

成功输出写入 `.ai-context/snapshots/<bundle_id>/`：

- `manifest.json`：批准输入；
- `repomix.xml`：可移植快照；
- `provenance.json`：输入、profile、Repomix、package/lock hash、Node、npm、配置和文件数。

bundle ID 由输入清单、Repomix 配置、快照内容 SHA-256、专用 package/lock、Repomix 版本以及 Node/npm 版本共同派生。发布阶段先获取 `.ai-context/.publication.lock`，使用与图谱锁相同的 PID、随机 token、inode、有效 owner 回收与创建中断 grace 边界，串行覆盖 build rename、bundle 验证、retention/quarantine、便利 links 与 `current.json` 替换。发布器只接受 manifest、XML、provenance 三个文件的 owner-only bundle，重新验证文件集等值、快照哈希、provenance 和 bundle ID；同 ID 已存在时复验而不是覆盖。

激活前，发布器先清理可验证的遗留 `.removing.<bundle>.<token>` quarantine，再验证保留候选并把超出“新 bundle + 先前活动 bundle”范围的旧目录原子改名到 quarantine 后删除。意外文件、symlink、非普通文件或删除失败都会保留原 `current.json`，不会切到新 bundle。retention 成功后，脚本才分别原子替换便利 symlink，并最后原子替换 `.ai-context/current.json`；`current.json` 是规范激活指针并记录快照 SHA-256。最多保留当前与前一个 bundle。

`.ai-context/repomix.xml` 和 `.ai-context/repomix-input-manifest.json` 是当前 bundle 的便利入口。快照不能提交到 Git，也不能作为架构事实源；交给任何远程模型前仍要人工检查范围。

## 数据、隐私和网络边界

`.codebase-memory/` 与 `.ai-context/` 是可重建、潜在敏感的源码派生物，必须保持 Git 忽略。以下内容不得索引或打包：

- `.env`、密钥、认证信息与个人 Codex 配置；
- SQLite 数据库、用户小说、备份、导出作品和生成正文；
- `data/`、`backend/data/`、`backend/artifacts/`；
- `backups/`、`exports/`、`output/`、`outputs/`、`logs/`、`.logs/`、`test-artifacts/`；
- `frontend/node_modules/`、`frontend/dist/`、`.git/`；
- `.codebase-memory/`、`.ai-context/` 与其他工具缓存；
- `docs/archive/`、`docs/superpowers/`、`docs/test-reports/` 和报告型文档。

`.gitignore`、`.cbmignore`、`.repomixignore` 与硬编码 deny 共同保护范围，不能假设单个 ignore 文件足以覆盖另一个工具。ignore 文件禁止使用反向 `!` 规则恢复敏感路径。

默认不上传图谱、快照或源码。若把任何派生数据交给远程模型，必须由用户显式启用，API Key 只能来自环境变量。

已知联网动作：

- `scripts/code-intel.sh install` 从 GitHub Releases 下载固定资产；
- `scripts/build-ai-context.sh` 的 `npm ci` 按 lockfile 获取缺失包；
- `verify-ai-context.sh --full` 会执行完整 Repomix 构建，因此可能联网。

项目 MCP 启动仓库内 Python 代理并调用已安装的原生 CLI，不再直接暴露上游 MCP server。工具没有操作系统级网络沙箱；需要严格离线保证时，应在宿主网络层阻断外连并重新验收。

## 验证

普通 PR 和无第三方二进制环境运行离线静态合同：

```bash
./scripts/verify-ai-context.sh --static
```

它验证：

- 分层规则、固定八工具配置和 DeepWiki 禁用边界；
- codebase-memory 发布归档/二进制哈希、已安装文件合同与 Repomix 170 包 lock；
- 输入成员资格、untracked/deny、单文件描述符密钥扫描与哈希、UID/权限、symlink/hardlink、独立副本、受控锁、manifest 和原子指针单元测试；
- 服务端代理参数、只读 Cypher、查询前后输入/二进制复验、二进制替换拒绝、有界子进程和环境剥离合同；
- `full`、`backend`、`frontend`、`tooling` profile 配置；
- 9 个 profile membership 与源码字面锚点场景；
- 生成目录和敏感路径的 Git ignore 边界。

9 场景 smoke 只证明选定 profile 包含预期路径和配置的源码字面锚点，不调用真实 codebase-memory 或 Repomix，也不证明 hit@k、图边方向、precision/recall、snippet 正确性、索引新鲜度或生成确定性。当前精确合同如下：

| 场景 ID | Profile | 必含路径 | 关键 anchor / 真实检索期望 |
|---|---|---|---|
| `dual_api_prefix` | backend | `backend/app/main.py`、`backend/app/api/v1/router.py` | `/api` 与 `/api/v1`；`prefix="/api/v1"` → `backend/app/main.py` |
| `creation_star_lane` | backend | Creation Star service、`studio_service.py` | `canon-preview` → `backend/app/api/v1/router.py` |
| `outline_debate_lane` | backend | outline endpoint 与 service | `/chapters/confirm` → `backend/app/api/v1/router.py` |
| `chapter_writing_lane` | backend | chapter workflow、quality gate | `quality_gate_node` → chapter workflow |
| `batch_generation` | backend | writing endpoint、`studio_service.py` | `/write/batch-generate` → router |
| `canon_approval_boundary` | backend | router、`studio_service.py` | `approve_canon_proposal` → `backend/app/services/studio_service.py` |
| `frontend_outline_workbench` | frontend | Outline Studio、Debate Panel | `OutlineDebatePanel` → `OutlineStudioPage.tsx` |
| `frontend_proposal_apply` | frontend | Workspace、前端 Studio API | `applyProposal` → `WorkspacePage.tsx` |
| `tooling_and_ci_context` | tooling | CI、根规则、`scripts/dev.sh` | `verify-ai-context.sh --static` → `.github/workflows/ci.yml` |

已安装并重建代码图谱后，可另行运行真实文件检索基线：

```bash
python3 scripts/evaluate-code-graph.py
```

该入口读取同一 9 场景中的 `retrieval_queries`，逐条通过受控 `search_code` 查询前 10 个文件，报告 hit@10、MRR、每题排名和错误；任一 miss 返回非零。它验证的是固定样本上的文件级检索，不证明调用边方向、任意查询的 precision/recall、snippet 内容或跨版本稳定性。

安装第三方工具后，可手动或定期运行完整验收：

```bash
./scripts/verify-ai-context.sh --full
```

它会重新生成默认 `full` 快照和代码图谱，在新图谱上执行真实文件检索基线，再执行原始 MCP handshake，验证八工具集合、禁止调用、敏感路径排除、图路径为 manifest 子集、Repomix 文件集与 manifest 相等、内容寻址 provenance、生成物权限、激活指针、保留策略和 DeepWiki 缓存不存在。真实检索也可用上面的独立命令重跑；两者都不得成为普通产品测试、构建或启动的必需步骤。

若一批新增文件尚未进入主暂存区，可把当前 Git index 复制到临时文件，通过隔离的 `GIT_INDEX_FILE` 只 staged-add 本批精确路径，再在同一环境变量下运行 `--full`。这不会改变主 index，但完整验收仍会切换 `.codebase-memory/` 与 `.ai-context/` 的活动指针；验证后必须回到默认 Git index 再运行一次 `--full`，确认默认活动状态已经恢复。隔离 index 只能作为候选范围证据，不能替代最终提交后的干净检出验收。

`.github/workflows/ai-context-full.yml` 只提供人工 `workflow_dispatch` 完整验收，不在普通 push/PR 自动下载第三方 AI 工具。相关 workflow 的 Actions 固定完整 commit SHA，顶层权限为 `contents: read`，checkout 禁止持久化凭据；静态供应链测试会检查这些合同。

AI 上下文工具缺失时，根规则 `GLOBAL-VERIFY-001` 规定的产品测试、构建和 Docker 配置检查仍应正常运行。

## 升级

升级外部工具、依赖闭包、输入格式、权限或激活方式不是普通自动更新。必须先更新 `scripts/AGENTS.md` 的 `TOOLING-AI-CONTEXT-001`，必要时同步根路由和 ADR，获得确认后再：

1. 核对发布资产、哈希、许可证、notices 和变更日志；
2. 更新固定版本、平台资产哈希或 `scripts/repomix-runtime/package-lock.json`；
3. 运行供应链离线验证和全部合同测试；
4. 重新安装、重建并执行 `verify-ai-context.sh --full`；
5. 新建当次验收报告，不回写旧报告冒充新状态。

不得把 `latest`、浮动 semver 或未经审阅的新 registry 来源固化为仓库约定。

## 卸载

停止所有使用该 MCP 的 Codex 会话后执行：

```bash
./scripts/code-intel.sh uninstall
```

该入口先验证安装目录、当前 UID、精确文件集和哈希，再把版本目录原子改名为 `.removing.<version>.<token>` tombstone、`fsync` parent，最后删除其中的二进制、许可证、notices 和安装哈希。若进程在删除中断，下一次 install 或 uninstall 只会在复验 tombstone 名称、目录和剩余文件后继续清理；意外条目或 symlink 会失败关闭。“可恢复”表示可安全完成中断的卸载，不表示恢复已删除的二进制。

卸载不触碰产品源码、SQLite 数据、个人 Codex 配置或仓库索引。图谱仍保留在精确的 `.codebase-memory/` 目录；确认不再需要后可单独删除。

Repomix 没有持久 node_modules；构建结束后临时运行时会删除。不再需要快照时，可删除仓库根目录下精确的 `.ai-context/` 目录。

永久移除整套接入前，必须先更新 `TOOLING-AI-CONTEXT-001`、相关 ADR 和根路由并获得确认，再删除项目配置、ignore、脚本、专用 lockfile 和本指南。卸载本机工具不会影响产品运行、默认测试或 Docker 启动。

## 故障处理

### Codex 中看不到代码图谱工具

1. 确认仓库已标记为可信；
2. 运行 `./scripts/code-intel.sh status` 和 `./scripts/verify-ai-context.sh --static`；
3. 检查 `.codex/config.toml` 是否仍使用固定八工具 `enabled_tools`；
4. 重新打开 Codex 任务，使项目 MCP 配置重新加载。

### 索引缺失、陈旧或完整性失败

运行 `./scripts/code-intel.sh refresh`，成功后重新打开 Codex 任务，再用 `index_status`、实际结构查询和源码 `rg` 结果交叉核对。不要启用自动 watcher 绕过失败。完整性错误持续出现时，停止 MCP 会话、保留错误信息并运行 `rebuild`；不要直接修改 `.codebase-memory/inputs/`。

### 查询结果与源码冲突

以源码、测试和正式 schema 为准。记录错误问题，检查 `.cbmignore` 是否误排除必要源码，重建后再次验证；不要把错误推断写入 ADR。

### Repomix lock 或 npm ci 失败

先运行 `python3 scripts/verify-ai-tool-supply-chain.py`。若 lock 校验失败，不要用 `npm install`、`npm exec`、关闭 integrity 或浮动版本绕过。网络不可用时保留现有快照，稍后在允许访问 npm registry 的环境重试完整生成。

### Repomix 输出过大

选择更小的 `backend`、`frontend` 或 `tooling` profile，检查 manifest 与 `.repomixignore`，不要取消敏感路径排除换取完整性。修改规则或 profile 后重新生成并复验。

### 发现敏感内容进入派生数据

立即停止共享或上传，关闭 MCP 会话，删除精确的 `.codebase-memory/` 与 `.ai-context/` 生成目录，修复 deny/ignore 规则后重建并复验。若内容已发送到外部系统，按该系统的数据删除和密钥轮换流程处理。

## DeepWiki Open：尚未启用

当前不得克隆、安装或运行 DeepWiki Open，也不得创建 Wiki 缓存。前三阶段完成与通过验收不会自动授权第四阶段；只有用户再次明确确认后，才能为它提出新的规则、ADR、缓存位置和运行方案。

即使未来获准，克隆、向量索引、缓存和 Wiki 输出也必须位于仓库外用户缓存目录，默认只读，不进入 `docker-compose.yml`，不成为启动或测试条件；远程 Wiki/LLM 必须显式启用且密钥只来自环境变量。自动 Wiki 始终只是解释层，不是事实源。
