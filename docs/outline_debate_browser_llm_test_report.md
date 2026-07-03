# 大纲议事 6 Agent 真实浏览器 + DeepSeek LLM 压测报告

测试日期：2026-06-30

## 测试范围

- 前端：Vite 浏览器页面 `http://127.0.0.1:5176/`
- 后端：FastAPI `http://127.0.0.1:8010/api`
- 数据库：独立测试库 `data/outline_debate_browser_llm_test.sqlite`，未污染日常开发库
- LLM：复用现有 `LLM_PROVIDER=deepseek` / `deepseek-v4-flash`，后端以 `LLM_REQUIRE_REMOTE=true` 启动
- 规模：10 个不同题材；每个题材 book、volumes、chapters 三阶段；chapters 阶段要求 2 卷，每卷 50 章，共 100 章
- 浏览器证据：前端成功加载项目首页；修正 API base 后可读取后端项目列表；切换测试库后首页显示空库状态

## 产物位置

- 原始输出目录：`test-artifacts/outline_debate_browser_llm_20260630T021653Z`
- 汇总 JSON：`test-artifacts/outline_debate_browser_llm_20260630T021653Z/summary.json`
- 逐阶段讨论日志 JSONL：`test-artifacts/outline_debate_browser_llm_20260630T021653Z/raw_discussion_log.jsonl`
- 每个题材阶段输出：`test-artifacts/outline_debate_browser_llm_20260630T021653Z/case_XX_book.json`、`case_XX_volumes.json`、`case_XX_chapters.json`
- 批量测试脚本：`test-artifacts/run_outline_debate_browser_llm_tests.py`

## 10 个题材结果

| # | 题材 | 项目 | book turns | volumes turns | chapters turns | 章数 | 分卷 | 结论 |
|---:|---|---|---:|---:|---:|---:|---|---|
| 1 | 东方玄幻升级流 | 浏览器LLM压测-01-碎星炉-20260630T021653Z | 6 | 5 | 5 | 100 | {'1': 50, '2': 50} | 通过 |
| 2 | 都市悬疑探案 | 浏览器LLM压测-02-第七盏路灯-20260630T021653Z | 6 | 4 | 4 | 100 | {'1': 50, '2': 50} | 通过 |
| 3 | 赛博朋克群像 | 浏览器LLM压测-03-霓虹债主-20260630T021653Z | 6 | 6 | 6 | 100 | {'1': 50, '2': 50} | 通过 |
| 4 | 古代权谋女强 | 浏览器LLM压测-04-玉阶雪-20260630T021653Z | 6 | 4 | 4 | 100 | {'1': 50, '2': 50} | 通过 |
| 5 | 轻科幻殖民星球 | 浏览器LLM压测-05-潮汐宪章-20260630T021653Z | 6 | 4 | 5 | 100 | {'1': 50, '2': 50} | 通过 |
| 6 | 现言娱乐圈成长 | 浏览器LLM压测-06-热搜之外-20260630T021653Z | 6 | 4 | 4 | 100 | {'1': 50, '2': 50} | 通过 |
| 7 | 诡异规则怪谈 | 浏览器LLM压测-07-夜班守则-20260630T021653Z | 6 | 6 | 6 | 100 | {'1': 50, '2': 50} | 通过 |
| 8 | 西幻冒险公路文 | 浏览器LLM压测-08-风暴邮差-20260630T021653Z | 6 | 4 | 4 | 100 | {'1': 50, '2': 50} | 通过 |
| 9 | 历史架空商战 | 浏览器LLM压测-09-盐铁余烬-20260630T021653Z | 6 | 6 | 6 | 100 | {'1': 50, '2': 50} | 通过 |
| 10 | 校园青春轻悬疑 | 浏览器LLM压测-10-借光社-20260630T021653Z | 6 | 4 | 4 | 100 | {'1': 50, '2': 50} | 通过 |

## 真实 LLM 观察

1. 10 个题材全部完成远程 DeepSeek 调用，没有触发本地降级。
2. 每个 chapters 阶段均输出 100 个章纲候选，且分卷为第 1 卷 50 章、第 2 卷 50 章。
3. 动态议事席位符合 6 Agent 约束：只出现主持总策划、类型卖点、结构医生、角色生成、设定生成、连续性审计。
4. 候选门槛生效：部分题材的 volumes/chapters 阶段只触发 4 个核心审查席位，没有强行让角色/设定席位制造候选。
5. DeepSeek 对新增 `decision/scores` 契约遵守不稳定：部分 Agent 给出完整评分，部分 Agent 漏字段。

## 测试中发现的问题

1. 前端启动时 `VITE_API_BASE_URL` 若配置为 `http://127.0.0.1:8010`，会请求 `/projects` 并 404；必须使用 `http://127.0.0.1:8010/api`。
2. HTTP API 有统一 `{success, data}` 包装，测试脚本一开始按服务层裸返回解析，导致 `KeyError('id')`。
3. 测试脚本最初读取 `_llm.remote`，真实字段是 `_llm.used_remote_model`。这会误判远程状态。
4. 真实 LLM 不稳定遵守 `decision/scores` 输出契约，需要服务层兜底，否则前端仪表盘和日志会出现空裁决/空评分。
5. 运行时 task 提醒仍残留旧规则“凡发现未入库新对象都必须给出档案”，与候选触发门槛冲突。
6. 浏览器控制工具的页面只读执行环境不能直接使用 `fetch`/`XMLHttpRequest`，批量 API 调用改由本地 HTTP 客户端执行；浏览器用于真实 UI 连通性验证。
7. 浏览器全页截图和最终刷新检查两次超时，说明这类长页面/长会话不适合用全页截图作为批量验收证据，应优先使用 DOM 摘要和 API 结构化结果。

## 已完成的二次修改

1. `backend/app/services/outline_debate_service.py`
   - 将运行时 task 提醒改为：角色/设定 Agent 必须先输出功能审计，只有达到候选触发门槛才生成待确认档案。
   - 对真实 LLM 路径也启用 `decision` 和 `scores` 服务层兜底，不再只对 `local_preview` 生效。
   - 保留真实模型输出优先；只有模型漏字段或空字段时才使用默认裁决/评分。

2. `test-artifacts/run_outline_debate_browser_llm_tests.py`
   - 增加统一 `{success, data}` 响应解包。
   - 修正项目 id 获取逻辑。
   - 将远程判断字段改为 `_llm.used_remote_model`。

## 修改后 smoke 验证

- 使用新代码重启后端，执行 1 个 book 阶段远程 smoke。
- 结果：`StoryDirectorAgent` 与 `CharacterGeneratorAgent` 均 `used_remote_model=true`。
- 结果：两个 turn 均有 `decision=revise`，且 `scores` 字段被补齐。

## 新的修改建议

1. 建议前端/启动脚本显式校验 `VITE_API_BASE_URL` 必须包含 `/api`，否则首页给出“API 前缀错误”而不是泛化“无法连接后端”。
2. 建议在阶段结果中加入 `score_source=model|service_default`，区分模型主动评分和服务层兜底评分。
3. 建议把 `_llm.used_remote_model`、`provider`、`model` 显示到 Agent 运行详情里，避免真实/本地降级状态只能查 JSON。
4. 建议对远程 LLM 的 JSON 契约增加二次修复统计面板：`parsed`、`repair_attempted`、`repair_succeeded`、`validation_warnings`。
5. 建议为大纲议事增加“全量 100 章生成耗时/成本预估”提示；本轮 10 个题材耗时很长，用户需要运行前知道成本和时间。
6. 建议后续将 browser 批量测试做成专门的前端测试页或按钮，而不是依赖浏览器控制工具在页面内发起 HTTP。

## 结论

本轮真实浏览器连通性与真实 DeepSeek LLM 压测完成。10 个题材均成功生成两卷、每卷 50 章的章纲内容，并保存了完整讨论日志和阶段输出。测试发现的问题已经完成关键代码修复；剩余建议主要是前端可观测性、启动配置提示和成本/耗时提示。