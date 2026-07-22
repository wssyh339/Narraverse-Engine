# 提示词目录

Prompt Catalog 是本项目最重要的扩展点之一。

提示词文件位于：

```text
backend/app/prompts/
```

目录加载逻辑位于：

```text
backend/app/agents/shared/prompt_catalog.py
```

Agent 绑定关系位于：

```text
backend/app/agents/prompts.py
```

## 设计原则

提示词是可复用任务，Agent 是稳定角色，Workflow 决定调用顺序。

这样可以避免两个问题：

- 把每段提示词都膨胀成一个永久 Agent；
- 把全部写作逻辑塞进单个巨大提示词。

## 主要提示词分组

### 立项与小说宪法

- `00_general_control_prompt.md`
- `01_core_conflict_system_prompt.md`
- `02_novel_constitution_prompt.md`
- `03_constitution_stress_test_prompt.md`

用于创作 Star 和高层规划。

### 大纲议事支持

- `04_macro_outline_prompt.md`
- `05_ending_backcast_prompt.md`
- `06_volume_outline_prompt.md`
- `07_rolling_chapter_outline_prompt.md`

用于大纲议事的支持材料；正式大纲写入只能通过 `outline_debate` 会话、确认和提交接口。

### 章节生产

- `08_chapter_card_prompt.md`
- `09_scene_outline_prompt.md`
- `10_draft_generation_prompt.md`
- `11_draft_self_check_prompt.md`
- `12_draft_rewrite_prompt.md`
- `28_next_chapter_state_change_prompt.md`
- `31_single_round_generation_combo_prompt.md`
- `35_chapter_prep_prompt.md`

用于已确认章纲之后的章节写前准备、章节卡、场景细纲、正文草稿和修订流程。`35_chapter_prep_prompt.md` 只能固化本章位置、情绪目标、正典依赖、伏笔提醒和字数预算，不得重写全书大纲、卷纲或章纲。

### 连续性与正典

- `13_narrative_ledger_update_prompt.md`
- `14_foreshadowing_management_prompt.md`
- `15_character_arc_management_prompt.md`
- `16_relationship_network_management_prompt.md`
- `17_world_rules_management_prompt.md`
- `18_timeline_check_prompt.md`
- `20_structure_editor_review_prompt.md`
- `21_ten_chapter_health_check_prompt.md`
- `22_rolling_outline_revision_prompt.md`
- `23_context_compression_prompt.md`

用于维持长篇状态一致性。

### 风格与专项任务

- `24_style_calibration_prompt.md`
- `19_branch_plot_generation_prompt.md`
- `25_subplot_design_prompt.md`
- `26_antagonist_design_prompt.md`
- `27_climax_design_prompt.md`
- `29_recommended_workflow_order.md`
- `30_minimal_work_template.md`

用于定向增强和未来工作流扩展。

## 新增提示词流程

1. 在 `backend/app/prompts/` 下新增 Markdown 文件。
2. 如有需要，在 Prompt Catalog 中注册。
3. 绑定到 Agent 或 workflow task。
4. 添加测试，确保提示词可被发现。
5. 文档说明该提示词会影响哪些状态或输出。

## 提示词安全规则

- 提示词不得要求模型直接覆盖正式正典。
- 如果输出会被持久化，应要求结构化输出。
- 提示词应明确列出所需上下文块。
- 遇到不确定信息，应保留不确定项，而不是硬编设定。
