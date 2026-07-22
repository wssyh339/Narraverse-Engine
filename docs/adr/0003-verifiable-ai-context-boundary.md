# ADR-0003：采用可验证输入代际与服务端只读 AI 上下文边界

- 状态：Accepted
- 日期：2026-07-22
- 决策者：项目维护者
- 影响范围：开发期代码图谱、MCP 权限、Repomix 输入与供应链、AI 上下文 profile、生成缓存和验收；不影响产品运行时

## 背景

[ADR-0001](0001-local-ai-context-toolchain.md) 确立了本地代码图谱、人工 ADR / Mermaid 和 Repomix 快照三层工具链，但初始方案主要依赖客户端 `enabled_tools`，允许九个查询工具并包含读取实时工作树变化的 `detect_changes`。客户端白名单不能单独构成服务端权限边界，直接读取实时仓库也难以证明一次索引或快照究竟使用了哪些字节。

Repomix 初始包装只锁定顶层版本与 SRI，并通过临时 npm 解析执行。其传递依赖仍可能随时间变化；同时，若工具直接读取活跃工作树，构建期间的文件变化会形成 TOCTOU 风险。代码图谱和快照还需要清楚区分“生成成功”与“已经验证并激活”，避免失败构建覆盖先前可用状态。

因此需要把权限、输入、供应链、激活和验证同时收紧，并明确自动化 smoke 能证明与不能证明的范围。

## 决策

### 1. 统一可验证输入清单

- 代码图谱与 Repomix 使用 `scripts/ai-context-inputs.py` 构建 manifest。
- 默认成员资格来自 Git index 中已经提交或 staged-added 的普通文件；内容使用当前 worktree 字节，而不是 Git blob。
- untracked 默认拒绝，只接受精确仓库相对路径 `--allow-untracked PATH`，并把例外记录在 manifest。硬 deny、`.gitignore` 和专用 ignore 永远优先。
- symlink、gitlink、非普通文件、多硬链接文件、unmerged index、越界路径及不安全输出目录失败关闭。
- manifest 记录 Git HEAD、成员与内容来源、profile、ignore 哈希、文件来源、Git object、SHA-256、大小和权限。当前上限为 20,000 文件、单文件 1 MiB、总计 100 MiB。
- 受控路径使用 dirfd、no-follow 与 `lstat`/`fstat` inode 复验，并要求当前 UID 所有。同一个安全打开的文件描述符在一次读取中完成密钥扫描、SHA-256、大小与 mode 记录，读取前后复验元数据；tracked 和显式 untracked 应用相同边界。

### 2. 独立代码图谱输入与服务端固定八工具

- 图谱只索引 `.codebase-memory/inputs/<inventory_sha>/files/` 下的 owner-only 独立副本，不使用硬链接，也不直接索引实时仓库。
- index、refresh 和 rebuild 必须持有受控 index 锁；原生 CLI 的安全配置写入必须持有独立 runtime 锁。锁目录拒绝 symlink 和非目录替换，owner 使用 PID 与随机 token，并在打开、回收和释放时复验 inode。有效 owner 仅在其 PID 不再存活时回收；创建中断留下的精确空锁目录或仅含 `.owner.pending.<token>` 的锁目录，超过 5 秒 grace 后可恢复；异常文件集、类型、所有权或路径替换失败关闭。
- 每个输入代际包含 manifest；代际与嵌套目录为当前 UID 的 `0500`，普通文件为 `0400`，可执行文件为 `0500`。cache、inputs、snapshot、generation、build 与 lock 等可写受控目录为 `0700`。权限设置或 `fchmod` 失败时停止；索引完成后复验全部路径、内容哈希和权限，并确认图中的文件路径是 manifest 的非空、未截断子集。
- 只有上述检查通过后才原子替换 `.codebase-memory/current-input.json`。失败构建不改变先前指针；原子性只适用于指针，不声称底层图数据库事务化。
- `.codex/config.toml` 通过仓库内 Python 服务端代理连接原生 CLI。服务端只发布 `search_graph`、`query_graph`、`trace_path`、`get_code_snippet`、`get_graph_schema`、`get_architecture`、`search_code` 和 `index_status`。
- `project` 由服务端注入。`detect_changes`、项目选择、索引、删除、ADR 写入、trace 导入、rename、shell、文件写入、跨仓库路径和写 Cypher 在调用原生二进制前拒绝。客户端 `enabled_tools` 仅作为纵深防御。
- 每次 MCP 查询在原生调用前后完整复验绑定输入及原生二进制；二进制同时绑定平台固定 SHA-256 与启动时文件身份。前验失败不启动 native，后验发现输入或二进制替换时不返回结果，后续调用也失败关闭。参数、相对路径、只读 Cypher、环境、请求、超时、stdout、stderr 和最终结果都有硬上限，越界时终止子进程组并失败关闭。
- codebase-memory 发布归档及其中的原生二进制按平台分别锁定 SHA-256；安装保留许可证与 notices，并为已安装文件保存和复核哈希。运行时不接受 PATH 或环境变量中的替代二进制，所有原生 CLI 调用使用最小环境、有界子进程包装器和执行前后完整性复验。
- uninstall 先复验受控安装，再把版本目录原子改名为带随机 token 的 tombstone、同步 parent 后逐项删除。后续 install/uninstall 可在复验名称、目录和剩余精确文件集后完成中断清理；symlink 或意外条目失败关闭。

### 3. Repomix 独立输入、依赖闭包与 provenance

- Repomix 不加入产品、前端或后端依赖。`scripts/repomix-runtime/package.json` 精确依赖 `repomix 1.17.0`，专用 `package-lock.json` 使用 lockfileVersion 3，当前锁定 170 个 `node_modules` 包条目。
- 离线供应链验证要求每个条目具有精确版本、npm registry HTTPS URL 和 SHA-512 integrity；禁止 link、install script、浮动版本、非 registry 来源、dev dependency 与运行脚本。
- 每次生成先从 manifest 物化独立、owner-read-only 的临时输入根。package manifest、lockfile 与 Repomix 配置通过 no-follow 文件描述符复制，并在复制前后复验源文件身份、大小和修改时间。
- `npm ci --ignore-scripts --no-audit --no-fund --omit=dev` 在清空继承环境、只注入受控 PATH/HOME/TMP/cache/locale/timezone 的有界子进程中执行。安装完成后复核 Repomix 版本、顶层 lock entry、integrity、入口和许可证。
- Repomix 在独立输入根内通过 stdin 接收精确路径；不使用 `npm exec`、`npm view`、`npx`、Git history、默认 ignore 或浮动版本。输出路径集合必须与 manifest 完全相等。
- Node/npm/Repomix 版本探测限制为 15 秒和 4 KiB stdout/stderr；npm 安装与 Repomix 生成各限制 600 秒，前者 stdout/stderr 各 1 MiB，后者 stdout 4 MiB、stderr 1 MiB，快照上限 512 MiB。超时、信号、I/O 或快照越界时终止子进程组；成功 leader 退出后也清理同组后台进程。
- 临时输入、node_modules、HOME、cache 和 tmp 在生成后删除。成功 bundle 固定包含 `manifest.json`、`repomix.xml` 和 `provenance.json`。
- bundle ID 由输入、配置、快照内容 SHA-256、package/lock hash、Repomix、Node 和 npm 版本共同派生；provenance 记录同一组事实。发布必须持有 `.ai-context/.publication.lock`，以 PID/token/inode 复验的 owner-only 目录锁串行覆盖 build rename、bundle 验证、retention/quarantine、便利 links 与 `current.json`。发布器只接受精确的 manifest/XML/provenance 三文件集合，复验 owner-only 权限、manifest 等值、快照哈希、provenance 和内容寻址 ID；同 ID 已存在时验证而非覆盖。
- retention 在激活前执行：先安全清理遗留 removal quarantine，再验证候选，把超出“新 bundle + 先前活动 bundle”的旧目录原子改名到 quarantine 并删除。任何不安全条目或删除失败都不替换旧指针。之后才依次替换便利 symlink，最后原子激活、记录快照 SHA-256 的 `.ai-context/current.json`。最多保留当前与前一个 bundle。

### 4. Profile 与评测边界

- Repomix profile 固定为 `full`、`backend`、`frontend`、`tooling`，默认 `full`。profile 只能缩小已批准 manifest，不能绕过 deny，也不改变代码图谱范围。
- `scripts/evaluate-ai-context.py` 离线执行 9 个 profile membership 与源码字面锚点场景：`dual_api_prefix`、`creation_star_lane`、`outline_debate_lane`、`chapter_writing_lane`、`batch_generation`、`canon_approval_boundary`、`frontend_outline_workbench`、`frontend_proposal_apply`、`tooling_and_ci_context`。正典审批场景的锚点与真实检索目标是 `approve_canon_proposal`，不使用正文提案的 `apply_proposal` 代替。
- 该 smoke 不运行真实 codebase-memory 或 Repomix，不证明 hit@k、边方向、precision/recall、snippet 准确性、重建新鲜度或生成确定性。真实图谱准确率仍需与源码、测试和 `rg` 人工交叉验证。
- `scripts/evaluate-code-graph.py` 在已安装、已重建的图谱上读取同一配置的 `retrieval_queries`，通过受控 `search_code` 评估前 10 个文件，报告 hit@10、MRR 和逐题排名；任一 miss 失败。它是固定样本的文件级检索基线，不替代边方向、snippet 和人工源码复核。

### 5. 数据、事实层与非目标

- `.codebase-memory/` 与 `.ai-context/` 是 Git 忽略的可重建敏感数据，不得提交或默认上传。
- 根/作用域规则、源码、测试和正式 schema 是事实源；人工 ADR / Mermaid 记录稳定设计；图谱、快照和 smoke 只是检索或验证层。
- 工具链不修改产品 API、数据表、前端页面、默认 Compose、后端 requirements 或前端 package manifest，也不成为产品启动、测试或构建前置条件。
- DeepWiki Open 继续禁用。前三阶段完成不会自动授权其克隆、安装、运行或缓存；启用必须由用户再次明确确认并采用新的规则和 ADR。

## 后果

### 正向影响

- 服务端而非客户端配置强制执行固定查询能力和仓库绑定。
- 一次索引或快照使用的路径、字节、权限、profile 和工具供应链均可由 manifest 与 provenance 复核。
- 当前 UID、dirfd/no-follow、单文件描述符读取与权限合同缩小路径替换、重复打开和宽权限窗口。
- 独立副本与查询前后复验降低实时工作树变化、硬链接和结果返回窗口中的 TOCTOU 风险。
- 受控锁避免并发索引、激活和原生安全配置写入互相踩踏；原生二进制后验能阻止替换窗口中的结果泄漏。
- 构建后验证与指针激活保留先前可用代际，失败不会直接替换当前入口。
- 激活前 quarantine 让 retention 错误在旧指针仍有效时暴露；卸载 tombstone 允许后续调用安全完成中断清理。
- publication lock 防止两个已经完成生成的 Repomix 进程在 rename、retention 和指针替换之间交错。
- 快照内容哈希参与 bundle ID 和当前指针，发布前复验可发现同 ID 目录或快照内容漂移。
- Repomix 的传递依赖闭包、integrity 和运行环境不再依赖临时浮动解析。
- 有界 runner 限制安装和生成的时间、输出与派生快照规模，并阻止工具遗留同组后台进程。
- 离线静态合同可进入普通 PR CI，不要求第三方 AI 二进制、npm 下载或真实 LLM。
- 完整联网验收只由最小权限、Actions 固定完整 commit SHA 的人工 workflow dispatch 执行，不进入普通 push/PR 路径。

### 成本与风险

- 复制输入和每次查询完整哈希增加磁盘 I/O 与延迟；大型仓库受显式文件数和容量上限约束。
- worktree 修改只有重建后才进入图谱；已有 MCP 会话绑定启动时代际，刷新后需要重开客户端任务。
- Repomix 每次完整生成创建临时依赖运行时，耗时和网络成本高于复用全局安装；`npm ci` 仍依赖 registry 可用性。
- lockfile、平台资产哈希、Node/npm 版本和许可证需要人工升级与重新验收。
- manifest 和 provenance 是完整性记录而非签名；已控制本地账户、脚本、安装目录或原生二进制的攻击者不在该威胁模型内。
- 图谱解析仍可能产生漏边和误边，不能替代源码和测试。

## 备选方案

- 仅依赖客户端 `enabled_tools`：无法阻止其他 MCP 客户端或配置漂移调用服务端能力，拒绝。
- 保留 `detect_changes`：需要读取实时工作树并扩大模型可见范围，与固定输入代际冲突，拒绝。
- 直接索引或打包仓库根目录：无法稳定证明构建期间读取的字节，拒绝。
- 使用硬链接节省复制成本：源文件和代际可能相互影响，权限变化也会共享 inode，拒绝。
- 仅锁定 Repomix 顶层版本或每次使用 `npm exec`：传递依赖仍可漂移，拒绝。
- 把外部工具加入默认产品依赖或普通产品 CI：增加运行、网络和供应链耦合，拒绝。
- 当前启用 DeepWiki、Neo4j 或其他图数据库：超出已确认范围，拒绝。

## 验证方式

离线静态合同：

```bash
python3 scripts/verify-agents-guidance.py
bash -n scripts/*.sh
python3 scripts/verify-ai-tool-supply-chain.py
./scripts/verify-ai-context.sh --static
docker compose config --quiet
```

安装第三方工具后的完整验收：

```bash
./scripts/verify-ai-context.sh --full
```

完整验收必须覆盖真实 Repomix 生成、代码图谱重建、原始 MCP handshake、固定八工具、禁止调用、敏感路径排除、图路径 manifest 子集、Repomix manifest 等值、provenance、生成物权限、指针、保留策略和 DeepWiki 缓存不存在；随后在新图谱上执行真实文件检索基线。`docs/test-reports/2026-07-22-ai-context-security-hardening.md` 保留为早期加固时点的历史证据；当前发布候选范围、最终实测值与签发结论记录在新建的 `docs/test-reports/2026-07-22-ai-context-release-candidate-validation.md`，不得通过改写旧报告冒充新状态。

未进入主暂存区的候选批次可以复制当前 index 到隔离 `GIT_INDEX_FILE`，只加入本批精确路径后运行完整验收。该流程不得修改主 index，且结束后必须用默认 index 重跑并恢复默认活动指针；隔离验证不能替代最终提交后的干净检出证据。

## 关联

- 相关稳定规则 ID 与作用域文件：`scripts/AGENTS.md` 的 `TOOLING-AI-CONTEXT-001`、`OPS-CI-001`；根 `AGENTS.md` 的 `GLOBAL-DOCS-001`
- 开发指南：`docs/ai-assisted-development.md`
- 架构概览：`docs/architecture.md`
- 安全加固报告：`docs/test-reports/2026-07-22-ai-context-security-hardening.md`
- 发布候选验收报告：`docs/test-reports/2026-07-22-ai-context-release-candidate-validation.md`
- 取代的 ADR：ADR-0001
- 被取代于：无
