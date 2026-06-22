# 2026-06-21 大纲动态议事与真实 LLM 测试报告

## 目标

验证大纲议事改造后的三项要求：

- 议事不再按固定 Agent 顺序机械发言。
- `CharacterGeneratorAgent` 与 `SettingGeneratorAgent` 可在发现新角色/新设定后立即插入。
- 只要讨论中出现未入库角色或设定，就生成对应候选；同名变体和谓词短语不得误生成重复候选。

## 实现要点

- 调度从固定 `DEBATE_AGENTS` 遍历改为动态 next-agent 选择。
- 用户 `@` 指定角色仍最高优先级。
- 新角色/新设定信号会优先插入角色生成器或设定生成器。
- 候选策略从“明确缺口才生成”改为“未入库新对象出现即生成”。
- 支持同阶段多个 `character_candidate` / `setting_candidate` artifact。
- 名称去重会忽略空白、中点、连接符和常见标点。
- 文本抽名收紧为引号或冒号形式，避免把“陆闻是审判执行者”这类谓词句误当成名称。
- 真实 LLM JSON 解析失败时增加一次远程 JSON 修复重试；仍失败才报错。

## 自动化验证

命令：

```bash
pytest backend/tests/test_outline_debate_engine.py -q -k "text_name_extraction or dedupe_ignores or not real_llm"
pytest backend/tests/test_agent_prompt_runtime_contract.py -q
pnpm --dir frontend test
```

结果：

- `backend/tests/test_outline_debate_engine.py`: 22 passed, 1 deselected.
- `backend/tests/test_agent_prompt_runtime_contract.py`: 12 passed.
- `frontend` contract tests: 32 passed.

## 真实 LLM 模拟

Provider: `deepseek`

Model: `deepseek-v4-flash`

请求目标：

```text
请简短讨论总纲。总纲中必须出现新角色“药契监察使陆闻”和新设定“星炉药契审判场”，如果它们未在正典中生成过，请立即生成候选。每位 Agent 只输出一到两句。
```

最终真实 LLM 运行结果：

```json
{
  "project_id": "prj_60f75e39c53b4b37b3ed650928",
  "session_id": "odb_64d1a6651b1948f788c1c008db",
  "turn_agents": [
    "outline_debate/StoryDirectorAgent",
    "outline_debate/CharacterGeneratorAgent",
    "outline_debate/SettingGeneratorAgent",
    "outline_debate/MarketPositionAgent",
    "outline_debate/StructureDoctorAgent",
    "outline_debate/ContinuityAuditorAgent"
  ],
  "artifact_titles": [
    "总纲候选",
    "药契监察使陆闻",
    "星炉药契审判场"
  ],
  "character_candidate_count": 1,
  "setting_candidate_count": 1,
  "status": "succeeded",
  "candidate_status": "pending_confirmation"
}
```

LLM 元数据结论：

- 6 个 Agent turn 均使用远程模型。
- 6 个 Agent turn 均解析为 JSON。
- `StoryDirectorAgent` 首轮触发了一次 JSON 修复重试，修复成功。
- 后续 5 个 Agent turn 未触发修复。

## 过程中发现并修复的问题

1. 真实 LLM 偶发输出非 JSON，导致真实路径失败。
   - 修复：`call_agent_json` 增加一次远程 JSON 修复重试。

2. 同一角色可能出现标点变体，例如 `药契监察使·陆闻` 与 `药契监察使陆闻`。
   - 修复：名称 key 归一化时去除中点、连接符、空白和常见标点。

3. 自由文本抽名过宽，会把 `陆闻是审判的执行者`、`审判场是核心场景` 误当候选名。
   - 修复：文本抽名只接受引号或冒号后的显式名称，并过滤谓词短语。

## 结论

当前实现已完成动态议事基础闭环：角色/设定生成器不再被固定顺序锁死，能够在新对象出现后提前插入；真实 LLM 路径可完成一次总纲议事模拟，并产出可确认的总纲候选、角色候选和设定候选。
