# Prompt Agent Lifecycle Workflows Design

**Goal:** 将 `backend/app/prompts/00_*.md` 到 `31_*.md` 对应的 `prompt_agent` 节点，从“提示词目录式分组”重新设计为“长篇小说生产生命周期工作流”。

**Status:** 用户已确认方向，进入设计文档阶段。

**Date:** 2026-06-14

---

## 1. 背景

当前系统已经完成两件事：

1. 32 个长篇小说生产提示词已经拆为 Markdown 文件，并通过 Prompt Catalog 注册。
2. 每个提示词节点已经标记为 `node_subtype="prompt_agent"`，并暴露独立输入 schema、输出 schema、必需输入和产物字段。

但当前可视化工作流仍主要按提示词文件用途粗分为：

- `conception`：立项与小说宪法
- `outline_planning`：全书与分卷规划
- `chapter_production`：单章生产闭环
- `serial_maintenance`：连载维护与体检
- `special_design`：专项增强

这个分法能说明“提示词属于哪里”，但还不够像真实创作生产线。用户在前端 Agent 菜单里看到的仍偏向提示词目录，而不是“从立项、结构、分卷、单章、连载维护到专项增强”的可执行工作流。

## 2. 设计原则

1. 不新增 32 个正式 Agent。
   仍保留 11 个对外稳定 Agent，32 个提示词只作为 `prompt_agent` workflow node 或 prompt task。

2. 工作流面向创作生命周期，而不是面向文件编号。
   用户应看到“我现在处于小说生产的哪一步”，而不是“我正在使用第几个 prompt”。

3. `00_general_control` 作为隐式总控，不作为普通顺序节点。
   它在每次 prompt task 调用前组合 `task`、`context`、`expected_output_schema`，约束输出边界。

4. 正式闭环与快捷模式分离。
   `30_minimal_work_template` 和 `31_single_round_generation_combo` 是快捷模式，不应混在正式单章生产主链里。

5. 维护节点按触发条件运行。
   伏笔、人物弧线、关系网、世界规则、时间线和风格校准可以并行或按需触发，不必每章全跑。

6. 质量门必须可视化。
   宪法压力测试、正文自检、结构体检都需要有 passed / needs_revision / blocked 等明确回流路径。

## 3. 推荐工作流总览

推荐新增或替换为 6 条生命周期工作流：

1. `story_foundation_lifecycle`：立项与宪法工作流
2. `book_structure_lifecycle`：全书结构推演工作流
3. `volume_rolling_lifecycle`：分卷与滚动章纲工作流
4. `chapter_closed_loop_lifecycle`：单章生产闭环工作流
5. `serial_maintenance_lifecycle`：连载维护与体检工作流
6. `special_booster_lifecycle`：专项增强工作流

这些工作流可以替代当前 5 条 prompt workflow 的展示层，但底层仍复用现有 `PromptNodeContract`、`PromptCatalogEntry`、`node_subtype="prompt_agent"` 和 schema。

## 4. 总体拓扑

```mermaid
flowchart LR
  S["创作 Star 已确认立项种子"] --> C1["01 核心矛盾系统"]
  C1 --> C2["02 小说宪法"]
  C2 --> C3["03 宪法压力测试"]
  C3 -- "needs_revision / blocked" --> C1
  C3 -- "passed / passed_with_notes" --> CP["正典候选预览 canon_curator"]

  CP --> B1["04 全书宏观大纲"]
  B1 --> B2["05 结局反推"]
  B2 --> B3["26 反派设计"]
  B3 --> B4["27 高潮设计"]
  B4 --> V1["06 分卷大纲"]
  V1 --> V2["07 滚动章纲"]

  V2 --> CH0["28 下一章状态变化"]
  CH0 --> CH1["08 章节卡"]
  CH1 --> CH2["09 场景细纲"]
  CH2 --> CH3["10 正文生成"]
  CH3 --> CH4["11 正文自检"]
  CH4 -- "needs_revision / blocked" --> CH5["12 正文改写"]
  CH5 --> CH6["13 叙事账本更新"]
  CH4 -- "passed" --> CH6

  CH6 --> M["14-18 并行维护检查"]
  M --> H["20/21 结构体检"]
  H -- "revise_outline" --> R["22 滚动大纲修正"]
  R --> V2
```

## 5. 工作流一：立项与宪法

**Workflow ID:** `story_foundation_lifecycle`

**用途:** 承接创作 Star 已确认候选，将抽卡结果转化为可以支撑长篇连载的核心矛盾、小说宪法和正典候选。

**节点:**

| 顺序 | 节点 | 类型 | 默认 Agent | 输入 | 输出 |
|---:|---|---|---|---|---|
| 1 | `core_conflict_system` | prompt_agent | `chief_architect` | `project_seed`, `canon_context`, `market_position` | `core_conflict_system` |
| 2 | `novel_constitution` | prompt_agent | `chief_architect` | `project_seed`, `core_conflict_system`, `canon_context` | `novel_constitution` |
| 3 | `constitution_stress_test` | prompt_agent | `reviewer` | `novel_constitution`, `core_conflict_system`, `canon_context` | `constitution_review` |
| 4 | `canon_preview` | agent | `canon_curator` | `project_seed`, `core_conflict_system`, `novel_constitution`, `constitution_review` | `canon_candidates` |

**质量门:**

- `constitution_review.status in ["passed", "passed_with_notes"]`：进入正典候选预览。
- `constitution_review.status in ["needs_revision", "blocked"]`：回流到 `core_conflict_system` 或 `novel_constitution`。

**和现有区别:**

现有 `conception` 只是 `00 -> 01 -> 02 -> 03` 顺序展示。新设计把 `00` 下沉为隐式总控，把 01-03 接入创作 Star 的正式立项流程，并增加正典预览和质量门。

## 6. 工作流二：全书结构推演

**Workflow ID:** `book_structure_lifecycle`

**用途:** 从小说宪法推演整本书的结构，不急着写章节。

**节点:**

| 顺序 | 节点 | 类型 | 默认 Agent | 输入 | 输出 |
|---:|---|---|---|---|---|
| 1 | `macro_outline` | prompt_agent | `chapter_planner` | `novel_constitution`, `core_conflict_system`, `target_length`, `canon_context` | `macro_outline` |
| 2 | `ending_backcast` | prompt_agent | `chapter_planner` | `novel_constitution`, `macro_outline`, `desired_ending` | `ending_backcast` |
| 3 | `antagonist_design` | prompt_agent | `chief_architect` | `novel_constitution`, `core_conflict_system`, `protagonist_profile` | `antagonist_profile` |
| 4 | `climax_design` | prompt_agent | `chapter_planner` | `novel_constitution`, `macro_outline`, `crisis_candidates`, `foreshadowing_list` | `climax_design` |
| 5 | `structure_editor_review` | prompt_agent | `reviewer` | `macro_outline`, `rolling_chapter_outline`, `completed_chapters`, `novel_constitution` | `structure_review` |

**可选分支:**

- `branch_plot_generation`：当宏观结构出现多个可行方向时触发。
- `subplot_design`：当主线过直、人物线不足或需要副线支撑主题时触发。

**质量门:**

- `structure_review.structure_status == "healthy"`：进入分卷与滚动章纲。
- `watch`：允许进入下一步，但记录风险。
- `needs_revision / blocked`：回流到 `macro_outline` 或 `ending_backcast`。

**和现有区别:**

现有 `special_design` 把反派和高潮放在专项增强里。新设计中，反派和高潮是全书结构的关键承重墙，应进入主结构推演链路，同时仍保留按需单独调用能力。

## 7. 工作流三：分卷与滚动章纲

**Workflow ID:** `volume_rolling_lifecycle`

**用途:** 把全书结构落到当前卷，并维护未来 10-15 章的可写作章纲。

**节点:**

| 顺序 | 节点 | 类型 | 默认 Agent | 输入 | 输出 |
|---:|---|---|---|---|---|
| 1 | `volume_outline` | prompt_agent | `chapter_planner` | `novel_constitution`, `macro_outline`, `ending_backcast`, `volume_index` | `volume_outline` |
| 2 | `rolling_chapter_outline` | prompt_agent | `chapter_planner` | `novel_constitution`, `volume_outline`, `narrative_ledger`, `completed_chapters` | `rolling_chapter_outline` |
| 3 | `context_compression` | prompt_agent | `canon_curator` | `canon_context`, `completed_chapters`, `narrative_ledger`, `compression_goal` | `context_summary` |
| 4 | `rolling_outline_revision` | prompt_agent | `chapter_planner` | `rolling_chapter_outline`, `health_check_report`, `narrative_ledger`, `user_instruction` | `revised_rolling_chapter_outline` |

**触发条件:**

- 新卷开始：执行 `volume_outline`。
- 每次准备未来章节窗口：执行 `rolling_chapter_outline`。
- 上下文过长：执行 `context_compression`。
- 体检失败或用户改方向：执行 `rolling_outline_revision`。

**和现有区别:**

现有 `outline_planning` 是固定的宏观大纲、结局反推、分卷大纲、滚动章纲顺序。新设计将宏观结构和分卷滚动拆开，分卷章纲成为可循环修正的连载机制。

## 8. 工作流四：单章生产闭环

**Workflow ID:** `chapter_closed_loop_lifecycle`

**用途:** 写出一章，并完成自检、改写、账本更新，形成可持续连载闭环。

**节点:**

| 顺序 | 节点 | 类型 | 默认 Agent | 输入 | 输出 |
|---:|---|---|---|---|---|
| 1 | `next_chapter_state_change` | prompt_agent | `chapter_planner` | `current_story_state`, `rolling_chapter_outline`, `narrative_ledger` | `next_chapter_state_change_plan` |
| 2 | `chapter_card` | prompt_agent | `chapter_planner` | `novel_constitution`, `volume_outline`, `rolling_chapter_outline`, `narrative_ledger`, `previous_chapter_summary`, `user_instruction` | `chapter_card` |
| 3 | `scene_outline` | prompt_agent | `plot_narrator` | `novel_constitution`, `chapter_card`, `narrative_ledger`, `canon_context` | `scene_outline` |
| 4 | `draft_generation` | prompt_agent | `integrator` | `novel_constitution`, `chapter_card`, `scene_outline`, `narrative_ledger`, `style_profile`, `canon_context` | `integrated_draft` |
| 5 | `draft_self_check` | prompt_agent | `reviewer` | `integrated_draft`, `chapter_card`, `scene_outline`, `novel_constitution`, `narrative_ledger` | `draft_self_check` |
| 6 | `draft_rewrite` | prompt_agent | `reviewer` | `integrated_draft`, `draft_self_check`, `chapter_card`, `user_instruction`, `style_profile` | `rewritten_draft` |
| 7 | `narrative_ledger_update` | prompt_agent | `canon_curator` | `final_chapter_text`, `chapter_card`, `narrative_ledger`, `canon_context` | `narrative_ledger`, `candidate_canon_updates` |

**质量门:**

- `draft_self_check.pass_level == "passed"`：进入账本更新。
- `minor_revision / major_revision / blocked`：进入 `draft_rewrite`。
- `draft_rewrite.remaining_issues` 仍有 blocking：不得直接定稿。

**快捷模式:**

- `minimal_work_template`：极简章节工作环，用于快速试写。
- `single_round_generation_combo`：单轮组合生成，用于低成本探索，不替代正式闭环。

**和现有区别:**

现有 `chapter_production` 把正式闭环和快捷模板放在同一条线上。新设计把正式写作链路和快捷模式拆开，防止用户误以为 `31_single_round_generation_combo` 是标准生产方式。

## 9. 工作流五：连载维护与体检

**Workflow ID:** `serial_maintenance_lifecycle`

**用途:** 在连载过程中持续检查伏笔、人物、关系、世界规则、时间线、风格和结构健康。

**并行维护节点:**

| 节点 | 默认 Agent | 输出 |
|---|---|---|
| `foreshadowing_management` | `canon_curator` | `foreshadowing_updates` |
| `character_arc_management` | `canon_curator` | `character_arc_updates` |
| `relationship_network_management` | `canon_curator` | `relationship_network_updates` |
| `world_rules_management` | `fact_checker` | `world_rule_updates` |
| `timeline_check` | `fact_checker` | `timeline_check_report` |
| `style_calibration` | `style_unifier` | `style_profile` |

**汇总裁决节点:**

| 节点 | 默认 Agent | 输出 |
|---|---|---|
| `structure_editor_review` | `reviewer` | `structure_review` |
| `ten_chapter_health_check` | `reviewer` | `health_check_report` |

**回流:**

- 小问题：生成建议和候选更新。
- 中问题：触发 `rolling_outline_revision`。
- 大问题：回流到 `novel_constitution` 或 `macro_outline`。

**和现有区别:**

现有 `serial_maintenance` 是一串维护 prompt。新设计将它改成“并行检查 + 汇总裁决 + 回流修正”的结构，更符合长篇连载真实维护方式。

## 10. 工作流六：专项增强

**Workflow ID:** `special_booster_lifecycle`

**用途:** 当故事卡住、需要增强某一块时按需调用。

**节点:**

| 节点 | 用途 | 定位 |
|---|---|---|
| `branch_plot_generation` | 生成多分支剧情候选 | 卡文或分歧时调用 |
| `subplot_design` | 设计支线 | 主线过直或人物线不足时调用 |
| `antagonist_design` | 强化反派或对立力量 | 可被全书结构复用 |
| `climax_design` | 强化高潮候选 | 可被全书结构复用 |
| `recommended_workflow_order` | 推荐下一步工作流 | UI 助手或调度器使用 |
| `minimal_work_template` | 极简写作模板 | 快速试写 |
| `single_round_generation_combo` | 单轮组合生成 | 探索草稿，不替代正式链路 |

**和现有区别:**

现有 `special_design` 只有支线、反派、高潮。新设计把所有“不应作为主流程固定步骤，但对创作很有用”的 prompt 统一放入专项增强。

## 11. 现有工作流与新工作流对照

| 维度 | 现有设计 | 新设计 |
|---|---|---|
| 组织方式 | 按 prompt 类型分 5 组 | 按小说生产生命周期分 6 条流程 |
| `00_general_control` | 普通 conception 节点 | 隐式总控前置层 |
| 创作 Star 关系 | 和 prompt workflow 并列 | 立项种子直接进入核心矛盾、宪法、压力测试 |
| 全书结构 | 大纲节点和专项节点分离 | 宏观大纲、结局反推、反派、高潮合并为结构链 |
| 分卷章纲 | 属于 outline_planning 的尾部 | 独立成可循环修正工作流 |
| 单章生产 | 正式链路和快捷 prompt 混排 | 正式闭环与快捷模式分离 |
| 连载维护 | 长列表顺序展示 | 并行检查、汇总裁决、回流修正 |
| UI 理解成本 | 像提示词目录 | 像真实创作工作台生产线 |
| 执行接入 | 多为 prompt binding metadata | 可逐步映射到真实 runtime entrypoints |

## 12. API 设计影响

短期只改 `/api/workflows` 的展示数据，不改真实执行接口。

建议每条 workflow 返回：

```json
{
  "id": "chapter_closed_loop_lifecycle",
  "key": "chapter_closed_loop_lifecycle",
  "label": "单章生产闭环",
  "workflow_kind": "prompt_lifecycle",
  "runtime_status": "applied_via_prompt_binding",
  "nodes": [
    {
      "id": "chapter_card",
      "type": "prompt",
      "node_subtype": "prompt_agent",
      "prompt_id": "chapter_card",
      "agent_name": "chapter_planner",
      "inputs": ["novel_constitution", "volume_outline"],
      "outputs": ["chapter_card"],
      "input_schema": {},
      "output_schema": {}
    }
  ],
  "edges": [
    {
      "source": "chapter_card",
      "target": "scene_outline",
      "label": "章节卡生成场景细纲"
    }
  ]
}
```

中期可以增加：

- `workflow_kind`: `runtime` / `prompt_lifecycle` / `shortcut`
- `trigger_policy`: `manual` / `on_chapter_complete` / `every_10_chapters` / `on_quality_gate_failed`
- `quality_gate`: 节点级质量门配置
- `fallback_edges`: 回流边配置

## 13. 前端设计影响

Agent 菜单应从“提示词目录”转向“生命周期流程”：

1. 工作流列表展示 6 条主流程。
2. 节点标签显示：
   - `agent`
   - `control`
   - `prompt_agent`
3. 点击节点时继续显示：
   - Prompt ID
   - Prompt 文件
   - 默认 Agent
   - 模型覆盖
   - 输入字段
   - 输出字段
   - 输入 Schema
   - 输出 Schema
4. 边应显示语义：
   - `passed`
   - `needs_revision`
   - `blocked`
   - `parallel_check`
   - `revision_loop`
   - `shortcut`
5. 快捷模式应单独标识，避免和正式生产流程混淆。

## 14. 执行落地顺序

第一阶段：只改可视化工作流编排。

- 在 `prompt_catalog.py` 中新增生命周期 workflow definition。
- 保留旧 5 条 prompt workflow 一段时间，或通过 feature flag 隐藏旧分组。
- 更新测试，确保 32 个节点全部仍可被覆盖，且每个节点仍有 schema。

第二阶段：前端显示优化。

- Agent 菜单默认展示生命周期工作流。
- 对 `prompt_agent` 节点显示 subtype 标签和 schema 摘要。
- 对回流边、质量门边使用不同颜色或标签。

第三阶段：逐步接入真实 runtime。

- 创作 Star 的 6-9 步映射到 `story_foundation_lifecycle`。
- 总纲/章节大纲生成映射到 `book_structure_lifecycle` 和 `volume_rolling_lifecycle`。
- 单章正文生成映射到 `chapter_closed_loop_lifecycle`。

第四阶段：调度器增强。

- 使用 `recommended_workflow_order` 根据项目阶段推荐下一条工作流。
- 根据章节数、体检结果、上下文长度自动建议维护工作流。

## 15. 测试策略

后端测试：

1. 32 个 prompt node contract 仍全部存在。
2. 新 6 条 lifecycle workflow 被 `/api/workflows` 返回。
3. `chapter_closed_loop_lifecycle` 不包含 `minimal_work_template` 和 `single_round_generation_combo`。
4. `special_booster_lifecycle` 包含 `minimal_work_template` 和 `single_round_generation_combo`。
5. `story_foundation_lifecycle` 中所有 prompt 节点都有 `node_subtype="prompt_agent"`。
6. 质量门边必须包含 `needs_revision / blocked / passed` 语义。

前端测试：

1. Agent 菜单能显示 `prompt_agent` 标签。
2. 节点详情能显示输入 schema 和输出 schema。
3. 生命周期工作流名称可被选择。
4. 快捷模式节点有独立标签。

回归测试：

1. `/api/workflows` 仍保留正式运行工作流：创作 Star、初始化、长篇大纲推演、章节规划、单章正文、批量生成。
2. Agent 模型覆盖仍按 `workflow_id + agent_name` 生效。
3. Prompt Catalog 仍能加载所有 Markdown 文件。

## 16. 验收标准

1. 前端 Agent 菜单不再只像提示词目录，而是能看到 6 条小说生产生命周期工作流。
2. 每个 00-31 prompt 节点仍标记 `node_subtype="prompt_agent"`。
3. 每个 prompt 节点仍暴露独立输入 schema 和输出 schema。
4. 正式单章生产闭环清晰展示“状态变化 → 章节卡 → 场景细纲 → 正文 → 自检 → 改写 → 账本更新”。
5. 快捷模式与正式闭环分离。
6. 连载维护节点以并行检查和回流修正方式展示。
7. 不新增 32 个正式 Agent，不破坏 11 个稳定 Agent 边界。

## 17. 后续决策

实现前需要确认一个产品决策：

- 是否保留旧 5 条 prompt workflow 作为“提示词库视图”？

推荐答案：保留，但降级为高级/调试视图。默认展示新 6 条生命周期工作流。

