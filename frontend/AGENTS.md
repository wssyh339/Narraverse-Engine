# 前端作用域规范

> 适用于 `frontend/**` 和前端 Dockerfile。本文件与根 `AGENTS.md` 同时生效；跨前后端任务还必须读取 `backend/AGENTS.md`。

## FRONTEND-STACK-001：运行时与依赖

实际依赖以 `frontend/package.json` 和 `frontend/pnpm-lock.yaml` 为准。

| 技术 | 当前锁定 |
|---|---:|
| Node.js | 24.14.0 |
| pnpm | 11.5.1 |
| React | 18.3.1 |
| TypeScript | 5.9.3 |
| Vite | 7.2.7 |
| Ant Design | 5.27.6 |
| @assistant-ui/react | 0.14.14 |
| react-router-dom | 6.30.2 |
| @tanstack/react-query | 5.100.14 |
| Zustand | 5.0.8 |
| Axios | 1.13.2 |
| ECharts | 6.0.0 |
| lucide-react | 1.17.0 |

- 前端默认 API 地址为 `http://localhost:8000/api`；不得把双前缀合约误改成只支持 `/api/v1`。
- API Key 只能由后端从环境变量读取，前端不得读取、保存、转发或把 Key 编译进 `VITE_*` 变量。
- 新增或升级依赖必须遵守 `GLOBAL-CHANGE-GATE-001`，并同步 package manifest、lockfile 和版本说明。

## FRONTEND-STUDIO-001：统一创作工作室

前端必须保持统一的项目级创作工作室，而不是多个割裂管理页。项目路由共享当前项目、当前章节、当前卷和当前正典上下文。

工作室必须提供：

- 项目列表和项目创建。
- 创作 Star。
- 正文工作台。
- 大纲议事工作台。
- 设定工作台。
- 作品资料。
- 角色、世界观、图谱和伏笔。
- 笔记。
- 已有小说导入、Method Pack、对标资产和审稿计划。
- Agent 配置。
- 版本。
- 批量任务。
- 导出。

项目首页“创建新项目”必须先创建本地草稿项目，再进入创作 Star 向导。创作 Star 默认使用 `creation/sessions` 分步接口；旧 draw/commit 仅作兼容，不得重新成为默认流程。

## FRONTEND-OUTLINE-001：大纲工作台

大纲前端拆分必须保持：

- `frontend/src/pages/OutlineStudioPage.tsx`：页面编排、URL 参数、React Query、选择状态和 mutation 组合。
- `frontend/src/pages/outline/`：大纲目录、编辑器、议事面板、规模规划和批量选择等子模块。

`OutlineDebatePanel` 是正式议事流的唯一前端展示入口，必须支持：

- 逐字流式输出。
- 用户加入讨论和 `@` 运行时席位。
- 打断、逐阶段确认和正式提交。
- 在议事流中展示拓扑等结构化证据。

不得恢复历史推演图组件，也不得把拓扑重新变成独立的大纲生成入口。确认按钮必须遵守后端质量证据和阻塞状态，不能绕过正式议事与正典物化边界。

## FRONTEND-APPROVAL-001：AI 编辑与正典审批

AI 编辑操作必须遵循：

```text
生成提案
  -> 展示差异
  -> 用户确认
  -> 应用前快照
  -> 写入正文
```

章节 Chat 选区修改流程为：

```text
选中文本
  -> 输入修改要求
  -> 流式生成建议
  -> 用户点击应用到选区
  -> 自动保存并保留快照
```

- 流式生成阶段不得直接写正文。
- 设定更新必须遵循“候选变更 → 用户审批 → 写入设定集”。
- 导入报告、Method Pack、对标资产和审稿计划只能作为参考上下文，不能在前端直接覆盖正文或正典。
- 即使后端启用 Deep Agent 写能力，前端仍必须呈现并保留提案或候选审批边界。

## FRONTEND-API-001：API 类型与状态

- API wrapper、TypeScript 类型和页面消费方必须与后端正式 schema 同步。
- 长任务必须展示真实 parent/child job 状态、进度、当前章节、失败与重试上下文，不得用前端假进度替代。
- 页面级状态优先留在对应页面/React Query；只有确实跨路由共享的项目、章节、卷或正典上下文才进入全局状态。
- API 路径或响应结构变化属于公共接口变更，必须同时遵守 `GLOBAL-CHANGE-GATE-001` 和 `BACKEND-API-001`。

## FRONTEND-VERIFY-001：前端验证

默认验证：

```bash
cd frontend
pnpm test
pnpm build
```

修改页面、API wrapper、类型或工作室状态时先运行对应 contract test，再运行完整前端测试和构建。Docker 模式下修改 `VITE_*` 变量后必须重新构建前端镜像。
