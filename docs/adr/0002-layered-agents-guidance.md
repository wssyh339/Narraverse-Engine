# ADR-0002：采用分层 AGENTS 项目规范

- 状态：Accepted
- 日期：2026-07-22
- 决策者：项目维护者
- 影响范围：Codex 项目规则发现、后端/前端/脚本/文档开发约束和 CI 静态验证

## 背景

原根 `AGENTS.md` 已达到 32,043 字节，距离 Codex 默认 32 KiB 合并上限只剩 725 字节。继续把所有后端、前端、部署和 AI 工具细节集中在单一文件中，会增加截断、重复和跨域规则漂移风险。

Codex 在每次运行开始时，从项目根沿当前工作目录发现规则；从仓库根启动后再打开 `backend/` 文件，并不会动态加载嵌套规则。因此，单纯把正文移动到子目录会让根启动的跨栈任务漏读约束。

## 决策

采用五文件混合渐进式结构：

```text
AGENTS.md
backend/AGENTS.md
frontend/AGENTS.md
scripts/AGENTS.md
docs/AGENTS.md
```

- 根文件只保留全局不可削弱的版本、产品、安全、非目标、确认门、验证基线和路径路由。
- 四个作用域文件分别拥有后端、前端、脚本/运维、文档细则。
- 根路由要求从仓库根启动的 Agent 在接触目标路径前显式完整读取对应作用域文件；跨栈任务读取多个作用域。
- 每条规则使用稳定 ID，跨文档引用“文件路径 + 规则 ID”，不再依赖章节号。
- 作用域规则只能细化根基线，不能放宽根级版本、安全、作者审批、非目标或变更确认门。
- 暂不继续拆分 `backend/app/agents/`：三条 Agent 线横跨 agents、services 和 endpoints，过深的目录规则会形成错误所有权。

`.codex/config.toml` 设置 `project_doc_max_bytes = 65536` 作为可信项目的容量兜底，并显式禁用 fallback 文件名。但内容预算仍按未信任新 clone 的默认限制设计：根文件最多 12 KiB，任一有效根到作用域链最多 28 KiB。

`scripts/verify-agents-guidance.py` 以纯标准库模拟规则发现，拒绝未登记文件和 `AGENTS.override.md`，检查路由、链预算和规则 ID 唯一性。CI 必须运行该静态合同。

## 后果

### 正向影响

- 根任务只常驻全局基线，专项任务按目录加载必要细则。
- 在项目配置未被信任或未生效时，所有有效链仍低于默认 32 KiB。
- 稳定规则 ID 降低章节重排造成的引用漂移。
- 后端、前端、工具和文档规则有明确所有者，合同测试可以验证真实路由而不是要求根文件复制全部细节。

### 成本与风险

- 从仓库根启动的 Agent 必须遵守显式路由；Codex 不会因稍后打开文件自动补载子规则。
- 跨栈任务需要读取多个作用域文件。
- 新增作用域时必须同步根路由、验证器和 ADR，否则静态合同失败。
- `project_doc_max_bytes` 只在受信任项目配置加载后生效，不能替代 28 KiB 的可移植内容预算。

## 备选方案

- 继续维护单一根文件：已接近默认上限，拒绝。
- 仅创建嵌套文件、不保留根路由：根启动任务会漏读，拒绝。
- 立即细分到 `backend/app/agents/`：当前工作流跨越多个代码目录，会制造错误作用域，暂缓。
- 把全部规范放到普通 `docs/`：不会自动进入 Codex instruction chain，也弱化规则与说明文档的区别，拒绝。

## 验证方式

```bash
python3 scripts/verify-agents-guidance.py
python3 -m pytest backend/tests/test_agents_three_lanes_contract.py -q
cd frontend
node --test tests/frontend-contract.test.mjs
```

验证器必须证明五个活跃文件集合精确匹配、根路由完整、无 override、稳定规则 ID 唯一，并且根及四条有效链都低于预算。

安装 Codex 的本地环境还可运行 `python3 scripts/verify-agents-guidance.py --runtime`，直接比较 Codex 实际合并内容；该 smoke 不进入普通 CI。

## 关联

- 相关稳定规则：根 `GLOBAL-DISCOVERY-001`、`GLOBAL-CHANGE-GATE-001`；`scripts/AGENTS.md` 的 `OPS-GUIDANCE-001`
- Codex 官方说明：https://developers.openai.com/codex/guides/agents-md
- 静态验证：`scripts/verify-agents-guidance.py`
- 架构说明：`docs/architecture.md`
- 取代的 ADR：无
- 被取代于：无
