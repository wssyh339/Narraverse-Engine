# 大纲议事质量升级实施记录

更新时间：2026-06-30

## 背景

本轮目标是把当前“大纲能生成指定章数”升级为“长篇结构大纲可用”。计划原文明确指出，`2`、`50`、`100` 只是当前测试规模，不得写死到生成逻辑或验收逻辑中。

## 执行原则

- 议事流程只使用 6 个 Agent：`@主持总策划`、`@类型卖点`、`@结构医生`、`@角色生成`、`@设定生成`、`@连续性审计`。
- 不恢复历史大纲流程、历史图组件、历史章纲计划接口或历史席位配置。
- 卷数、每卷章数、总章数、章节窗口数均从 `scale_plan`、`volume_count`、`chapters_per_volume`、`chapter_ranges` 动态推导。
- 讨论阶段只产生候选；正式写入仍依赖用户确认。

## 已实施变更

### 1. 动态规模推导

服务端已支持：

- 明确 `target_volume_no` 时生成单卷；未指定时按请求规模生成全部卷。
- 明确 `target_chapter_no` 时生成单章；提供 `chapter_ranges` 或规模参数时生成批量章纲。
- `chapter_window_size` 默认由 `chapters_per_volume / DEFAULT_CHAPTER_WINDOWS_PER_VOLUME` 推导；当前 50 章/卷会得到 10 章窗口，但 10 不是固定写死的业务规则。

### 2. 卷纲字段补齐

每卷候选现在至少包含：

- `volume_no`
- `title`
- `volume_function`
- `core_goal`
- `main_conflict`
- `rhythm_model`
- `chapter_range`
- `ending_hook`
- `volume_hook`
- `character_arc`
- `setting_reveal_plan`
- `foreshadowing_plan`

质量门要求卷纲数量匹配请求，且关键字段覆盖率为 `1.0`。

### 3. 章节窗口先行

批量章纲先生成 `chapter_windows`，再由窗口派生 `chapter_outlines`。

每个 `chapter_window` 至少包含：

- `window_no`
- `volume_no`
- `chapter_range`
- `stage_goal`
- `reader_promise`
- `main_pressure`
- `state_change_goal`
- `new_information`
- `relationship_change`
- `resource_change`
- `rule_or_setting_reveal`
- `foreshadowing_to_plant`
- `foreshadowing_to_remind`
- `foreshadowing_to_mislead`
- `foreshadowing_to_payoff`
- `mini_crisis`
- `mini_climax`
- `transition_hook`
- `risk`

### 4. 逐章章纲从窗口展开

每章候选现在至少包含：

- `chapter_no`
- `volume_no`
- `window_no`
- `title`
- `outline`
- `pov_character`
- `core_event`
- `conflict`
- `crisis`
- `climax`
- `result`
- `hook`
- `cliffhanger`
- `state_change`
- `state_change_text`
- `foreshadowing_use`
- `reader_promise`
- `continuity_risk`
- `source_window`
- `source_window_detail`
- `milestone_function`

`state_change` 是结构化对象：`type`、`before`、`after`、`cost`。

`foreshadowing_use` 是结构化对象：`plant`、`remind`、`mislead`、`payoff`。

### 5. 模板化阻塞检查

模板阻塞词覆盖计划原文中的典型泛句，包括：

- `待确认`
- `围绕本章核心事件推进一次行动`
- `本章危机是主角必须作出不可逆选择`
- `本章高潮是主角执行选择并付出可见代价`
- `本章结果改变局面`
- `留下下一章必须回应的问题`
- `根据类型、读者体验和阶段冲突选择`

命中模板句会进入 `quality_metrics.blocking_items`，并使 `quality_metrics.status=failed`。

### 6. Agent 输出来源

每个 turn 现在保留：

- `decision`
- `decision_source=model|service_default|local_preview`
- `scores`
- `score_source=model|service_default|local_preview`

测试脚本会检查 `decision`、`scores` 以及来源字段的覆盖率。

## 严格验收指标

### 数量与结构

- `actual_volume_count == expected_volume_count`
- `actual_chapter_count == expected_chapter_count`
- `chapters_by_volume == expected_chapters_by_volume`
- `actual_chapter_window_count == expected_chapter_window_count`
- `volume_required_field_coverage == 1.0`
- `window_required_field_coverage == 1.0`
- `window_mini_climax_coverage == 1.0`

### 章节质量

- `template_blocking_count == 0`
- `state_change_coverage >= 0.95`
- `foreshadowing_use_coverage >= 0.90`
- `source_window_coverage >= 0.95`
- `crisis_climax_result_distinct_rate >= 0.95`
- `duplicate_title_rate <= 0.02`

### 伏笔与里程碑

- `foreshadowing_window_coverage >= 0.80`
- `volume_end_function_coverage == 1.0`
- `final_chapter_turn_present == true`

当前 2 卷 x 50 章测试中，这意味着第 50 章必须承担卷末功能，第 100 章必须承担第二卷收束或下一阶段钩子功能。换成别的规模时，判断会按每个 `chapter_range.end_chapter_no` 动态计算。

### LLM 与 Agent 契约

- 非 `local_preview` 测试中，所有 Agent turn 必须记录远程模型调用成功。
- `decision_coverage == 1.0`
- `score_coverage == 1.0`
- `decision_source_coverage == 1.0`
- `score_source_coverage == 1.0`
- 任一阶段 `validation_report.status == failed` 时不得视为严格通过。
- 服务端 `quality_metrics.status == failed` 时不得视为严格通过。

## 测试脚本变更

更新文件：`test-artifacts/run_outline_debate_browser_llm_tests.py`

新增能力：

- 每个题材可独立设置 `volume_count`、`chapters_per_volume`、`chapter_word_target`、`chapter_window_size`。
- 默认仍使用当前压测规模：2 卷、每卷 50 章。
- `planned_chapter_count`、`target_words`、`chapter_ranges`、`expected_chapter_window_count` 均动态计算。
- 输出 `ok` 与 `accepted` 分离：
  - `ok=true` 表示测试流程未中断。
  - `accepted=true` 表示严格验收全部通过。

## 本轮修改文件

- `backend/app/services/outline_debate_service.py`
- `backend/app/prompts/outline_debate_story_director_skill.md`
- `backend/app/prompts/outline_debate_market_position_skill.md`
- `backend/app/prompts/outline_debate_structure_doctor_skill.md`
- `backend/app/prompts/outline_debate_character_generator_skill.md`
- `backend/app/prompts/outline_debate_setting_generator_skill.md`
- `backend/app/prompts/outline_debate_continuity_auditor_skill.md`
- `test-artifacts/run_outline_debate_browser_llm_tests.py`

## 当前验证边界

已完成语法检查和本地合成检查。完整 10 题材真实浏览器 + LLM 压测仍需要运行新版脚本，以 `accepted=true` 作为最终验收信号。
