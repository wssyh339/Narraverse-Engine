# 长篇小说撰写 Agent Studio 1.0

本项目是本地优先的 AI 小说创作工作室，包含 FastAPI 后端、React Web 前端、Python CLI 和 LangGraph 多 Agent 写作工作流。

## 核心能力

- 11 个工作室 Agent：总策划、章节规划、情节叙事、人物对话、环境描写、审核修改、风格统一、事实核查、整合输出、设定整理、创作 Star。
- 13-Agent 长篇大纲推演系统：总编统筹、一句话故事扩展、类型卖点定位、世界圣经、主角成长、人物树、势力冲突、金手指升级、全书结构、卷级大纲、章节节拍、伏笔管理、逻辑审计。
- 正典补全推演系统：从“已有世界观 + 一句话故事”开始，执行 Why 追问、实体抽取、S/A 级实体补全、正典合并、连续性审查，并生成 `final_outline.md` 与 `canon_store.json`。
- LangGraph 工作流：初始化项目、章节规划、单章正文、批量生成。
- 动态设定集：角色卡、剧情实体、实体物件、世界观事实、图节点、图边、连续性问题持续更新。
- 设定前置编辑：可在写正文前手动维护角色卡、世界观事实、地点/组织/物件/线索，并让 Agent 辅助生成候选设定。
- 伏笔管理：支持预埋、状态追踪、Agent 建议、回收标记和图谱关联。
- 工作流图：Agent 配置中心展示初始化、章节规划、单章正文和批量生成流程，点击节点可编辑提示词或说明。
- 版本系统：Agent 自动快照、diff 对比、回滚、分支。
- 章节 Chat 协作：基于 `assistant-ui` 外壳和 FastAPI SSE 接口，支持选区上下文、流式局部修改建议和确认后应用到选区。
- Web 工作台：Dashboard、项目创建/删除、写作工作台、Agent 配置、版本、角色、图谱、世界观、伏笔、批量生成、导出。
- CLI 入口：保留命令行创建、恢复、生成、查询、导出能力。
- 导出：Markdown、TXT、HTML、PDF、EPUB、Word 本地文件。

## 技术栈

- 后端：Python 3.10+、FastAPI、LangGraph、LangChain OpenAI、SQLAlchemy、SQLite、pydantic v2。
- 前端：React 18、TypeScript、Vite、Ant Design、assistant-ui、Zustand、React Router、Axios、ECharts、Markdown Editor。
- 部署：Docker Compose。

## 结构约定

后端 API 路由按领域拆分在 `backend/app/api/v1/endpoints/` 下，`backend/app/api/v1/router.py` 只负责挂载：

- `backend/app/api/v1/endpoints/project_studio.py`：项目、状态、故事圣经和章节读写。
- `backend/app/api/v1/endpoints/agents.py`：Agent、创作 Star、提示词模板和工作流图。
- `backend/app/api/v1/endpoints/knowledge.py`：角色、实体、世界观事实和图谱。
- `backend/app/api/v1/endpoints/foreshadowing.py`：伏笔预埋、编辑、删除和回收。
- `backend/app/api/v1/endpoints/writing.py`：写作任务、批量任务、暂停恢复取消和 Agent 轨迹。
- `backend/app/api/v1/endpoints/versions.py`：版本列表、diff、回滚和分支。
- `backend/app/api/v1/endpoints/canon.py`：正典补全、canon context、final_outline 与 canon_store。
- `backend/app/api/v1/endpoints/tools.py`：摘要、事实核查、一致性检查、风格学习和知识查询。
- `backend/app/api/v1/endpoints/exporting.py`：导出和导出模板。

`backend/app/api/v1/endpoints/studio.py` 保留为 legacy compatibility facade，避免一次性迁移破坏已有调用；新增接口不要继续堆到这个文件。

前端大纲工作台采用薄页面编排：`frontend/src/pages/OutlineStudioPage.tsx` 只管理页面状态和数据流，具体 UI 拆在 `frontend/src/pages/outline/`：

- `OutlineDirectory.tsx`：大纲目录、卷章层级、删除和批量删除。
- `OutlineEditorPanel.tsx`：总纲、卷纲、章节、章纲编辑区。
- `OutlineGenerationModal.tsx`：长篇大纲/卷纲/章纲生成参数弹窗。
- `OutlineInferenceGraph.tsx`：13-Agent 实时推演过程。
- `CanonStudioPanel.tsx`：正典补全、下载 `final_outline.md` 和 `canon_store.json`。

## Agent 三线架构

- `backend/app/agents/creation_star/`：抽卡式立项，只生成候选设定，用户确认后写入正式项目。
- `backend/app/agents/outline_swarm/`：大纲生成与世界构建，使用 `langgraph-swarm==0.1.0` 做 `active_agent` 动态路由和有限循环；每个节点通过 `OutlineSwarmAgentRunner` 加载 `backend/app/prompts/*.md` 并调用统一 `llm_client`，无 API Key 时使用同 schema 的本地降级结果；节点只使用用户立项种子与正典上下文，不硬编码示例故事。
- `backend/app/agents/chapter_writing/`：章节正文生成，使用稳定 LangGraph StateGraph 和质量门修订循环。

现有 `backend/app/agents/workflow.py`、`outline_workflow.py`、`canon_workflow.py` 先保留为 legacy compatibility 入口；新增 Agent 逻辑优先进入三条线目录。

## Python 虚拟环境

推荐在项目根目录使用独立 `.venv`，避免把依赖安装到 `conda base` 或系统 Python 中。

创建并安装后端依赖：

```bash
cd /Users/mac/Documents/长篇小说撰写agent
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

如果不想激活虚拟环境，也可以始终显式使用 `.venv/bin/python`：

```bash
.venv/bin/python -m pip install -r backend/requirements.txt
```

当前已验证环境：

- Python：`3.13.13`
- 解释器：`.venv/bin/python`
- 依赖文件：`backend/requirements.txt`

## 环境变量

复制模板：

```bash
cp .env.example .env
```

常用配置：

```bash
LLM_PROVIDER=qwen
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

没有 API Key 时，系统仍可用本地规则化输出跑通工作流；远程模型调用结果会标记为未使用远程模型。

## 本地启动

建议开两个终端：一个跑后端，一个跑前端。

### 1. 首次安装依赖

后端：

```bash
cd /Users/mac/Documents/长篇小说撰写agent
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

前端：

```bash
cd /Users/mac/Documents/长篇小说撰写agent/frontend
export PATH="/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
node ../.codex-tools/pnpm-11.5.1/bin/pnpm.cjs install
```

### 2. 启动后端

在终端 1 运行：

```bash
cd /Users/mac/Documents/长篇小说撰写agent
source .venv/bin/activate
DATABASE_URL=sqlite:///./backend/data/novel_agent.db \
JOB_ARTIFACT_DIR=backend/artifacts/runs \
FRONTEND_ORIGIN=http://localhost:5173 \
python -m uvicorn --app-dir backend app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 启动前端

在终端 2 运行：

```bash
cd /Users/mac/Documents/长篇小说撰写agent/frontend
export PATH="/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
VITE_API_BASE_URL=http://localhost:8000/api \
node ../.codex-tools/pnpm-11.5.1/bin/pnpm.cjs dev
```

访问：

- 前端：`http://localhost:5173`
- API 文档：`http://localhost:8000/docs`
- API 示例：`http://localhost:8000/api/projects`

如果 Vite 提示 `Port 5173 is in use` 并自动切到 `5174`，最简单的处理是关闭占用 5173 的旧前端服务后重启前端。也可以把后端启动命令中的 `FRONTEND_ORIGIN` 改成实际端口，例如 `http://localhost:5174`。

如果看到 `ModuleNotFoundError: No module named 'app'`，请确认后端启动命令是在项目根目录运行，并保留了 `--app-dir backend`。

### 常用命令

```bash
cd /Users/mac/Documents/长篇小说撰写agent
source .venv/bin/activate
python -m pytest backend/tests -q

cd /Users/mac/Documents/长篇小说撰写agent/frontend
export PATH="/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
node ../.codex-tools/pnpm-11.5.1/bin/pnpm.cjs test
node ../.codex-tools/pnpm-11.5.1/bin/pnpm.cjs build
```

## Docker 启动

```bash
cp .env.example .env
docker compose up --build
```

## CLI

先启用虚拟环境，再从项目根目录运行：

```bash
source .venv/bin/activate
python main.py new
python main.py resume
python main.py plan --count 3
python main.py generate-chapter --chapter-no 1
python main.py versions
python main.py character_map
python main.py query "谁是主角？"
python main.py export --format markdown
```

13-Agent 长篇大纲推演系统使用本地 `workspace/story_state.json`，不依赖数据库项目：

```bash
source .venv/bin/activate
python main.py init --name "长篇推演项目" --genre "都市脑洞" --tone "搞笑腹黑"
python main.py set-input --worldview worldview.txt --story "林缺用反常识操作让怪谈规则破防。"
python main.py run-full
python main.py run-stage S7
python main.py run-volume 1
python main.py audit
python main.py export --outline --format markdown
```

大纲推演默认目标为 100 万字、10 卷、每卷 50 章、每章约 2000 字。`run-full` 会生成故事核心、类型卖点定位、世界圣经、主角成长线、人物树、势力冲突表、金手指升级体系、全书 10 卷总纲、逐卷 50 章大纲、章节节拍表、伏笔账本、逻辑审计报告和最终修订版纲要。

Markdown 导出目录默认为 `workspace/exports/`，固定生成：

```text
01_故事核心.md
02_类型卖点定位.md
03_世界圣经.md
04_主角成长线.md
05_人物树.md
06_势力冲突表.md
07_金手指升级体系.md
08_全书10卷总纲.md
09_逐卷50章大纲.md
10_章节节拍表.md
11_伏笔账本.md
12_逻辑审计报告.md
13_最终修订版纲要.md
```

正典补全推演系统用于从已有世界观和一句话故事生成正式正典库、DramaNode 节点表、连续性审查报告和最终总纲。示例输入：

```json
{
  "project_id": "sample_novel_001",
  "worldview": "帝国依靠龙骨能源维持工业文明。",
  "one_sentence_story": "一个低等矿工发现自己体内封印着最后一条真龙。",
  "genre": "奇幻 / 工业幻想",
  "target_length": "长篇，多卷结构",
  "tone": "沉重、史诗、成长"
}
```

运行：

```bash
source .venv/bin/activate
python main.py canon-run --input data/sample_input.json --output outputs/final_outline.md
# 等价兼容入口：
python cli.py --input data/sample_input.json --output outputs/final_outline.md
```

输出：

```text
outputs/final_outline.md
outputs/canon_store.json
outputs/<project_id>/trace_store.json
outputs/<project_id>/version_store.json
```

Web 端也可以在项目内进入“大纲”页面，使用“正典补全”区域输入世界观和一句话故事，运行后查看 Agent handoff、正典库实体表、实体补全状态表、DramaNode 故事节点图、ContinuityAgent 审查结果，并下载 `final_outline.md` 与 `canon_store.json`。

项目内“大纲”页面调用 `POST /api/projects/{id}/chapters/plan` 时，后端会保留旧 13-Agent 大纲结构输出，同时附加 `outline_swarm` 字段；前端“实时推演过程”优先读取 `outline_swarm.agent_trace`，展示 `StoryDirectorAgent`、`WhyInterrogatorAgent`、`WorldSettingAgent`、`CharacterArcAgent`、`ConflictAgent`、`PlotArchitectAgent`、`BeatControllerAgent`、`ForeshadowingAgent`、`EntityExtractorAgent`、`ContinuityAgent` 的真实调用轨迹和本地降级/远程模型元数据。该接口还会把 10 个 Swarm 节点以 `outline_swarm/<AgentName>` 写入 `agent_runs`，因此任务详情页可以和旧 13-Agent 链路一起查看完整 23 步执行记录。

也可在 `backend/` 目录运行：

```bash
python main.py resume
```

## 验证

测试和构建命令见“本地启动”里的“常用命令”。

已验证的核心流程：

1. 创建项目。
2. 生成章节规划。
3. 生成单章正文。
4. 查询 Agent 运行轨迹。
5. 提前创建/编辑角色卡、剧情实体、实体物件和世界观事实。
6. 使用 Agent 辅助生成候选设定。
7. 创建、编辑、回收、删除伏笔，并调用 Agent 伏笔建议。
8. 查看 Agent 工作流图并编辑提示词。
9. 删除项目并确认列表刷新。
10. 查看图谱节点。
11. 查看版本快照、对比差异并回滚版本。
12. 重复创建批量任务，并验证暂停、恢复、取消状态控制。
13. 导出 Markdown 和 TXT。
14. 停止后端并确认前端显示友好的不可用提示。

## 仍然不做

- 不做登录注册、权限、多用户协作。
- 不做支付订阅。
- 不做在线发布平台或自动投稿。
- 不默认引入 Neo4j 或复杂向量数据库。
- 不让前端直接接触 LLM API Key。
