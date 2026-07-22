# AI 开发上下文发布候选验收报告

## 1. 报告状态

- 日期：2026-07-22
- 验收对象：ADR-0003 的当前发布候选，包括 Repomix 发布锁、激活前 retention/quarantine、codebase-memory 中断卸载 tombstone、精确正典审批评测，以及隔离 Git index 候选验收流程。
- 关联决策：[ADR-0003](../adr/0003-verifiable-ai-context-boundary.md)
- 前序证据：[初始接入报告](2026-07-22-ai-context-integration.md) 与 [安全加固报告](2026-07-22-ai-context-security-hardening.md) 是各自运行时点的历史证据，不回写为本次发布候选状态。
- 当前状态：**通过**。隔离 index 候选与恢复后的默认 index 均已完成全链路验收，主 Git index 全程保持 0 个 staged 路径。
- DeepWiki Open：继续明确为“暂不启用”；本次不得克隆、安装、运行或生成缓存。

本报告只证明运行命令时的输入集合与生成物。根/作用域 `AGENTS.md`、当前源码、测试和正式 API schema 仍是更高优先级的事实源；图谱、快照、评测和本报告不能替代它们。

## 2. 候选基线与范围

| 字段 | 冻结范围或最终实测值 |
|---|---|
| Git HEAD | `f6d97d2cbeee9389199f8c1e029eba8cab7960c2` |
| 分支 | `main` |
| 最终验收时间 | 2026-07-22 15:04:05 CST（Asia/Shanghai） |
| 操作系统 / Python / Node.js / npm | Darwin 25.5.0 arm64 / Python 3.9.6 / Node.js v26.0.0 / npm 11.12.1 |
| 主 Git index 暂存路径数 | 验收前后均为 0 |
| 工作树状态 | `--untracked-files=all` 共 102 个条目：55 modified、3 deleted、44 untracked、0 other |
| 默认 index 成员 / 批准文件 | 305 / 284 |
| 隔离 index 成员 / 批准文件 | 345 / 322 |
| 显式 untracked 例外 | 默认与隔离候选都应为空；隔离 index 通过 staged-added membership 授权 |

默认成员资格来自 Git index 中 committed 或 staged-added 的普通文件，内容来自当前 worktree 字节。隔离验收复制主 index，只 staged-add 本批 40 个精确路径；它不修改主 index。候选中的两个 `docs/test-reports/**` 路径仍被硬 deny，因此实测中 40 个 staged-added 路径使批准集合从 284 增至 322，而不是 324。本报告自身同属被排除的报告目录，但不是这 40 个候选路径之一。

### 2.1 隔离候选的 40 个精确路径

```text
.cbmignore
.codex/config.toml
.github/workflows/ai-context-full.yml
.repomixignore
backend/AGENTS.md
docs/AGENTS.md
docs/adr/0000-template.md
docs/adr/0001-local-ai-context-toolchain.md
docs/adr/0002-layered-agents-guidance.md
docs/adr/0003-verifiable-ai-context-boundary.md
docs/adr/README.md
docs/ai-assisted-development.md
docs/test-reports/2026-07-22-ai-context-integration.md
docs/test-reports/2026-07-22-ai-context-security-hardening.md
frontend/AGENTS.md
repomix.config.json
scripts/AGENTS.md
scripts/ai-context-eval.json
scripts/ai-context-inputs.py
scripts/ai-context-profiles.json
scripts/ai_tool_subprocess.py
scripts/build-ai-context.sh
scripts/code-intel-mcp-proxy.py
scripts/code-intel-native.py
scripts/code-intel-validate.py
scripts/code-intel.sh
scripts/evaluate-ai-context.py
scripts/evaluate-code-graph.py
scripts/repomix-runtime/package-lock.json
scripts/repomix-runtime/package.json
scripts/run-bounded-ai-tool.py
scripts/tests/test_ai_context_inputs.py
scripts/tests/test_ai_tool_subprocess.py
scripts/tests/test_ai_tool_supply_chain.py
scripts/tests/test_code_intel_mcp_proxy.py
scripts/tests/test_code_intel_wrapper.py
scripts/tests/test_evaluate_code_graph.py
scripts/verify-agents-guidance.py
scripts/verify-ai-context.sh
scripts/verify-ai-tool-supply-chain.py
```

以下 3 个同时存在的 untracked 后端文件不属于本次 AI 上下文候选，不得加入隔离 index：

```text
backend/app/prompts/35_chapter_prep_prompt.md
backend/tests/test_p0_p1_story_engine.py
backend/tests/test_real_flow_script.py
```

## 3. 最终执行顺序与结果

最终验收必须在本报告及相关活跃文档停止变化后按顺序执行。隔离候选 `--full` 会切换本地派生数据的活动指针，因此最后必须回到默认 index 再跑一次 `--full`，并核对主 index 未被修改。

| 顺序 | 命令或检查 | 最终结果 |
|---:|---|---|
| 1 | `python3 -m unittest discover -s scripts/tests -p 'test_*.py'` | 45 / 45 通过，9.584 秒 |
| 2 | `./scripts/verify-ai-context.sh --static` | 通过；分层规则、供应链、输入/MCP 合同、profile smoke 与忽略边界均通过 |
| 3 | 复制主 index，精确 staged-add 2.1 的 40 个路径，并在同一 `GIT_INDEX_FILE` 下运行 `./scripts/verify-ai-context.sh --full` | 通过；345 个 index 成员，322 / 322 打包，快照 4,141,781 bytes |
| 4 | 取消 `GIT_INDEX_FILE`，使用默认 index 运行 `./scripts/verify-ai-context.sh --full` | 通过；305 个 index 成员，284 / 284 打包，默认活动指针已恢复 |
| 5 | `python3 scripts/evaluate-code-graph.py` | 隔离 index hit@10 = 9 / 9、MRR = 0.456；恢复默认 index 后 hit@10 = 9 / 9、MRR = 0.569 |
| 6 | `python3 scripts/verify-agents-guidance.py` | 通过；5 个规则文件、42 个稳定规则 ID，最大可移植规则链不超过 28,672 bytes |
| 7 | `docker compose config --quiet` | 通过 |
| 8 | `git diff --cached --name-only` | 验收前、隔离验收后和默认恢复后均为 0 |

`--full` 会在最小环境中执行 `npm ci` 并可能访问 npm registry；它不是默认产品测试，也不证明宿主机处于离线状态。

## 4. 本候选新增或收紧的合同

| 控制面 | 当前合同 | 最终证据要求 |
|---|---|---|
| Repomix 发布并发 | `.ai-context/.publication.lock` 使用 PID、随机 token、当前 UID 与 inode 复验的 owner-only 目录锁，串行覆盖 build rename、bundle 验证、retention/quarantine、便利 links 和 `current.json`。有效 owner 仅在 PID 不存活时回收；创建中断留下的精确空锁或仅含 `.owner.pending.<token>` 的状态超过 5 秒 grace 后可恢复；异常状态失败关闭。 | 45 个单测中的双进程发布串行化测试通过；隔离和默认 `--full` 均通过。 |
| 激活前 retention | 先安全清理遗留 `.removing.<bundle>.<token>`，再验证保留候选，把超额旧 bundle 原子改名到 quarantine 后删除；任一不安全条目或删除失败均保留旧 `current.json`。 | 静态合同、故障注入单测和完整生成物检查通过。 |
| codebase-memory 卸载 | 经受控复验后把版本目录原子改名为 `.removing.<version>.<token>` tombstone；后续 install/uninstall 只能在名称、目录和剩余精确文件集安全时继续清理。 | wrapper 单测与静态合同通过；“可恢复”只指中断清理，不指数据恢复。 |
| 正典审批评测 | `canon_approval_boundary` 使用 `approve_canon_proposal`，真实检索目标为 `backend/app/services/studio_service.py`；不得用正文 `apply_proposal` 代替。 | 离线 9 场景 smoke 和真实 9 题检索均通过。 |
| 隔离候选输入 | 复制主 index，精确 staged-add 40 个路径；主 index 保持 0 staged，普通 untracked 不因存在于 worktree 自动获准。 | 隔离 manifest 应为 345 个 index member、322 个 approved，`explicit_untracked` 为空；最终以生成物实测回填。 |
| 默认活动状态恢复 | 隔离验收结束后使用默认 index 重跑 `--full`。 | 默认 manifest 应恢复为 305 个 index member、284 个 approved；默认图谱和 `current.json` 指向最终默认生成物。 |
| DeepWiki 边界 | 不克隆、不安装、不运行、不生成缓存，也不进入默认产品或 AI 上下文链路。 | static/full 均确认配置、依赖与缓存不存在。 |

其余固定合同继续由 ADR-0003 与安全加固报告定义：服务端固定八工具、`detect_changes` 和写能力不可达、同一安全文件描述符的密钥扫描与哈希、查询前后输入及原生二进制完整性、独立 owner-only 输入、170 包 Repomix 闭包、有界子进程、精确三文件 bundle 和快照 SHA-256 内容寻址。

## 5. 九场景检索基线

最终实测两轮均为 hit@10 = 9 / 9。隔离 index 因新增工具与文档进入候选图谱，部分同名匹配排名后移，MRR 为 0.456；恢复默认 index 后 MRR 为 0.569。

| 场景 | 期望路径 | 隔离 index 排名 | 默认 index 排名 |
|---|---|---:|---:|
| `dual_api_prefix` | `backend/app/main.py` | 1 | 1 |
| `creation_star_lane` | `backend/app/api/v1/router.py` | 6 | 5 |
| `outline_debate_lane` | `backend/app/api/v1/router.py` | 6 | 4 |
| `chapter_writing_lane` | `backend/app/agents/chapter_writing/workflow.py` | 1 | 1 |
| `batch_generation` | `backend/app/api/v1/router.py` | 7 | 6 |
| `canon_approval_boundary` | `backend/app/services/studio_service.py` | 2 | 2 |
| `frontend_outline_workbench` | `frontend/src/pages/OutlineStudioPage.tsx` | 2 | 2 |
| `frontend_proposal_apply` | `frontend/src/pages/WorkspacePage.tsx` | 2 | 2 |
| `tooling_and_ci_context` | `.github/workflows/ci.yml` | 8 | 1 |

该基线只证明固定查询的文件级 top-10 命中，不证明任意查询的 precision/recall、调用边方向、snippet 正确性或跨版本稳定性。

## 6. 最终生成物回填

### 6.1 隔离 index 候选

| 字段 | 最终实测值 |
|---|---|
| Git index member / approved | 345 / 322 |
| Explicit untracked | 空 |
| 图谱输入 inventory | `b8a3c07d2d49c0c2c01146e2d726cf392afdae520dd5f8116b9a160a1adeba35` |
| 图谱批准文件 / 输入字节 | 322 / 3,250,275 |
| 图中索引文件 / nodes / edges | 311 / 4,155 / 17,886 |
| Bundle ID | `ff96b8b78b8822fabe37e5dead9e913ce6d3a51ba534c888ee7bde5aca215b61` |
| Manifest inventory | `4fd2b42e862491ad629adbfb967690fe9594e565f4a0ed5151e8d2930ac42da7` |
| 批准 / 打包文件 | 322 / 322 |
| 批准输入字节 | 3,250,275 |
| 快照字节 | 4,141,781 |
| Snapshot SHA-256 | `62832470fd77eddc20aca156f111f03ad97b32ad6ca79f1709605c898615e8ff` |
| 活动指针（隔离验收结束时） | 图谱指向 `inputs/b8a3c07d…/files`；`current.json` 及两个便利链接指向 bundle `ff96b8b7…` 的三个实存文件 |

### 6.2 恢复后的默认 index

| 字段 | 最终实测值 |
|---|---|
| Git index member / approved | 305 / 284 |
| Explicit untracked | 空 |
| 图谱输入 inventory | `cb9d8b7c5cefd6b939f571b33b97b2e20e7ad21343acfd713a22899361d0897f` |
| 图谱批准文件 / 输入字节 | 284 / 2,745,334 |
| 图中索引文件 / nodes / edges | 277 / 3,574 / 15,411 |
| Bundle ID | `a0b2c9ebcdcf16b710a8b3fd0d84d025b2814d0e10e58337e5dfdb7c6580d3e4` |
| Manifest inventory | `6bc9f4ade914b937dd4abcb11e5132c81030d4a72a0b9156b86a4ddd8a11dd4f` |
| 批准 / 打包文件 | 284 / 284 |
| 批准输入字节 | 2,745,334 |
| 快照字节 | 3,487,623 |
| Snapshot SHA-256 | `5fd18abd497a006565d4ceb970b9e579ec15370adda42eb54e15727caf3237d6` |
| 最终规范活动指针 | 图谱指向 `inputs/cb9d8b7c…/files`；`current.json` 及两个便利链接指向 bundle `a0b2c9eb…` 的三个实存文件 |

两轮最终生成物都应继续使用 Repomix `1.17.0`、170 包闭包，并复核配置、runtime package 和 lock 哈希。由于跟踪文档和新增测试内容已经变化，不沿用早期报告或发布锁加入前的 bundle ID、inventory、输入字节、快照字节或 snapshot SHA。

## 7. 限制与发布判定

- 隔离 index 验收证明的是本批精确路径在 staged-added membership 下的候选范围，不替代提交后的干净检出验收。
- 当前工作树包含本批之外的后端改动；它们不能因隔离验证而被解释为已经纳入本次 AI 上下文候选。
- manifest/provenance 是本地完整性记录，不是数字签名或远程证明；已控制本地账户、仓库脚本、安装目录或原生二进制的攻击者不在该威胁模型内。
- Repomix 的 `npm ci` 可能联网，工具没有操作系统级网络沙箱；严格离线保证需要宿主层阻断网络后重新验收。
- 图谱仍可能出现漏边和误边，固定 9 题命中不提升图谱为事实源。
- publication lock、quarantine 和 tombstone 约束并发与中断清理，但不声称底层图数据库或多个文件拥有跨步骤事务，也不提供被删除数据恢复。

以下发布判定条件已全部满足：

1. 45 / 45 单测、static、隔离 index `--full` 和默认 index `--full` 全部通过；
2. 隔离生成物实测为 322 / 322，默认恢复生成物实测为 284 / 284，且两者 `explicit_untracked` 均为空；
3. 真实检索 hit@10 为 9 / 9，正典审批场景命中 `approve_canon_proposal` 的 service 路径；
4. 主 Git index 在验收前后都保持 0 staged；
5. 默认活动图谱和快照指针已在隔离验收后恢复；
6. DeepWiki 仍无活跃依赖、配置或缓存。

当前结论：**本轮 AI 开发上下文发布候选通过。默认活动状态已恢复，DeepWiki Open 仍保持禁用。**
