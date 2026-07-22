# 架构决策记录（ADR）

本目录保存已经人工讨论和审阅的架构决策。ADR 与 `docs/architecture.md` 共同记录稳定的设计意图；源码、测试和正式 API schema 证明实现事实，根 `AGENTS.md` 与适用的作用域规则构成项目约束。

代码图谱、Repomix 快照或未来的自动 Wiki 只能帮助发现问题，不能自动创建、接受、修改或替代 ADR。

## 状态

- `Proposed`：提案，尚未成为项目约束。
- `Accepted`：已经确认并正在生效。
- `Superseded`：被后续 ADR 取代，保留供追溯。
- `Rejected`：经过讨论但未采纳。

## 维护流程

1. 复制 `0000-template.md`，使用下一个四位编号和简短英文文件名。
2. 写清背景、决策、边界、后果和可验证证据。
3. 涉及新增功能、依赖、目录、接口、数据表或部署方式时，必须先更新拥有该事项的稳定规则 ID；作用域变化还要更新根路由，并获得确认。
4. 由人审阅后再把状态改为 `Accepted`，同时更新本索引和必要的架构文档。
5. 决策变化时新增 ADR，并把旧 ADR 标记为 `Superseded`；不要改写历史。

## 索引

| ADR | 状态 | 决策 |
|---|---|---|
| [0001](0001-local-ai-context-toolchain.md) | Superseded | 初始采用本地、只读、分层的 AI 开发上下文工具链；已由 ADR-0003 取代。 |
| [0002](0002-layered-agents-guidance.md) | Accepted | 采用根基线、作用域规则和显式路由组成的渐进式项目规范。 |
| [0003](0003-verifiable-ai-context-boundary.md) | Accepted | 采用可验证输入代际、服务端固定八工具和锁定 Repomix 供应链。 |
