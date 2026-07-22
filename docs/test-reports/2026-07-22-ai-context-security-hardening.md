# AI 开发上下文安全加固验收报告

## 1. 报告状态

- 日期：2026-07-22
- 验收对象：固定八工具代码图谱代理、可验证输入代际、Repomix 锁定供应链与快照 bundle、四个 profile、离线 smoke 和 DeepWiki 禁用边界。
- 关联决策：[ADR-0003](../adr/0003-verifiable-ai-context-boundary.md)
- 取代关系：本报告记录当前加固实现的证据；[初始接入报告](2026-07-22-ai-context-integration.md) 继续作为历史基线，不回写为当前状态。
- 当前结论：静态合同和完整集成验收均通过；DeepWiki Open 未启用。

本报告验证的是运行命令时可见的当前工作树及其受控输入清单，不把图谱、快照或测试报告提升为事实源。根/作用域 `AGENTS.md`、当前源码、测试和正式 API schema 仍具有更高事实优先级。

## 2. 验收基线与可复现性

| 字段 | 实际值 |
|---|---|
| Git HEAD | `f6d97d2cbeee9389199f8c1e029eba8cab7960c2` |
| 分支 | `main` |
| 验收时间 | 2026-07-22 13:47（Asia/Shanghai） |
| 操作系统 | Darwin 25.5.0 arm64 |
| Python | 3.9.6 |
| Node.js | v26.0.0 |
| npm | 11.12.1 |
| 工作树 | 非干净；完整验收时共 101 个状态条目，其中 55 个 modified、3 个 deleted、43 个 untracked |

输入工具的成员资格来自 Git index 中已经提交或 staged-added 的普通文件，内容来自这些成员在当前 worktree 中的字节。完整验收不会自动纳入普通 untracked 文件；本轮未使用 `--allow-untracked`。因此，以上结果是当前 index 成员集合和实际执行入口的有效运行证据，但不是 43 个未跟踪文件的打包或发布证明；其中包含本轮新增的工具与文档。合并或发布前应先让目标文件进入 Git index，再从干净检出重新执行完整验收。

## 3. 执行命令与结果

| 命令 | 结果 |
|---|---|
| `python3 scripts/verify-ai-tool-supply-chain.py` | 通过；Repomix 专用 lock 固定 170 个 `node_modules` 包条目。 |
| `python3 -m unittest discover -s scripts/tests -p 'test_*.py'` | 42 / 42 通过；耗时 9.543 秒。 |
| `./scripts/verify-ai-context.sh --static` | 通过；分层规则、配置、供应链、输入与代理合同、四个 profile、9 场景 smoke、ignore 和 DeepWiki 边界均通过。 |
| `./scripts/verify-ai-context.sh --full` | 通过；重建图谱和 `full` 快照、真实图谱检索、原始 MCP handshake、内容寻址 provenance、权限、路径集合、指针、保留策略及 DeepWiki 边界均通过。 |
| `python3 scripts/evaluate-code-graph.py` | 通过；真实 `search_code` 文件检索 hit@10 = 9 / 9（1.000），MRR = 0.569。 |
| `python3 scripts/verify-agents-guidance.py` | 通过；5 个规则文件、42 个稳定规则 ID，最大可移植规则链不超过 28,672 bytes。 |
| `docker compose config --quiet` | 通过；AI 上下文工具未成为默认产品 Compose 依赖。 |

`--full` 会在最小环境中执行 `npm ci` 并可能访问 npm registry；它不是默认产品测试，也不证明宿主机处于离线状态。

## 4. 安全合同验收矩阵

| 控制面 | 已验证合同 | 结果 |
|---|---|---|
| MCP 能力面 | 服务端只发布 `search_graph`、`query_graph`、`trace_path`、`get_code_snippet`、`get_graph_schema`、`get_architecture`、`search_code`、`index_status`；`detect_changes`、索引、项目选择、删除、ADR 写入、trace 导入、rename、shell、文件写入和写 Cypher 不可达。 | 通过 |
| 仓库绑定 | 客户端不能提交 `project`；代理注入启动时已验证的输入代际，并校验相对路径和只读 Cypher。 | 通过 |
| 查询 TOCTOU | 每次原生调用前后都完整复验输入副本与原生二进制；二进制绑定固定 SHA-256 和启动时文件身份。前验失败不执行，后验发现输入或二进制替换时隐藏结果并阻止后续调用。 | 通过 |
| 资源边界 | 请求 64 KiB、原生 stdout 256 KiB、stderr 32 KiB、最终结果 256 KiB、单次调用 45 秒；越界或超时终止子进程组。 | 通过 |
| 输入成员资格 | Git index membership + 当前 worktree bytes；untracked 默认拒绝；硬 deny 优先；symlink、gitlink、多硬链接、非普通文件和越界路径失败关闭。 | 通过 |
| 安全读取与权限 | 受控目录要求当前 UID，使用 dirfd/no-follow/inode 复验；同一文件描述符一次完成密钥扫描、SHA/size/mode 并复验读前后元数据；可写目录 `0700`、只读输入目录 `0500`、普通文件 `0400`、可执行文件 `0500`；`fchmod` 失败关闭。 | 通过 |
| 图谱输入代际 | manifest 批准文件被复制为独立 owner-read-only 文件；不用硬链接；索引与复验通过后才替换 `current-input.json`。 | 通过 |
| 并发与锁 | index/refresh/rebuild 使用独占 index 锁，安全运行时配置使用独立 runtime 锁；锁目录、owner PID/token 与 inode 均校验，陈旧锁只在 owner 进程不存在时回收。 | 通过 |
| 图路径覆盖 | 图中路径必须是 manifest 的非空、未截断子集，而非错误要求所有可打包文档均可解析为图节点。 | 通过；277 个索引文件 |
| codebase-memory 供应链 | 固定 `0.9.0` 平台归档及原生二进制 SHA-256；安装文件、许可证和 notices 有清单并在使用前复核；不接受 PATH/环境变量替代二进制。 | 通过 |
| Repomix 供应链 | `repomix 1.17.0` 专用 lock；170 包闭包逐项要求精确版本、HTTPS registry URL 和 SHA-512 integrity；拒绝 link、install script 与浮动来源。 | 通过 |
| Repomix 隔离 | manifest 物化独立只读输入；package/lock/config 以 no-follow 描述符复制并前后复验；清空继承环境后执行 `npm ci --ignore-scripts --no-audit --no-fund --omit=dev`；临时 HOME/cache/tmp/runtime 均清理。 | 通过 |
| Repomix 资源边界 | 版本探测 15 秒/4 KiB；npm 安装 600 秒且 stdout/stderr 各 1 MiB；Repomix 生成 600 秒、stdout 4 MiB、stderr 1 MiB、快照 512 MiB；失败时终止子进程组并清理同组后台进程。 | 通过 |
| CI 供应链合同 | `ci.yml` 与 `ai-context-full.yml` 的 Actions 固定完整 commit SHA，权限为 `contents: read`，checkout 使用 `persist-credentials: false`；完整 AI 上下文验收仅 `workflow_dispatch`。 | 静态合同通过；本报告未触发远程 workflow |
| 快照闭包 | `repomix.xml` 的文件路径集合与 manifest 完全相等；bundle 固定包含 manifest、XML 和 provenance，快照 SHA-256 参与 bundle ID 并写入 provenance/current；发布器复验精确文件集、权限和内容寻址关系后才激活。 | 通过；284 / 284 文件 |
| Profile | `full`、`backend`、`frontend`、`tooling` 只能缩小批准集合，不能绕过 deny；默认是 `full`。 | 通过 |
| 离线 smoke | 双 API 前缀、创作 Star、大纲议事、章节写作、批量生成、人工审批、两个前端交互和 tooling/CI 共 9 场景。 | 9 / 9 通过 |
| 真实文件检索 | 在已重建图谱上逐题调用受控 `search_code`，仅取前 10 个文件并检查 expected path；任一 miss 失败。 | hit@10 9 / 9；MRR 0.569 |
| 敏感与生成路径 | `.codebase-memory/`、`.ai-context/`、数据、导出、日志、数据库、密钥和报告型目录保持排除且不被 Git 跟踪。 | 通过 |
| DeepWiki | 仓库中无克隆、依赖、配置或缓存进入活跃链路；验证器检查其生成目录不存在。 | 通过；仍禁用 |

## 5. 完整验收生成物

### 5.1 代码图谱

| 字段 | 实际值 |
|---|---|
| 输入代际 | `39e87350197a7694aef31ab09aa72c39c1cdafeb4bea81eea8bb8a53204f3544` |
| 批准文件 | 284 |
| 批准字节 | 2,744,657 |
| 图中索引文件 | 277；为 manifest 的非空、未截断子集 |
| 图规模 | 3,574 nodes / 15,407 edges |
| 状态 | `ready` |
| 成员资格 / 内容 | `git_index_committed_or_staged_added` / `current_worktree` |
| 显式 untracked | 空 |

原生 MCP stdio handshake 返回的工具集合与固定八工具完全一致，禁止调用在进入原生 CLI 前被拒绝。图谱根路径指向该输入代际的独立 `files/` 副本，不指向仓库实时根目录。

### 5.2 Repomix bundle

| 字段 | 实际值 |
|---|---|
| Bundle ID | `e08eef0bd9919e79abfc81ad9ef4e75e043187562f00d8648f053f866b2014e9` |
| Profile | `full` |
| Manifest inventory | `0f3d8f589dead760c88e30259da4990e27e244ac9f8a16d42ce7b0134ee630b3` |
| 批准 / 打包文件 | 284 / 284 |
| 批准输入字节 | 2,744,657 |
| 快照字节 | 3,486,911 |
| Snapshot SHA-256 | `944ecb26ee82c7fee916a0862b480dd7ad88958d2da9827edf1c75718f463320` |
| Repomix 配置 SHA-256 | `250950e587384bf7166aea83ede81dcb43c0379de553688ee9fee57fbb6abee4` |
| Runtime package SHA-256 | `fc9dfe897170da493151fabfe70c63c40240b1d58e2dc6012b4028e9d966ba73` |
| Runtime lock SHA-256 | `0d2a6f6899f6c1bcef2c10d37f13b07fa06e8344bcb03b81dc18d5f7c023ab0b` |
| Repomix / Node / npm | 1.17.0 / v26.0.0 / 11.12.1 |
| 规范激活指针 | `.ai-context/current.json` |

manifest、快照和 provenance 位于同一内容寻址 bundle 目录，发布时复验精确文件集、owner-only 权限、快照哈希与 bundle ID。便利 symlink 逐个原子替换，`current.json` 最后替换并作为唯一规范激活指针；这里的原子性不扩展为多文件事务。

## 6. 仍然存在的限制

- 工作树非干净，普通 untracked 文件不会进入默认 manifest；目标改动进入 Git index 后必须重跑发布前证据。
- 9 场景 smoke 只检查 profile membership 与源码字面锚点；独立真实检索只证明固定 9 题的文件级 hit@10 与 MRR。二者都不证明任意查询的 precision/recall、图边方向、snippet 正确性或构建确定性。
- codebase-memory 解析仍可能漏掉 instance method、endpoint 到 service、内嵌 callback、`yield from`、React callback 和动态 URL，并可能生成常见同名符号误边；结论必须用源码、测试或 `rg` 复核。
- Repomix 的 `npm ci` 可能联网；代理和构建脚本没有操作系统级网络沙箱。严格离线环境需在宿主层阻断网络并重新验收。
- manifest 与 provenance 是本地完整性记录，不是数字签名、远程证明或对已失陷本地账户的保护。
- 指针替换保证失败构建不激活新代际，但不声称底层图数据库、便利 symlink 或整个 bundle 切换具有跨步骤事务。

## 7. 结论

ADR-0003 所定义的输入、权限、供应链、激活和验证边界已在本次受控成员集合上通过静态与完整验收。codebase-memory、人工 ADR / Mermaid 和 Repomix 三阶段可继续作为可选开发工具使用；它们不进入产品运行时，也不能替代源码和测试。DeepWiki Open 继续明确为“暂不启用”，启用前必须获得新的用户确认并另立规则、ADR 与验收证据。
