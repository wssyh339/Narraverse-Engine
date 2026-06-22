# 架构说明

叙界推演引擎 / Narraverse Engine 的核心产品原则是：

> 长篇小说生成必须是状态化、可追踪、可审查、由作者确认的。

因此，系统把立项、大纲推演、章节写作、正典管理和前端呈现拆成相对独立的层。

## 系统层级

```mermaid
flowchart TD
  Web["React Studio UI"] --> API["FastAPI API 层"]
  CLI["Python CLI"] --> Services["应用服务层"]
  API --> Services
  Services --> Agents["Agent 三线"]
  Services --> DB["SQLite 持久化"]
  Services --> Export["导出器"]
  Agents --> LLM["统一 LLM Client"]
  LLM --> Providers["OpenAI / DeepSeek / Qwen / 兼容接口"]
  Agents --> Canon["Canon Context 构建器"]
  Canon --> DB
```

## Agent 三线

### 创作 Star

路径：`backend/app/agents/creation_star/`

职责：

- 生成项目立项候选；
- 抽取世界观、主角、卖点、书名等候选卡；
- 生成核心矛盾、小说宪法和正典预览；
- 只在用户确认后提交正式正典。

这一条线在卡片生成阶段不得直接覆盖用户正典。

### 大纲议事引擎

路径：`backend/app/services/outline_debate_service.py`

接口：`backend/app/api/v1/endpoints/outline_debate.py`

职责：

- 以回合制实时议事推演长篇总纲、逐卷卷纲和逐章章纲；
- 让多个大纲 Agent 逐条发言、交接、接收用户插话和打断；
- 从项目状态、故事圣经、canon context 和已确认大纲读取上下文；
- 每个阶段都产出可确认候选，用户确认后才写入正式大纲与正典。
- 长篇章纲可通过 `chapters/autopilot` 创建后台 parent job，按单章讨论、单章确认、单章正典更新的顺序推进，并由任务接口显示进度。

大纲线应该读取立项种子、故事圣经、canon context、角色、实体、世界观事实和已有大纲。

### 章节写作

路径：`backend/app/agents/chapter_writing/`

职责：

- 构建章节 canon context；
- 生成情节、对话、环境和整合稿；
- 执行审校、事实核查、质量门、修订、风格统一和正典更新；
- 保存 Agent 轨迹和版本快照。

## 正典模型

系统使用关系型表模拟图结构，而不是默认依赖外部图数据库：

- characters：角色卡；
- story entities：剧情实体、地点、组织、物件、线索；
- world facts：世界观事实；
- graph nodes：图节点；
- graph edges：图边；
- foreshadowing items：伏笔；
- continuity issues：连续性问题；
- version snapshots：版本快照。

这样可以保持本地启动简单，同时支持关系图谱渲染和连续性检查。

## 人工确认提交流程

多数 AI 工作流都遵循这个形状：

```mermaid
sequenceDiagram
  participant U as 作者
  participant UI as Web UI
  participant API as FastAPI
  participant A as Agent 线
  participant DB as SQLite

  U->>UI: 请求生成
  UI->>API: 提交上下文和指令
  API->>A: 运行 Agent 工作流
  A->>API: 返回结构化预览
  API->>UI: 展示卡片、diff 或正典候选
  U->>UI: 确认或编辑
  UI->>API: 提交确认结果
  API->>DB: 写入正式状态和快照
```

## 竞争力来自哪里

- 把 AI 输出视为结构化状态，而不是一次性文本。
- 允许作者检查和编辑推理链。
- 支持需要长期连续性的长篇项目。
- 本地优先，部署依赖相对轻。
- 把提示词工程、图状态和写作 UI 结合成可运行系统。
